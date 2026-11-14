"""
HimShiksha API - PDF Page Numbering Service
Adds customizable page numbers to PDF documents (position, format, font size, start page).
Supports files up to 2GB via disk-based PyMuPDF.
"""

import os
import pymupdf
from fastapi import HTTPException
from utils.upload_handler import create_temp_output_path


def add_page_numbers_to_pdf(
    input_path: str,
    position: str = "bottom-center",
    format_type: str = "page_of_total",
    start_number: int = 1,
    margin: float = 36.0,
    font_size: float = 10.0
) -> str:
    """Add page numbers to every page of the PDF."""
    try:
        doc = pymupdf.open(input_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {str(e)}")

    total_pages = doc.page_count
    if total_pages < 1:
        doc.close()
        raise HTTPException(status_code=400, detail="PDF has no pages.")

    try:
        for i, page in enumerate(doc):
            curr_num = start_number + i
            if format_type == "page_of_total":
                text = f"Page {curr_num} of {start_number + total_pages - 1}"
            elif format_type == "slash":
                text = f"{curr_num} / {start_number + total_pages - 1}"
            else:
                text = f"{curr_num}"

            rect = page.rect
            text_width = font_size * len(text) * 0.55

            # Calculate X
            if "left" in position:
                x = margin
            elif "right" in position:
                x = rect.width - margin - text_width
            else:
                x = (rect.width - text_width) / 2.0

            # Calculate Y
            if "top" in position:
                y = margin + font_size
            else:
                y = rect.height - margin

            page.insert_text(
                pymupdf.Point(x, y),
                text,
                fontsize=font_size,
                color=(0.2, 0.2, 0.2)
            )

        out_path = create_temp_output_path(prefix="hs_numbered_", suffix=".pdf")
        doc.save(out_path, garbage=3, deflate=True)
        return out_path
    finally:
        doc.close()
