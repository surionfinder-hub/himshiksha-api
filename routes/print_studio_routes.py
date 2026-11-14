"""
HimShiksha API - Print Studio Imposition & Duplex Endpoints
Supports up to 2 GB with booklet binding, N-Up, and manual duplex prep.
"""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import Response

from utils.security import verify_api_key
from utils.file_validation import LIMIT_2GB_BYTES
from utils.upload_handler import save_upload_to_disk
from utils.cleanup import remove_file_silent
from print_studio_engine import PrintStudioServerEngine

router = APIRouter(prefix="/api/convert", tags=["Print Studio"])


@router.post("/print-studio")
async def print_studio_endpoint(
    file: UploadFile = File(...),
    paper_size: str = Form("a4"),
    orientation: str = Form("portrait"),
    nup: int = Form(1),
    booklet: bool = Form(False),
    booklet_binding: str = Form("left"),
    duplex_mode: str = Form("simplex"),
    duplex_part: str = Form("all"),
    color_mode: str = Form("color"),
    watermark_text: Optional[str] = Form(None),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    spooled_path = await save_upload_to_disk(file, max_bytes=LIMIT_2GB_BYTES, suffix="_print_studio.pdf")

    try:
        with open(spooled_path, "rb") as f:
            pdf_bytes = f.read()

        out_bytes = PrintStudioServerEngine.process_print_job(
            input_pdf_bytes=pdf_bytes,
            paper_size=paper_size,
            orientation=orientation,
            nup=nup,
            booklet=booklet,
            booklet_binding=booklet_binding,
            duplex_mode=duplex_mode,
            duplex_part=duplex_part,
            color_mode=color_mode,
            watermark_text=watermark_text
        )
        return Response(
            content=out_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="print_studio_output.pdf"'}
        )
    finally:
        remove_file_silent(spooled_path)
