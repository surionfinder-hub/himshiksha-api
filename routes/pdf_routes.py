"""
HimShiksha API - PDF Tools Endpoints
All PDF tools support up to 2 GB (2,147,483,648 bytes) with disk-based streaming and low memory footprint.
"""

import os
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, Header, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from utils.security import verify_api_key, sanitize_filename, make_content_disposition
from utils.file_validation import LIMIT_2GB_BYTES
from utils.upload_handler import save_upload_to_disk
from utils.cleanup import remove_file_silent

from services.pdf_password_service import protect_pdf_file, unlock_pdf_file
from services.pdf_compressor_service import compress_pdf_disk
from services.pdf_split_service import split_pdf_file
from services.pdf_merge_service import merge_pdf_files
from services.pdf_numbering_service import add_page_numbers_to_pdf
from services.pdf_editor_service import (
    rotate_pdf_file,
    watermark_pdf_file,
    apply_pdf_color_effects_file,
    edit_pdf_pages_file,
    txt_to_pdf_file,
    pdf_to_txt_file
)

router = APIRouter(prefix="/api/convert", tags=["PDF Tools"])


# 1. PDF Password Protection (AES-256)
@router.post("/pdf-protect")
async def api_protect_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    password: str = Form(...),
    confirm_password: Optional[str] = Form(None),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = protect_pdf_file(in_path, password, confirm_password)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}_protected.pdf")}
    )


# 2. PDF Password Unlock
@router.post("/pdf-unlock")
async def api_unlock_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    password: str = Form(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = unlock_pdf_file(in_path, password)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}_unlocked.pdf")}
    )


# 3. PDF Compression
@router.post("/pdf-compress")
async def api_compress_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    preset: str = Form("balanced"),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path, stats = compress_pdf_disk(in_path, preset)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    headers = {
        "Content-Disposition": make_content_disposition(f"{base}_compressed.pdf"),
        "X-Original-Bytes": str(stats["original_bytes"]),
        "X-Compressed-Bytes": str(stats["compressed_bytes"]),
        "X-Savings-Percent": str(stats["savings_percent"]),
        "X-Is-Reduced": "true" if stats["is_reduced"] else "false",
        "X-Engine": stats["engine"],
        "Access-Control-Expose-Headers": "X-Original-Bytes, X-Compressed-Bytes, X-Savings-Percent, X-Is-Reduced, X-Engine"
    }
    return FileResponse(out_path, media_type="application/pdf", headers=headers)


# 4. PDF Split
@router.post("/pdf-split")
async def api_split_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form("range"),
    ranges: str = Form("1"),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    out_path, is_zip, out_name = split_pdf_file(in_path, mode, ranges, base)
    background_tasks.add_task(remove_file_silent, out_path)

    mime = "application/zip" if is_zip else "application/pdf"
    return FileResponse(
        out_path,
        media_type=mime,
        headers={"Content-Disposition": make_content_disposition(out_name)}
    )


# 5. PDF Merge
@router.post("/pdf-merge")
async def api_merge_pdf(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for merging.")

    saved_paths = []
    for f in files:
        p = await save_upload_to_disk(f, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
        saved_paths.append(p)
        background_tasks.add_task(remove_file_silent, p)

    out_path = merge_pdf_files(saved_paths)
    background_tasks.add_task(remove_file_silent, out_path)

    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition("merged_document.pdf")}
    )


# 6. PDF Page Numbering
@router.post("/pdf-page-number")
async def api_number_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    format: str = Form("page_of_total"),
    start_number: int = Form(1),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = add_page_numbers_to_pdf(in_path, position=position, format_type=format, start_number=start_number)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}_numbered.pdf")}
    )


# 7. PDF Rotation
@router.post("/pdf-rotate")
async def api_rotate_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    angle: int = Form(90),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = rotate_pdf_file(in_path, angle)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}_rotated.pdf")}
    )


# 8. PDF Watermark
@router.post("/pdf-watermark")
async def api_watermark_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    text: str = Form("CONFIDENTIAL"),
    opacity: float = Form(0.3),
    rotation: float = Form(45.0),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = watermark_pdf_file(in_path, text=text, opacity=opacity, rotation=rotation)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}_watermarked.pdf")}
    )


# 9. PDF Color Effects
@router.post("/pdf-color-effects")
async def api_color_effects_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    preset: str = Form("grayscale"),
    intensity: float = Form(1.0),
    dpi: int = Form(150),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = apply_pdf_color_effects_file(in_path, preset=preset, intensity=intensity, dpi=dpi)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}_{preset}.pdf")}
    )


# 10. PDF Page Editor
@router.post("/pdf-page-editor")
async def api_page_editor_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    page_operations: str = Form(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = edit_pdf_pages_file(in_path, page_operations)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "doc")[0])
    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}_edited.pdf")}
    )


# 11. TXT to PDF
@router.post("/txt-to-pdf")
async def api_txt_to_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".txt")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = txt_to_pdf_file(in_path)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "document")[0])
    return FileResponse(
        out_path,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition(f"{base}.pdf")}
    )


# 12. PDF to TXT
@router.post("/pdf-to-txt")
async def api_pdf_to_txt(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".pdf")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path = pdf_to_txt_file(in_path)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "document")[0])
    return FileResponse(
        out_path,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": make_content_disposition(f"{base}.txt")}
    )
