from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union, Any

import numpy as np
import rawpy
import requests
import time
import shutil
from PIL import Image

from removebg_square.xmp import write_processed_tags


@dataclass
class ProcessResult:
    written: list[Path]
    processed: int
    unprocessed: int
    processed_files: list[dict[str, Any]]
    unprocessed_files: list[dict[str, Any]]
    run_id: str


def pil_to_rgba(pil_img: Image.Image) -> Image.Image:
    return pil_img if pil_img.mode == "RGBA" else pil_img.convert("RGBA")


def find_nontransparent_bbox(alpha: np.ndarray):
    ys, xs = np.where(alpha > 0)
    if xs.size == 0 or ys.size == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return x0, y0, x1, y1


Size = Union[int, Tuple[int, int]]


def paste_on_white_canvas(
    img: Image.Image,
    out_size: Size,
    left: int,
    right: int,
    top: int,
    bottom: int,
) -> Image.Image:
    left = int(left)
    right = int(right)
    top = int(top)
    bottom = int(bottom)

    if isinstance(out_size, int):
        out_w, out_h = out_size, out_size
    else:
        out_w, out_h = int(out_size[0]), int(out_size[1])

    rgba = pil_to_rgba(img)
    arr = np.array(rgba)
    alpha = arr[:, :, 3]

    bbox = find_nontransparent_bbox(alpha)
    if bbox is None:
        return Image.new("RGB", (out_w, out_h), (255, 255, 255))

    x0, y0, x1, y1 = bbox
    cropped = rgba.crop((x0, y0, x1 + 1, y1 + 1))
    cw, ch = cropped.size
    if cw <= 0 or ch <= 0:
        return Image.new("RGB", (out_w, out_h), (255, 255, 255))

    inner_w = out_w - left - right
    inner_h = out_h - top - bottom
    if inner_w <= 1 or inner_h <= 1:
        raise ValueError("Inner area is too small; check margin values")

    scale = min(inner_w / cw, inner_h / ch)
    new_w = max(1, int(np.floor(cw * scale)))
    new_h = max(1, int(np.floor(ch * scale)))

    new_w = min(new_w, inner_w)
    new_h = min(new_h, inner_h)

    resized = cropped.resize((new_w, new_h), resample=Image.LANCZOS)

    x = left + (inner_w - new_w) // 2
    y = top + (inner_h - new_h) // 2

    x = max(left, min(x, out_w - right - new_w))
    y = max(top, min(y, out_h - bottom - new_h))

    temp = Image.new("RGBA", (out_w, out_h), (255, 255, 255, 255))
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

    if ext in [".png", ".jpeg", ".jpg"]:
        return input_path

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if ext in [".nef", ".arw", ".cr3"]:
        img = raw_to_rgb_pil(input_path)
        img.save(out_path, format="JPG")
        return out_path

    img = Image.open(input_path).convert("RGB")
    img.save(out_path, format="JPG")
    return out_path


def _copy_to_bad_folder(
    src: Path, bad_dir: Path, reason: str, extra_text: Optional[str] = None
) -> Optional[Path]:
    bad_dir.mkdir(parents=True, exist_ok=True)

    dst = bad_dir / src.name
    try:
        shutil.copy2(src, dst)
    except Exception:
        dst = None

    note = bad_dir / f"{src.stem}_ERROR.txt"
    try:
        msg = f"{reason}\n"
        if extra_text:
            msg += f"\n{extra_text}\n"
        note.write_text(msg, encoding="utf-8")
    except Exception:
        pass

    return dst


def removebg_via_requests(
    input_path: Path,
    out_dir: Path,
    api_key: str,
    bad_dir: Path,
    size: str = "auto",
    timeout_s: int = 60,
) -> tuple[Optional[Path], Optional[str], Optional[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{input_path.stem}.jpg"

    url = "https://api.remove.bg/v1.0/removebg"
    headers = {"X-Api-Key": api_key}

    try:
        with input_path.open("rb") as f:
            files = {"image_file": f}
            data = {"size": size}
            resp = requests.post(
                url, headers=headers, files=files, data=data, timeout=timeout_s
            )
    except requests.RequestException as e:
        _copy_to_bad_folder(
            src=input_path,
            bad_dir=bad_dir,
            reason="remove.bg request failed (network/timeout)",
            extra_text=str(e),
        )
        return None, "removebg_request_failed", str(e)

    if resp.status_code == 200:
        out_path.write_bytes(resp.content)
        return out_path, None, None

    if 400 <= resp.status_code <= 403:
        ct = resp.headers.get("Content-Type", "")
        extra = None
        if "application/json" in ct:
            try:
                extra = str(resp.json())
            except Exception:
                extra = resp.text[:2000]
        else:
            extra = resp.text[:2000]

        _copy_to_bad_folder(
            src=input_path,
            bad_dir=bad_dir,
            reason=f"remove.bg HTTP {resp.status_code} {resp.reason} (ignored)",
            extra_text=extra,
        )
        return None, f"removebg_http_{resp.status_code}", extra

    ct = resp.headers.get("Content-Type", "")
    extra = None
    if "application/json" in ct:
        try:
            extra = str(resp.json())
        except Exception:
            extra = resp.text[:2000]
    else:
        extra = resp.text[:2000]

    resp.raise_for_status()
    return None, f"removebg_http_{resp.status_code}", extra


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
    out_size: Size = 1000,
    margin_left: int = 111,
    margin_right: int = 111,
    margin_top: int = 111,
    margin_bottom: int = 111,
    remove_size: str = "auto",
    out_ext: str = ".png",
    xmp_tool: str = "removebg-square-cli",
    embed_png_xmp: bool = True,
    also_write_xmp_sidecar: bool = False,
    run_id: str = "unknown",
) -> ProcessResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)

    total_t0 = time.time()
    run_date = time.strftime("%Y-%m-%d")

    files = iter_input_files(input_dir)
    if not files:
        print("No input files found.")
        return ProcessResult(
            written=[],
            processed=0,
            unprocessed=0,
            processed_files=[],
            unprocessed_files=[],
            run_id=run_id,
        )

    temp_dir = output_dir / "_tmp_removebg"
    temp_dir.mkdir(parents=True, exist_ok=True)

    bad_dir = output_dir / "bad"
    written: list[Path] = []

    processed = 0
    unprocessed = 0

    processed_files: list[dict[str, Any]] = []
    unprocessed_files: list[dict[str, Any]] = []

    def _record_processed(*, src: str, dest: str, seconds: float) -> None:
        processed_files.append(
            {
                "src": src,
                "dest": dest,
                "seconds": float(seconds),
            }
        )

    def _record_unprocessed(
        *,
        src: str,
        dest: Optional[str],
        reason: str,
        error: Optional[str],
        seconds: float,
    ) -> None:
        unprocessed_files.append(
            {
                "src": src,
                "dest": dest or "",
                "reason": reason,
                "error": (error or "")[:2000],
                "seconds": float(seconds),
            }
        )

    for idx, path in enumerate(files, start=1):
        img_t0 = time.time()
        print(f"[{idx}/{len(files)}] Processing: {path}")

        # 1) Normalize
        try:
            normalized = normalize_input_to_png(
                path, temp_dir / f"{path.stem}_normalized.png"
            )
        except Exception as e:
            bad_copy = _copy_to_bad_folder(
                path, bad_dir, "Normalize/open failed (skipped)", str(e)
            )
            print("  -> Skipped (normalize failed)")
            unprocessed += 1
            _record_unprocessed(
                src=path.name,
                dest=(str(bad_copy.name) if bad_copy else ""),
                reason="normalize_failed",
                error=str(e),
                seconds=time.time() - img_t0,
            )
            continue

        remove_png_path, fail_reason, fail_extra = removebg_via_requests(
            normalized,
            temp_dir,
            api_key,
            bad_dir=bad_dir,
            size=remove_size,
        )

        if remove_png_path is None:
            print("  -> Skipped (remove.bg 400–403 or request failure; copied to bad/)")
            unprocessed += 1
            _record_unprocessed(
                src=path.name,
                dest=str((bad_dir / path.name).name),
                reason=fail_reason or "removebg_failed",
                error=fail_extra,
                seconds=time.time() - img_t0,
            )
            continue

        try:
            removed = Image.open(remove_png_path).convert("RGBA")
        except Exception as e:
            bad_copy = _copy_to_bad_folder(
                path, bad_dir, "Failed to open remove.bg output (skipped)", str(e)
            )
            print("  -> Skipped (could not open remove.bg output)")
            unprocessed += 1
            _record_unprocessed(
                src=path.name,
                dest=(str(bad_copy.name) if bad_copy else ""),
                reason="open_removebg_output_failed",
                error=str(e),
                seconds=time.time() - img_t0,
            )
            continue

        try:
            out_img = paste_on_white_canvas(
                removed,
                out_size=out_size,
                left=margin_left,
                right=margin_right,
                top=margin_top,
                bottom=margin_bottom,
            )
        except Exception as e:
            bad_copy = _copy_to_bad_folder(
                path, bad_dir, "Canvas/paste failed (skipped)", str(e)
            )
            print("  -> Skipped (paste_on_white_canvas failed)")
            unprocessed += 1
            _record_unprocessed(
                src=path.name,
                dest=(str(bad_copy.name) if bad_copy else ""),
                reason="canvas_paste_failed",
                error=str(e),
                seconds=time.time() - img_t0,
            )
            continue

        out_path = output_dir / f"{path.stem}{out_ext}"
        try:
            out_img.save(out_path)
        except Exception as e:
            bad_copy = _copy_to_bad_folder(
                path, bad_dir, "Save output failed (skipped)", str(e)
            )
            print("  -> Skipped (save failed)")
            unprocessed += 1
            _record_unprocessed(
                src=path.name,
                dest=(str(bad_copy.name) if bad_copy else ""),
                reason="save_failed",
                error=str(e),
                seconds=time.time() - img_t0,
            )
            continue

        written.append(out_path)
        processed += 1

        tagged = write_processed_tags(
            out_path,
            tool=xmp_tool,
            processed_date=run_date,
            embed_png=embed_png_xmp,
            also_write_sidecar=also_write_xmp_sidecar,
        )
        if tagged:
            print(f"  [XMP] tagged: {out_path.name} (ProcessedWith:{xmp_tool})")
        else:
            print(f"  [XMP] FAILED to tag: {out_path.name}")

        print(f"  Wrote: {out_path}")
        sec = time.time() - img_t0
        print(f"  Per-image time: {sec:.2f}s")

        _record_processed(src=path.name, dest=out_path.name, seconds=sec)

    print(
        f"[TOTAL] Finished {processed}/{len(files)} images in {time.time() - total_t0:.2f}s"
    )
    return ProcessResult(
        written=written,
        processed=processed,
        unprocessed=unprocessed,
        processed_files=processed_files,
        unprocessed_files=unprocessed_files,
        run_id=run_id,
    )
