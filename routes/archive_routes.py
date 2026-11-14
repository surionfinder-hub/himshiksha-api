"""
HimShiksha API - Archive & Multi-File Packaging Endpoints
Supports up to 2 GB (2,147,483,648 bytes) with ZIP bomb protection.
"""

import os
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, Header, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from utils.security import verify_api_key, sanitize_filename, make_content_disposition
from utils.file_validation import LIMIT_2GB_BYTES
from utils.upload_handler import save_upload_to_disk
from utils.cleanup import remove_file_silent
from services.archive_service import pdf_to_images_zip, images_to_pdf_file

router = APIRouter(prefix="/api/convert", tags=["Archive & Packaging"])


@router.post("/pdf-to-images")
async def api_pdf_to_images(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    img_format: str = Form("png"),
    dpi: int = Form(150),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    base = sanitize_filename(os.path.splitext(file.filename or "page")[0])
    out_zip = pdf_to_images_zip(in_path, img_format=img_format, dpi=dpi, base_name=base)
    background_tasks.add_task(remove_file_silent, out_zip)

    return FileResponse(
        out_zip,
        media_type="application/zip",
        headers={"Content-Disposition": make_content_disposition(f"{base}_images.zip")}
    )


@router.post("/images-to-pdf")
@router.post("/multi-image-to-pdf")
async def api_images_to_pdf(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided.")

    saved_paths = []
    for f in files:
        p = await save_upload_to_disk(f, max_bytes=LIMIT_2GB_BYTES, suffix=".img")
        saved_paths.append(p)
        background_tasks.add_task(remove_file_silent, p)

    out_pdf = images_to_pdf_file(saved_paths)
    background_tasks.add_task(remove_file_silent, out_pdf)

    return FileResponse(
        out_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition("converted_images.pdf")}
    )
