"""
HimShiksha - Comprehensive PDF Color Effects & Filter Engine
Supports 10 visual presets:
  1. Original
  2. Invert / Negative
  3. Grayscale
  4. Black & White
  5. Warm Tone
  6. Cool Tone
  7. Classic Blue
  8. Green Tone
  9. Sepia
  10. High Contrast

Features adjustable intensity, page-by-page memory streaming, and exact
page dimensions & orientation preservation.
Powered by PyMuPDF (fitz) and PIL/NumPy.
"""

import io
import gc
from typing import Optional
from PIL import Image
import numpy as np

try:
    import pymupdf as fitz
except ImportError:
    import fitz


class PDFColorEngine:
    def apply_filter_to_image(
        self,
        img: Image.Image,
        preset: str = "invert",
        intensity: float = 1.0
    ) -> Image.Image:
        """
        Applies one of the 10 color effect presets to a PIL RGB image with intensity blending.
        """
        preset_clean = preset.lower().replace("_", "-").strip()
        if preset_clean in ("original", "none", "") or intensity <= 0.0:
            return img

        alpha = float(np.clip(intensity, 0.0, 1.0))
        arr = np.array(img, dtype=np.float32)
        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]

        if preset_clean in ("invert", "negative"):
            r_target = 255.0 - r
            g_target = 255.0 - g
            b_target = 255.0 - b

        elif preset_clean == "grayscale":
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            r_target = lum
            g_target = lum
            b_target = lum

        elif preset_clean in ("black-white", "bw", "threshold"):
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            bw = np.where(lum > 128.0, 255.0, 0.0)
            r_target = bw
            g_target = bw
            b_target = bw

        elif preset_clean in ("warm", "warm-tone"):
            r_target = np.clip(r * 1.10 + 15.0, 0.0, 255.0)
            g_target = np.clip(g * 1.03 + 8.0, 0.0, 255.0)
            b_target = np.clip(b * 0.88 - 8.0, 0.0, 255.0)

        elif preset_clean in ("cool", "cool-tone"):
            r_target = np.clip(r * 0.90 - 5.0, 0.0, 255.0)
            g_target = np.clip(g * 1.04 + 6.0, 0.0, 255.0)
            b_target = np.clip(b * 1.15 + 18.0, 0.0, 255.0)

        elif preset_clean in ("classic-blue", "blue"):
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            r_target = np.clip(lum * 0.72 + 10.0, 0.0, 255.0)
            g_target = np.clip(lum * 0.86 + 25.0, 0.0, 255.0)
            b_target = np.clip(lum * 1.18 + 55.0, 0.0, 255.0)

        elif preset_clean in ("green", "green-tone", "natural-green"):
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            r_target = np.clip(lum * 0.78 + 10.0, 0.0, 255.0)
            g_target = np.clip(lum * 1.18 + 38.0, 0.0, 255.0)
            b_target = np.clip(lum * 0.80 + 15.0, 0.0, 255.0)

        elif preset_clean == "sepia":
            r_target = np.clip(0.393 * r + 0.769 * g + 0.189 * b, 0.0, 255.0)
            g_target = np.clip(0.349 * r + 0.686 * g + 0.168 * b, 0.0, 255.0)
            b_target = np.clip(0.272 * r + 0.534 * g + 0.131 * b, 0.0, 255.0)

        elif preset_clean in ("high-contrast", "contrast"):
            factor = 1.0 + (0.9 * alpha)
            r_target = np.clip((r - 128.0) * factor + 128.0, 0.0, 255.0)
            g_target = np.clip((g - 128.0) * factor + 128.0, 0.0, 255.0)
            b_target = np.clip((b - 128.0) * factor + 128.0, 0.0, 255.0)
            return Image.fromarray(np.stack([r_target, g_target, b_target], axis=2).astype(np.uint8))

        else:
            return img

        # Blend target effect with original image based on intensity alpha
        r_out = np.clip((1.0 - alpha) * r + alpha * r_target, 0.0, 255.0).astype(np.uint8)
        g_out = np.clip((1.0 - alpha) * g + alpha * g_target, 0.0, 255.0).astype(np.uint8)
        b_out = np.clip((1.0 - alpha) * b + alpha * b_target, 0.0, 255.0).astype(np.uint8)

        return Image.fromarray(np.stack([r_out, g_out, b_out], axis=2))

    def transform_pdf(
        self,
        pdf_bytes: bytes,
        preset: str = "invert",
        intensity: float = 1.0,
        target_dpi: int = 150
    ) -> bytes:
        """
        Processes multi-page PDF document, applies effect with intensity,
        and generates valid output PDF preserving page dimensions and orientation.
        """
        src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(src_doc) == 0:
            src_doc.close()
            raise ValueError("PDF document contains 0 pages.")

        out_doc = fitz.open()

        try:
            for page_idx in range(len(src_doc)):
                src_page = src_doc[page_idx]
                rect = src_page.rect
                rotation = src_page.rotation

                matrix = fitz.Matrix(target_dpi / 72.0, target_dpi / 72.0)
                pix = src_page.get_pixmap(matrix=matrix, alpha=False)

                pil_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                filtered_img = self.apply_filter_to_image(pil_img, preset=preset, intensity=intensity)

                img_buf = io.BytesIO()
                filtered_img.save(img_buf, format="JPEG", quality=92, optimize=True)
                img_bytes = img_buf.getvalue()

                new_page = out_doc.new_page(width=rect.width, height=rect.height)
                if rotation != 0:
                    new_page.set_rotation(rotation)

                new_page.insert_image(rect, stream=img_bytes)

                del pix, pil_img, filtered_img, img_bytes, img_buf
                gc.collect()

            out_buf = io.BytesIO()
            out_doc.save(out_buf, garbage=3, deflate=True)
            result_bytes = out_buf.getvalue()

            verify_doc = fitz.open(stream=result_bytes, filetype="pdf")
            if len(verify_doc) != len(src_doc):
                verify_doc.close()
                raise ValueError("Verification failed: Page count mismatch.")
            verify_doc.close()

            return result_bytes

        finally:
            src_doc.close()
            out_doc.close()


pdf_color_engine = PDFColorEngine()
