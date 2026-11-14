"""
HimShiksha API - PDF Merge Service
Merges multiple PDF documents into a single sequential PDF.
Supports batch totals up to 2GB via disk-based PyMuPDF.
"""

import os
import pymupdf
from fastapi import HTTPException
from utils.upload_handler import create_temp_output_path


def merge_pdf_files(input_paths: list[str]) -> str:
    """Merge a list of PDF file paths in order into a single unified PDF."""
    if not input_paths:
        raise HTTPException(status_code=400, detail="No PDF files provided for merge.")

    merged_doc = pymupdf.open()
    total_pages = 0

    try:
        for idx, path in enumerate(input_paths):
            try:
                sub_doc = pymupdf.open(path)
                if sub_doc.is_encrypted:
                    sub_doc.close()
                    raise HTTPException(
                        status_code=400,
                        detail=f"File #{idx+1} is password-protected. Please unlock it before merging."
                    )
                merged_doc.insert_pdf(sub_doc)
                total_pages += sub_doc.page_count
                sub_doc.close()
            except Exception as e:
                if isinstance(e, HTTPException):
                    raise e
                raise HTTPException(status_code=400, detail=f"Corrupted or invalid PDF #{idx+1}: {str(e)}")

        if total_pages == 0:
            raise HTTPException(status_code=400, detail="No valid pages found across the selected PDF files.")

        out_path = create_temp_output_path(prefix="hs_merged_", suffix=".pdf")
        merged_doc.save(out_path, garbage=3, deflate=True)
        return out_path
    finally:
        merged_doc.close()
