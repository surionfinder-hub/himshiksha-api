"""
HimShiksha API - Image Processing Service
Handles image format conversion, target-size compression, and editing operations.
Supports files up to 2GB via disk-based PIL processing.
"""

import os
import io
from PIL import Image, ImageOps
from fastapi import HTTPException
from utils.upload_handler import create_temp_output_path
from image_engine import ImageEngine

image_engine = ImageEngine()


def convert_image_format(input_path: str, target_format: str = "png", quality: int = 90) -> tuple[str, str, str]:
    """
    Convert image to target format (png, jpeg, webp).
    Returns (out_path, mime_type, extension).
    """
    try:
        img = Image.open(input_path)
        img = ImageOps.exif_transpose(img) or img
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot open image: {str(e)}")

    fmt = target_format.lower().replace(".", "").strip()
    if fmt in ["jpg", "jpeg"]:
        save_format = "JPEG"
        ext = ".jpg"
        mime = "image/jpeg"
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = bg
        else:
            img = img.convert("RGB")
    elif fmt == "webp":
        save_format = "WEBP"
        ext = ".webp"
        mime = "image/webp"
    elif fmt == "png":
        save_format = "PNG"
        ext = ".png"
        mime = "image/png"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported target image format: {target_format}")

    out_path = create_temp_output_path(prefix="hs_img_", suffix=ext)
    try:
        save_kwargs = {}
        if save_format in ["JPEG", "WEBP"]:
            save_kwargs["quality"] = max(10, min(100, quality))
            save_kwargs["optimize"] = True
        img.save(out_path, format=save_format, **save_kwargs)
        return out_path, mime, ext
    except Exception as e:
        if os.path.exists(out_path):
            os.remove(out_path)
        raise HTTPException(status_code=500, detail=f"Image conversion failed: {str(e)}")


def compress_image_to_target(
    input_path: str,
    target_kb: int = 200,
    max_width: int = 2000,
    max_height: int = 2000
) -> tuple[str, dict]:
    """Compress image aiming for target file size while preserving quality."""
    orig_size = os.path.getsize(input_path)
    try:
        img = Image.open(input_path)
        img = ImageOps.exif_transpose(img) or img
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot open image: {str(e)}")

    # Resize if above max dimensions
    w, h = img.size
    if w > max_width or h > max_height:
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

    if img.mode != "RGB":
        img = img.convert("RGB")

    target_bytes = target_kb * 1024
    out_path = create_temp_output_path(prefix="hs_img_comp_", suffix=".jpg")

    # Binary search optimal JPEG quality
    best_quality = 85
    min_q = 15
    max_q = 95
    while min_q <= max_q:
        mid_q = (min_q + max_q) // 2
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=mid_q, optimize=True)
        size = buf.tell()
        if size <= target_bytes:
            best_quality = mid_q
            min_q = mid_q + 1
        else:
            max_q = mid_q - 1

    img.save(out_path, format="JPEG", quality=best_quality, optimize=True)
    comp_size = os.path.getsize(out_path)
    savings = round(((orig_size - comp_size) / orig_size) * 100, 2) if orig_size > 0 else 0.0

    stats = {
        "original_bytes": orig_size,
        "compressed_bytes": comp_size,
        "savings_percent": max(0.0, savings),
        "quality_used": best_quality,
        "width": img.width,
        "height": img.height
    }
    return out_path, stats
