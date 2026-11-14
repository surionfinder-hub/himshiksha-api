"""
FastAPI Routes for HimShiksha AI Studio Pro:
Bulk Background Remover & Product Photo Enhancer
"""

import io
import json
import zipfile
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import Response, StreamingResponse
from services.studio_service import process_studio_image
import fitz  # PyMuPDF for PDF page extraction

router = APIRouter(prefix="/api/studio", tags=["AI Studio Pro"])

@router.post("/enhance-single")
async def enhance_single_image(
    file: UploadFile = File(...),
    options: Optional[str] = Form("{}")
):
    """
    Processes a single image through the complete studio pipeline:
    removes background, auto-centers, adds ground shadow, and boosts studio lighting.
    """
    try:
        opts = json.loads(options) if options else {}
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        output_bytes = process_studio_image(contents, opts)
        output_format = opts.get("output_format", "PNG").upper()
        media_type = "image/jpeg" if output_format in ("JPG", "JPEG") else "image/png"

        return Response(content=output_bytes, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Studio enhancement error: {str(e)}")


@router.post("/enhance-bulk")
async def enhance_bulk_images(
    files: List[UploadFile] = File(...),
    options: Optional[str] = Form("{}")
):
    """
    Processes multiple images (or directly extracted from ZIP/PDF),
    sequential one-by-one execution to guarantee zero server crash,
    and returns a clean ZIP bundle containing all enhanced studio photos.
    """
    try:
        opts = json.loads(options) if options else {}
        output_format = opts.get("output_format", "PNG").lower()
        processed_files = []

        for upload_file in files:
            filename = upload_file.filename or "photo"
            content = await upload_file.read()
            if not content:
                continue

            # Check if uploaded file is a ZIP archive
            if filename.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                        for entry in zf.namelist():
                            if entry.startswith("__MACOSX") or entry.startswith("."):
                                continue
                            if entry.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                                item_bytes = zf.read(entry)
                                clean_name = entry.rsplit(".", 1)[0].split("/")[-1]
                                out_img = process_studio_image(item_bytes, opts)
                                processed_files.append((f"{clean_name}_studio.{output_format}", out_img))
                except Exception as zip_err:
                    print(f"ZIP unpack error: {zip_err}")

            # Check if uploaded file is a PDF
            elif filename.lower().endswith(".pdf"):
                try:
                    doc = fitz.open(stream=content, filetype="pdf")
                    base_name = filename.rsplit(".", 1)[0]
                    for page_idx in range(len(doc)):
                        page = doc[page_idx]
                        pix = page.get_pixmap(dpi=150)
                        item_bytes = pix.tobytes("png")
                        out_img = process_studio_image(item_bytes, opts)
                        processed_files.append((f"{base_name}_page_{page_idx + 1}_studio.{output_format}", out_img))
                except Exception as pdf_err:
                    print(f"PDF extract error: {pdf_err}")

            # Standard Image
            else:
                clean_name = filename.rsplit(".", 1)[0] if "." in filename else filename
                try:
                    out_img = process_studio_image(content, opts)
                    processed_files.append((f"{clean_name}_studio.{output_format}", out_img))
                except Exception as img_err:
                    print(f"Error processing image {filename}: {img_err}")

        if not processed_files:
            raise HTTPException(status_code=400, detail="No valid images could be processed from uploads.")

        # Bundle all into a ZIP archive
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out_zip:
            for arc_name, data in processed_files:
                out_zip.writestr(arc_name, data)

        zip_buf.seek(0)
        return Response(
            content=zip_buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=himshiksha_studio_enhanced_photos.zip"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk studio processing error: {str(e)}")
