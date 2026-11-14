"""
HimShiksha API - PDF Editor, Manipulation & Styling Service
Handles rotation, text/image watermarks, color effect presets, page reordering, and TXT conversions.
"""

import os
import io
import math
import pymupdf
from fastapi import HTTPException
from utils.upload_handler import create_temp_output_path
from pdf_color_engine import PDFColorEngine
from pdf_editor_engine import PDFEditorEngine

color_engine = PDFColorEngine()
editor_engine = PDFEditorEngine()


def rotate_pdf_file(input_path: str, angle: int = 90) -> str:
    """Rotate all pages in a PDF by the specified degrees (90, 180, 270)."""
    try:
        doc = pymupdf.open(input_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {str(e)}")

    try:
        for page in doc:
            page.set_rotation((page.rotation + angle) % 360)

        out_path = create_temp_output_path(prefix="hs_rotated_", suffix=".pdf")
        doc.save(out_path, garbage=3, deflate=True)
        return out_path
    finally:
        doc.close()


def watermark_pdf_file(
    input_path: str,
    text: str = "CONFIDENTIAL",
    opacity: float = 0.3,
    rotation: float = 45.0,
    font_size: float = 48.0,
    color_rgb: tuple = (0.5, 0.5, 0.5)
) -> str:
    """Add a diagonal/custom text watermark across every page of the PDF."""
    try:
        doc = pymupdf.open(input_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {str(e)}")

    try:
        for page in doc:
            rect = page.rect
            cx, cy = rect.width / 2.0, rect.height / 2.0
            p = pymupdf.Point(cx, cy)
            # PyMuPDF insert_text with morph / opacity
            page.insert_text(
                p,
                text,
                fontsize=font_size,
                rotate=rotation,
                color=color_rgb,
                fill_opacity=max(0.05, min(1.0, opacity))
            )

        out_path = create_temp_output_path(prefix="hs_watermarked_", suffix=".pdf")
        doc.save(out_path, garbage=3, deflate=True)
        return out_path
    finally:
        doc.close()


def apply_pdf_color_effects_file(
    input_path: str,
    preset: str = "grayscale",
    intensity: float = 1.0,
    dpi: int = 150
) -> str:
    """Apply visual color filters (invert, grayscale, sepia, warm, cool, etc.) to PDF pages."""
    try:
        with open(input_path, "rb") as f:
            pdf_bytes = f.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read PDF: {str(e)}")

    try:
        processed_bytes = color_engine.apply_effect(
            pdf_bytes=pdf_bytes,
            preset=preset,
            intensity=intensity,
            dpi=dpi
        )
        out_path = create_temp_output_path(prefix="hs_colored_", suffix=".pdf")
        with open(out_path, "wb") as f_out:
            f_out.write(processed_bytes)
        return out_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Color effect processing failed: {str(e)}")


def edit_pdf_pages_file(input_path: str, operations_json: str) -> str:
    """Execute page operations (reorder, delete, rotate) on PDF."""
    try:
        with open(input_path, "rb") as f:
            pdf_bytes = f.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read PDF: {str(e)}")

    try:
        out_bytes = editor_engine.edit_pages(
            primary_pdf_bytes=pdf_bytes,
            page_operations_json=operations_json
        )
        out_path = create_temp_output_path(prefix="hs_edited_", suffix=".pdf")
        with open(out_path, "wb") as f_out:
            f_out.write(out_bytes)
        return out_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF page editor failed: {str(e)}")


def txt_to_pdf_file(input_path: str) -> str:
    """Convert text file into a paginated PDF document with unicode support."""
    try:
        with open(input_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read text file: {str(e)}")

    doc = pymupdf.open()
    lines = content.splitlines()
    lines_per_page = 48
    margin = 54
    line_height = 14

    for i in range(0, max(1, len(lines)), lines_per_page):
        chunk = lines[i:i + lines_per_page]
        page = doc.new_page(width=595, height=842) # A4
        y = margin
        for line in chunk:
            page.insert_text(pymupdf.Point(margin, y), line[:100], fontsize=10)
            y += line_height

    out_path = create_temp_output_path(prefix="hs_txt_to_pdf_", suffix=".pdf")
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return out_path


def pdf_to_txt_file(input_path: str) -> str:
    """Extract plain text from PDF."""
    try:
        doc = pymupdf.open(input_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {str(e)}")

    all_text = []
    try:
        for page in doc:
            all_text.append(page.get_text())
    finally:
        doc.close()

    out_path = create_temp_output_path(prefix="hs_pdf_to_txt_", suffix=".txt")
    with open(out_path, "w", encoding="utf-8") as f_out:
        f_out.write("\n\n--- Page Break ---\n\n".join(all_text))
    return out_path
