"""
HimShiksha - Server-Side Image Editing Engine
Supports crop, resize, rotate, flip, quality adjustment, and format conversion
using Pillow (PIL) with high performance and color preservation.
"""

import io
from typing import Tuple, Dict, Any, Optional
from PIL import Image, ImageOps


class ImageEngine:
    def edit_image(
        self,
        image_bytes: bytes,
        crop_box: Optional[Tuple[int, int, int, int]] = None, # (x, y, width, height)
        resize_dims: Optional[Tuple[int, int]] = None,       # (width, height)
        rotate_angle: float = 0.0,
        flip_h: bool = False,
        flip_v: bool = False,
        quality: int = 90,
        target_format: str = "jpeg"
    ) -> Tuple[bytes, str, Dict[str, Any]]:
        """
        Apply editing pipeline to an image and return (output_bytes, mime_type, metadata).
        """
        orig_size = len(image_bytes)
        img = Image.open(io.BytesIO(image_bytes))
        
        # Auto-orient based on EXIF tag
        img = ImageOps.exif_transpose(img) or img

        orig_w, orig_h = img.size

        # 1. Rotate
        if rotate_angle != 0.0:
            # Expand to accommodate rotated bounding box without clipping
            img = img.rotate(-rotate_angle, expand=True, resample=Image.Resampling.BICUBIC)

        # 2. Flip
        if flip_h:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if flip_v:
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        # 3. Crop (x, y, w, h)
        if crop_box:
            cx, cy, cw, ch = crop_box
            cx = max(0, min(cx, img.width - 1))
            cy = max(0, min(cy, img.height - 1))
            cw = max(1, min(cw, img.width - cx))
            ch = max(1, min(ch, img.height - cy))
            img = img.crop((cx, cy, cx + cw, cy + ch))

        # 4. Resize
        if resize_dims:
            rw, rh = resize_dims
            if rw > 0 and rh > 0:
                img = img.resize((rw, rh), resample=Image.Resampling.LANCZOS)

        # 5. Format conversion and color mode handling
        fmt = target_format.lower().strip()
        if fmt in ["jpg", "jpeg"]:
            save_format = "JPEG"
            mime_type = "image/jpeg"
            # JPEG doesn't support RGBA, blend over white background
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
        elif fmt == "png":
            save_format = "PNG"
            mime_type = "image/png"
        elif fmt == "webp":
            save_format = "WEBP"
            mime_type = "image/webp"
        else:
            save_format = "JPEG"
            mime_type = "image/jpeg"

        out_buf = io.BytesIO()
        save_kwargs = {}
        if save_format in ["JPEG", "WEBP"]:
            save_kwargs["quality"] = max(10, min(100, int(quality)))
            save_kwargs["optimize"] = True

        img.save(out_buf, format=save_format, **save_kwargs)
        out_bytes = out_buf.getvalue()

        meta = {
            "original_width": orig_w,
            "original_height": orig_h,
            "original_bytes": orig_size,
            "new_width": img.width,
            "new_height": img.height,
            "new_bytes": len(out_bytes),
            "format": save_format.lower()
        }

        return out_bytes, mime_type, meta


image_engine = ImageEngine()
