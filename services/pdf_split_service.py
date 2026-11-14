"""
HimShiksha API - PDF Split Service
Splits PDF documents by page ranges or into individual pages (ZIP).
Supports files up to 2GB via disk-based PyMuPDF.
"""

import os
import io
import zipfile
import pymupdf
from fastapi import HTTPException
from utils.upload_handler import create_temp_output_path
from utils.security import sanitize_filename


def parse_page_ranges(range_str: str, max_pages: int) -> list[int]:
    """Parse range string like '1-3, 5, 8-10' into 0-based page indices."""
    pages = set()
    parts = [p.strip() for p in range_str.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            sub = part.split("-", 1)
            try:
                start = max(1, int(sub[0].strip()))
                end = min(max_pages, int(sub[1].strip()))
                for p in range(start, end + 1):
                    pages.add(p - 1)
            except ValueError:
                continue
        else:
            try:
                p = int(part)
                if 1 <= p <= max_pages:
                    pages.add(p - 1)
            except ValueError:
                continue
    return sorted(list(pages))


def split_pdf_file(input_path: str, mode: str = "range", ranges: str = "1", base_name: str = "document") -> tuple[str, bool, str]:
    """
    Split PDF into pages.
    Returns: (output_path, is_zip, output_filename)
    """
    try:
        doc = pymupdf.open(input_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {str(e)}")

    total_pages = doc.page_count
    if total_pages < 1:
        doc.close()
        raise HTTPException(status_code=400, detail="PDF has no pages to split.")

    safe_base = sanitize_filename(base_name)

    if mode == "all":
        # Extract every page into a ZIP archive
        out_zip_path = create_temp_output_path(prefix="hs_split_all_", suffix=".zip")
        with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(total_pages):
                single_doc = pymupdf.open()
                single_doc.insert_pdf(doc, from_page=i, to_page=i)
                pdf_bytes = single_doc.tobytes()
                single_doc.close()
                zf.writestr(f"{safe_base}_page_{i+1:03d}.pdf", pdf_bytes)
        doc.close()
        return out_zip_path, True, f"{safe_base}_pages.zip"

    # Specific page ranges
    selected_indices = parse_page_ranges(ranges, total_pages)
    if not selected_indices:
        selected_indices = [0]

    out_doc = pymupdf.open()
    for idx in selected_indices:
        out_doc.insert_pdf(doc, from_page=idx, to_page=idx)

    out_pdf_path = create_temp_output_path(prefix="hs_split_", suffix=".pdf")
    out_doc.save(out_pdf_path, garbage=3, deflate=True)
    out_doc.close()
    doc.close()

    return out_pdf_path, False, f"{safe_base}_split.pdf"
