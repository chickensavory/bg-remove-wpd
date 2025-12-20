from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import rawpy
import requests
from PIL import Image, ImageOps


def pil_to_rgba(pil_img: Image.Image) -> Image.Image:
    return pil_img if pil_img.mode == "RGBA" else pil_img.convert("RGBA")


def find_nontransparent_bbox(alpha: np.ndarray):
    ys, xs = np.where(alpha > 0)
    if xs.size == 0 or ys.size == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return x0, y0, x1, y1


def cutout_to_square_canvas(
    obj_rgba: Image.Image, out_size: int, padding: int
) -> Image.Image:
    obj_rgba = pil_to_rgba(obj_rgba)
    rgba = np.array(obj_rgba)
    alpha = rgba[:, :, 3]

    bbox = find_nontransparent_bbox(alpha)
    if bbox is None:
        return Image.new("RGBA", (out_size, out_size), (0, 0, 0, 0))

    x0, y0, x1, y1 = bbox
    cropped = obj_rgba.crop((x0, y0, x1 + 1, y1 + 1))

    cw, ch = cropped.size
    if cw <= 0 or ch <= 0:
        return Image.new("RGBA", (out_size, out_size), (0, 0, 0, 0))

    target_long = max(1, out_size - 2 * padding)
    scale = target_long / max(cw, ch)
    new_w = max(1, int(round(cw * scale)))
    new_h = max(1, int(round(ch * scale)))

    resized = cropped.resize((new_w, new_h), resample=Image.LANCZOS)

    canvas = Image.new("RGBA", (out_size, out_size), (255, 255, 255, 255))
    x = (out_size - new_w) // 2
    y = (out_size - new_h) // 2
    canvas.alpha_composite(resized, (x, y))
    return canvas


def raw_to_rgb_pil(input_path: Path) -> Image.Image:
    with rawpy.imread(str(input_path)) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=8,
        )
    return Image.fromarray(rgb, mode="RGB")


def normalize_input_to_png(input_path: Path, out_path: Path) -> Path:
    ext = input_path.suffix.lower()

    if ext in [".png", ".jpeg", ".jpg"]:
        return input_path

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if ext in [".nef", ".arw", ".cr3"]:
        img = raw_to_rgb_pil(input_path)
        img.save(out_path, format="PNG")
        return out_path

    img = Image.open(input_path).convert("RGB")
    img.save(out_path, format="PNG")
    return out_path


def _safe_exif_transpose(img: Image.Image) -> Image.Image:
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def _try_ocr_best_rotation(img_rgb: Image.Image) -> Image.Image:
    try:
        import cv2
        import easyocr
    except Exception:
        return img_rgb

    try:
        reader = easyocr.Reader(["en"], gpu=False)

        def score(pil_img: Image.Image) -> float:
            arr = np.array(pil_img)
            if arr.ndim == 3 and arr.shape[2] == 3:
                bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            else:
                return 0.0
            results = reader.readtext(bgr, detail=1, paragraph=False)
            if not results:
                return 0.0
            total = 0.0
            for _bbox, text, conf in results:
                t = (text or "").strip()
                if len(t) >= 2:
                    total += float(conf) * min(len(t), 20)
            return total

        candidates = []
        for angle in (0, 90, 180, 270):
            if angle == 0:
                cand = img_rgb
            else:
                cand = img_rgb.rotate(angle, expand=True)
            candidates.append((score(cand), angle, cand))

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_angle, best_img = candidates[0]

        if best_score <= 0.0 or best_angle == 0:
            return img_rgb
        return best_img
    except Exception:
        return img_rgb


def rotate_input_upright(input_path: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(input_path).convert("RGB")
    img = _safe_exif_transpose(img)
    img = _try_ocr_best_rotation(img)
    img.save(out_path, format="PNG")
    return out_path


def removebg_via_requests(
    input_path: Path, out_dir: Path, api_key: str, size: str = "auto"
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{input_path.stem}_removebg.png"

    url = "https://api.remove.bg/v1.0/removebg"
    headers = {"X-Api-Key": api_key}

    with input_path.open("rb") as f:
        files = {"image_file": f}
        data = {"size": size}
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)

    if resp.status_code != 200:
        print("remove.bg HTTP", resp.status_code, resp.reason)
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct:
            try:
                print("remove.bg error JSON:", resp.json())
            except Exception:
                print("remove.bg error body:", resp.text[:2000])
        else:
            print("remove.bg error body:", resp.text[:2000])
        resp.raise_for_status()

    out_path.write_bytes(resp.content)
    return out_path


def iter_input_files(input_dir: Path) -> list[Path]:
    patterns = [
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.webp",
        "*.bmp",
        "*.tif",
        "*.tiff",
        "*.nef",
        "*.arw",
        "*.cr3",
    ]
    files: list[Path] = []
    for pat in patterns:
        files.extend(input_dir.glob(pat))
    return sorted(set(files))


def process_folder(
    input_dir: Path,
    output_dir: Path,
    api_key: str,
    out_size: int = 1000,
    padding: int = 50,
    remove_size: str = "auto",
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)

    files = iter_input_files(input_dir)
    if not files:
        return []

    temp_dir = output_dir / "_tmp_removebg"
    temp_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for path in files:
        print("Processing:", path)

        normalized = normalize_input_to_png(
            path, temp_dir / f"{path.stem}_normalized.png"
        )

        rotated = rotate_input_upright(
            normalized, temp_dir / f"{path.stem}_rotated.png"
        )

        remove_png_path = removebg_via_requests(
            rotated, temp_dir, api_key, size=remove_size
        )
        removed = Image.open(remove_png_path).convert("RGBA")

        out = cutout_to_square_canvas(removed, out_size=out_size, padding=padding)

        out_path = output_dir / f"{path.stem}_{out_size}x{out_size}_pad{padding}.png"
        out.save(out_path)
        print("Wrote:", out_path)
        written.append(out_path)

    return written
