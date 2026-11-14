"""
HimShiksha API - Image Tools Endpoints
All image tools support up to 2 GB (2,147,483,648 bytes) with disk-based streaming.
"""

import os
import json
import zipfile
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, Header, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from utils.security import verify_api_key, sanitize_filename, make_content_disposition
from utils.file_validation import LIMIT_2GB_BYTES
from utils.upload_handler import save_upload_to_disk, create_temp_output_path
from utils.cleanup import remove_file_silent
from services.image_service import convert_image_format, compress_image_to_target
from image_engine import ImageEngine

image_engine_instance = ImageEngine()
router = APIRouter(prefix="/api/convert", tags=["Image Tools"])


@router.post("/image-format")
async def api_image_format(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_format: str = Form("png"),
    quality: int = Form(90),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".img")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path, mime, ext = convert_image_format(in_path, target_format=target_format, quality=quality)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "image")[0])
    return FileResponse(
        out_path,
        media_type=mime,
        headers={"Content-Disposition": make_content_disposition(f"{base}{ext}")}
    )


@router.post("/image-compress")
async def api_image_compress(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_kb: int = Form(200),
    max_width: int = Form(2000),
    max_height: int = Form(2000),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".img")
    background_tasks.add_task(remove_file_silent, in_path)

    out_path, stats = compress_image_to_target(in_path, target_kb=target_kb, max_width=max_width, max_height=max_height)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "image")[0])
    headers = {
        "Content-Disposition": make_content_disposition(f"{base}_compressed.jpg"),
        "X-Original-Bytes": str(stats["original_bytes"]),
        "X-Compressed-Bytes": str(stats["compressed_bytes"]),
        "X-Savings-Percent": str(stats["savings_percent"]),
        "Access-Control-Expose-Headers": "X-Original-Bytes, X-Compressed-Bytes, X-Savings-Percent"
    }
    return FileResponse(out_path, media_type="image/jpeg", headers=headers)


@router.post("/image-editor")
async def api_image_editor(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    operations: str = Form(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    in_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix=".img")
    background_tasks.add_task(remove_file_silent, in_path)

    try:
        with open(in_path, "rb") as f:
            raw_bytes = f.read()
        ops = json.loads(operations)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid operations JSON: {str(e)}")

    crop_box = tuple(ops["crop"]) if ops.get("crop") else None
    resize_dims = tuple(ops["resize"]) if ops.get("resize") else None

    out_bytes, mime, meta = image_engine_instance.edit_image(
        image_bytes=raw_bytes,
        crop_box=crop_box,
        resize_dims=resize_dims,
        rotate_angle=float(ops.get("rotate", 0.0)),
        flip_h=bool(ops.get("flip_h", False)),
        flip_v=bool(ops.get("flip_v", False)),
        quality=int(ops.get("quality", 90)),
        target_format=str(ops.get("format", "jpeg"))
    )

    out_path = create_temp_output_path(prefix="hs_img_edited_", suffix=f".{meta.get('format', 'jpg').lower()}")
    with open(out_path, "wb") as f_out:
        f_out.write(out_bytes)
    background_tasks.add_task(remove_file_silent, out_path)

    base = sanitize_filename(os.path.splitext(file.filename or "image")[0])
    return FileResponse(
        out_path,
        media_type=mime,
        headers={"Content-Disposition": make_content_disposition(f"{base}_edited.{meta.get('format', 'jpg').lower()}")}
    )


@router.post("/batch-images")
async def api_batch_images(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    target_format: str = Form("png"),
    quality: int = Form(90),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded for batch conversion.")

    out_zip = create_temp_output_path(prefix="hs_batch_images_", suffix=".zip")
    background_tasks.add_task(remove_file_silent, out_zip)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, f in enumerate(files):
            tmp_in = await save_upload_to_disk(f, max_bytes=LIMIT_2GB_BYTES, suffix=".img")
            try:
                tmp_out, _, ext = convert_image_format(tmp_in, target_format=target_format, quality=quality)
                with open(tmp_out, "rb") as f_img:
                    base = sanitize_filename(os.path.splitext(f.filename or f"img_{idx}")[0])
                    zf.writestr(f"{base}{ext}", f_img.read())
                remove_file_silent(tmp_out)
            finally:
                remove_file_silent(tmp_in)

    return FileResponse(
        out_zip,
        media_type="application/zip",
        headers={"Content-Disposition": make_content_disposition("converted_images.zip")}
    )
