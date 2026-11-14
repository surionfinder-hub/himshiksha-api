"""
HimShiksha API - Archive & Batch Processing Service
Handles PDF to Images (ZIP packaging) and Images to PDF conversions.
Enforces ZIP bomb protections and safe extraction bounds.
"""

import os
import io
import zipfile
import pymupdf
from PIL import Image
from fastapi import HTTPException
from utils.upload_handler import create_temp_output_path
from utils.security import sanitize_filename
from utils.zip_protection import inspect_and_validate_zip, safe_extract_zip


def pdf_to_images_zip(input_pdf_path: str, img_format: str = "png", dpi: int = 150, base_name: str = "page") -> str:
    """Render PDF pages to images and package into a ZIP archive."""
    try:
        doc = pymupdf.open(input_pdf_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {str(e)}")

    total_pages = doc.page_count
    if total_pages < 1:
        doc.close()
        raise HTTPException(status_code=400, detail="PDF contains no pages.")

    fmt = img_format.lower().replace(".", "").strip()
    ext = "jpg" if fmt in ["jpg", "jpeg"] else "png"
    safe_base = sanitize_filename(base_name)
    out_zip_path = create_temp_output_path(prefix="hs_pdf_imgs_", suffix=".zip")

    try:
        with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=dpi)
                img_data = pix.tobytes(ext)
                filename = f"{safe_base}_{i+1:03d}.{ext}"
                zf.writestr(filename, img_data)
        return out_zip_path
    finally:
        doc.close()


def images_to_pdf_file(image_paths: list[str]) -> str:
    """Convert multiple image files in order into a single PDF document."""
    if not image_paths:
        raise HTTPException(status_code=400, detail="No images provided for PDF conversion.")

    out_doc = pymupdf.open()
    try:
        for idx, img_path in enumerate(image_paths):
            try:
                img = Image.open(img_path)
                w, h = img.size
                # Create PDF page matching image dimensions
                page = out_doc.new_page(width=w, height=h)
                page.insert_image(pymupdf.Rect(0, 0, w, h), filename=img_path)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Cannot process image #{idx+1}: {str(e)}")

        out_path = create_temp_output_path(prefix="hs_imgs_to_pdf_", suffix=".pdf")
        out_doc.save(out_path, garbage=3, deflate=True)
        return out_path
    finally:
        out_doc.close()
