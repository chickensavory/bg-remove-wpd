from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import rawpy
import requests, time
from PIL import Image


def pil_to_rgba(pil_img: Image.Image) -> Image.Image:
    return pil_img if pil_img.mode == "RGBA" else pil_img.convert("RGBA")


def find_nontransparent_bbox(alpha: np.ndarray):
    ys, xs = np.where(alpha > 0)
    if xs.size == 0 or ys.size == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return x0, y0, x1, y1


def paste_on_white_canvas(
    img: Image.Image,
    out_size: int,
    left: float,
    right: float,
    top: float,
    bottom: float,
) -> Image.Image:
    rgba = pil_to_rgba(img)
    arr = np.array(rgba)
    alpha = arr[:, :, 3]

    bbox = find_nontransparent_bbox(alpha)
    if bbox is None:
        return Image.new("RGB", (out_size, out_size), (255, 255, 255))

    x0, y0, x1, y1 = bbox
    cropped = rgba.crop((x0, y0, x1 + 1, y1 + 1))
    cw, ch = cropped.size
    if cw <= 0 or ch <= 0:
        return Image.new("RGB", (out_size, out_size), (255, 255, 255))

    inner_w = out_size - left - right
    inner_h = out_size - top - bottom
    if inner_w <= 1 or inner_h <= 1:
        raise ValueError("Inner area is too small; check margin values")

    scale = min(inner_w / cw, inner_h / ch)
    new_w = max(1, int(round(cw * scale)))
    new_h = max(1, int(round(ch * scale)))
    resized = cropped.resize((new_w, new_h), resample=Image.LANCZOS)

    inner_x0 = left
    inner_y0 = top
    x = int(round(inner_x0 + (inner_w - new_w) / 2))
    y = int(round(inner_y0 + (inner_h - new_h) / 2))

    temp = Image.new("RGBA", (out_size, out_size), (255, 255, 255, 255))
    temp.alpha_composite(resized, (x, y))
    return temp.convert("RGB")


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

    if ext in [
        ".png",
        ".jpeg",
        ".jpg",
    ]:
        return input_path

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if ext in [
        ".nef",
        ".arw",
        ".cr3",
    ]:
        img = raw_to_rgb_pil(input_path)
        img.save(out_path, format="PNG")
        return out_path

    img = Image.open(input_path).convert("RGB")
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
    margin_left: float = 110,
    margin_right: float = 110,
    margin_top: float = 110,
    margin_bottom: float = 110,
    remove_size: str = "auto",
    out_ext: str = ".png",
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    
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
        remove_png_path = removebg_via_requests(
            normalized, temp_dir, api_key, size=remove_size
        )
        removed = Image.open(remove_png_path).convert("RGBA")

        out_img = paste_on_white_canvas(
            removed,
            out_size=out_size,
            left=margin_left,
            right=margin_right,
            top=margin_top,
            bottom=margin_bottom,
        )

        out_path = output_dir / f"{path.stem}_removebg_{out_size}{out_ext}"
        out_img.save(out_path)
        print("Wrote:", out_path)
        print(f"[TOTAL] Finished in {time.time() -t0:.2f}s")
        written.append(out_path)

    return written
