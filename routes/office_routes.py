"""
HimShiksha API - Office & Spreadsheets Endpoints
Handles DOCX, XLSX, and CSV documents with formatting and Hindi Unicode support.
Preserves 20 MB category limit for office documents.
"""

import os
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Header, HTTPException
from fastapi.responses import Response

from utils.security import verify_api_key, sanitize_filename, make_content_disposition
from utils.file_validation import LIMIT_20MB_BYTES, validate_file_size
from services.office_service import (
    convert_docx_to_pdf_bytes,
    extract_docx_to_txt_str,
    convert_xlsx_to_pdf_bytes,
    convert_xlsx_to_csv_str,
    convert_csv_to_xlsx_bytes
)

router = APIRouter(prefix="/api/convert", tags=["Office & Documents"])


@router.post("/docx-to-pdf")
async def api_docx_to_pdf(
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    content = await file.read()
    validate_file_size(len(content), category="office")

    pdf_bytes = convert_docx_to_pdf_bytes(content)
    base = sanitize_filename(os.path.splitext(file.filename or "document")[0])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}.pdf")}
    )


@router.post("/docx-to-txt")
async def api_docx_to_txt(
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    content = await file.read()
    validate_file_size(len(content), category="office")

    txt_content = extract_docx_to_txt_str(content)
    base = sanitize_filename(os.path.splitext(file.filename or "document")[0])
    return Response(
        content=txt_content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": make_content_disposition(f"{base}.txt")}
    )


@router.post("/xlsx-to-pdf")
async def api_xlsx_to_pdf(
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    content = await file.read()
    validate_file_size(len(content), category="office")

    pdf_bytes = convert_xlsx_to_pdf_bytes(content)
    base = sanitize_filename(os.path.splitext(file.filename or "spreadsheet")[0])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}.pdf")}
    )


@router.post("/xlsx-to-csv")
async def api_xlsx_to_csv(
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    content = await file.read()
    validate_file_size(len(content), category="office")

    csv_text = convert_xlsx_to_csv_str(content)
    base = sanitize_filename(os.path.splitext(file.filename or "spreadsheet")[0])
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": make_content_disposition(f"{base}.csv")}
    )


@router.post("/csv-to-xlsx")
async def api_csv_to_xlsx(
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    content = await file.read()
    validate_file_size(len(content), category="office")

    xlsx_bytes = convert_csv_to_xlsx_bytes(content.decode("utf-8", errors="replace"))
    base = sanitize_filename(os.path.splitext(file.filename or "data")[0])
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": make_content_disposition(f"{base}.xlsx")}
    )
