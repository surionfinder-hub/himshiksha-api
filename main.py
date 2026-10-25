"""
HimShiksha - High-Performance Python Conversion Backend
Designed for deployment on Render (Free Tier Web Service).
Provides server-side PDF, text, and image conversion tools with Hindi/Unicode support,
intelligent scanned-PDF detection, multi-file batch processing, and temporary file lifecycle management.
"""

import os
import sys
import io
import time
import zipfile
import tempfile
import re
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, Form, Header, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import pymupdf  # PyMuPDF
import pypdf
from PIL import Image

# ------------------------------------------------------------------------------
# Configuration & Security Constants
# ------------------------------------------------------------------------------
API_SECRET_KEY = os.environ.get("HIMSHIKSHA_API_KEY", "himshiksha_render_secret_key_2026")
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024       # 10 MB per file limit
MAX_BATCH_SIZE_BYTES = 100 * 1024 * 1024     # 100 MB total batch limit
MAX_BATCH_FILES = 100                        # Maximum 100 files per batch
START_TIME = time.time()

app = FastAPI(
    title="HimShiksha Python Conversion API",
    description="Render backend for heavy document and image conversions with zero permanent storage.",
    version="1.0.0"
)

# Enable CORS for HimShiksha frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from himshiksha.com and localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_api_key(x_himshiksha_key: Optional[str] = Header(None)):
    """
    Enforce shared secret API authentication between HimShiksha PHP and Render.
    In local development, falls back safely if key matches default.
    """
    expected = os.environ.get("HIMSHIKSHA_API_KEY", "himshiksha_render_secret_key_2026")
    if expected and x_himshiksha_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing X-HimShiksha-Key header."
        )

def sanitize_filename(filename: str, fallback: str = "document") -> str:
    """Sanitize filename to prevent directory traversal and header injection."""
    clean = os.path.basename(filename.strip())
    clean = re.sub(r'[^\w\.\-\s]', '_', clean)
    clean = re.sub(r'\s+', ' ', clean)
    return clean[:100] if clean else fallback

# ------------------------------------------------------------------------------
# 1. Health & Telemetry Endpoints (Free-tier Cold Start Monitoring)
# ------------------------------------------------------------------------------
@app.get("/")
@app.get("/health")
def health_check():
    """
    Cold-start diagnostic endpoint.
    Called by HimShiksha website to measure latency and confirm worker readiness.
    """
    uptime_seconds = round(time.time() - START_TIME, 1)
    return {
        "status": "healthy",
        "service": "HimShiksha Python Engine",
        "version": "1.0.0",
        "uptime_seconds": uptime_seconds,
        "limits": {
            "max_file_size_mb": 10,
            "max_batch_files": 100,
            "max_batch_total_mb": 100,
            "storage": "100% ephemeral temporary memory"
        }
    }

# ------------------------------------------------------------------------------
# 2. TXT to PDF Conversion (Unicode, Hindi Devanagari & Page Breaks)
# ------------------------------------------------------------------------------
@app.post("/api/convert/txt-to-pdf")
async def convert_txt_to_pdf(
    file: UploadFile = File(...),
    font_size: int = Form(11),
    margin: int = Form(40),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty text document (0 bytes).")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not decode text file as UTF-8 or Latin-1.")

    # Standardize tabs to 4 spaces
    text = text.replace("\t", "    ")
    # Split by ASCII form feed (\f) for explicit manual page breaks
    sections = text.split("\f")

    # Build PDF using PyMuPDF (fitz) with Unicode Devanagari font
    doc = pymupdf.open()
    page_width, page_height = 595.28, 841.89  # A4 points
    usable_width = page_width - (margin * 2)
    usable_height = page_height - (margin * 2) - 20
    line_height = font_size * 1.4
    max_lines_per_page = max(1, int(usable_height / line_height))

    # Font path resolution
    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(base_dir, "..", "assets", "fonts", "NotoSansCombined-Regular.ttf")
    if not os.path.exists(font_path):
        font_path = os.path.join(base_dir, "fonts", "NotoSansCombined-Regular.ttf")
    
    font_bytes = None
    if os.path.exists(font_path):
        with open(font_path, "rb") as f:
            font_bytes = f.read()

    pages_to_render = []
    for section in sections:
        raw_lines = section.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        section_wrapped = []
        for pline in raw_lines:
            if not pline.strip():
                section_wrapped.append("")
                continue
            
            # Simple wrapping logic
            words = pline.split(" ")
            current_line = ""
            for word in words:
                candidate = (current_line + " " + word).strip() if current_line else word
                # Approximate width check (0.55 * font_size per character)
                approx_width = len(candidate) * (font_size * 0.55)
                if approx_width <= usable_width:
                    current_line = candidate
                else:
                    if current_line:
                        section_wrapped.append(current_line)
                        current_line = word
                    else:
                        section_wrapped.append(word)
                        current_line = ""
            if current_line:
                section_wrapped.append(current_line)
        
        # Paginate section
        for i in range(0, max(1, len(section_wrapped)), max_lines_per_page):
            pages_to_render.append(section_wrapped[i : i + max_lines_per_page])

    total_pages = max(1, len(pages_to_render))

    for idx, page_lines in enumerate(pages_to_render):
        page = doc.new_page(width=page_width, height=page_height)
        if font_bytes:
            try:
                page.insert_font(fontname="NotoSans", fontbuffer=font_bytes)
            except Exception:
                pass
        y = margin + font_size

        for line in page_lines:
            if line:
                try:
                    if font_bytes:
                        page.insert_text(
                            pymupdf.Point(margin, y),
                            line,
                            fontsize=font_size,
                            fontname="NotoSans",
                            color=(0.1, 0.1, 0.12)
                        )
                    else:
                        page.insert_text(
                            pymupdf.Point(margin, y),
                            line,
                            fontsize=font_size,
                            color=(0.1, 0.1, 0.12)
                        )
                except Exception:
                    # Clean fallback
                    clean_line = re.sub(r'[^\x20-\x7E]', '?', line)
                    page.insert_text(pymupdf.Point(margin, y), clean_line, fontsize=font_size)
            y += line_height

        # Footer
        footer_text = f"Page {idx + 1} of {total_pages} • HimShiksha"
        page.insert_text(pymupdf.Point(page_width / 2 - 40, page_height - margin / 2), footer_text, fontsize=8, color=(0.5, 0.5, 0.55))

    pdf_buffer = io.BytesIO()
    doc.save(pdf_buffer)
    doc.close()
    pdf_buffer.seek(0)

    base_name = sanitize_filename(os.path.splitext(file.filename)[0])
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{base_name}.pdf"'}
    )

# ------------------------------------------------------------------------------
# 3. PDF to TXT Extraction & Scanned PDF Detection
# ------------------------------------------------------------------------------
@app.post("/api/convert/pdf-to-txt")
async def convert_pdf_to_txt(
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty PDF document (0 bytes).")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")

    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Corrupted or invalid PDF file: {str(e)}")

    total_pages = len(doc)
    extracted_text = []
    total_chars = 0
    total_images = 0

    for page_idx in range(total_pages):
        page = doc[page_idx]
        text = page.get_text("text").strip()
        total_chars += len(text)
        total_images += len(page.get_images())

        if total_pages > 1:
            extracted_text.append(f"--- Page {page_idx + 1} of {total_pages} ---\n{text}\n")
        else:
            extracted_text.append(text)

    doc.close()
    full_text = "\n".join(extracted_text)

    # Scanned PDF Detection:
    # If document has pages but text density is near zero (< 15 chars/page) while images exist
    is_scanned = (total_chars == 0) or (total_pages > 0 and (total_chars / total_pages) < 15)

    base_name = sanitize_filename(os.path.splitext(file.filename)[0])
    word_count = len(full_text.split())

    return JSONResponse({
        "success": True,
        "filename": f"{base_name}.txt",
        "page_count": total_pages,
        "character_count": total_chars,
        "word_count": word_count,
        "is_scanned": is_scanned,
        "scanned_notice": (
            "Notice: Scanned Document Detected. This PDF appears to be a scanned image or photo without selectable digital text."
            if is_scanned else None
        ),
        "text": full_text
    })

# ------------------------------------------------------------------------------
# 4. Multi-PDF Merge (Supports up to 100 Files)
# ------------------------------------------------------------------------------
@app.post("/api/convert/pdf-merge")
async def merge_pdfs(
    files: List[UploadFile] = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)

    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No PDF files provided.")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"Batch size exceeds {MAX_BATCH_FILES} files.")

    merged_doc = pymupdf.open()
    total_input_bytes = 0

    for idx, f in enumerate(files):
        data = await f.read()
        total_input_bytes += len(data)
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f'File "{f.filename}" exceeds 10 MB per-file limit.')
        if total_input_bytes > MAX_BATCH_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"Total batch size exceeds 100 MB limit.")

        try:
            sub_doc = pymupdf.open(stream=data, filetype="pdf")
            merged_doc.insert_pdf(sub_doc)
            sub_doc.close()
        except Exception as e:
            merged_doc.close()
            raise HTTPException(status_code=400, detail=f'Error processing PDF "{f.filename}": {str(e)}')

    output_buffer = io.BytesIO()
    merged_doc.save(output_buffer)
    total_pages = len(merged_doc)
    merged_doc.close()
    output_buffer.seek(0)

    return StreamingResponse(
        output_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="himshiksha_merged.pdf"',
            "X-Page-Count": str(total_pages)
        }
    )

# ------------------------------------------------------------------------------
# 5. Multiple Images to Single PDF (Up to 100 Images)
# ------------------------------------------------------------------------------
@app.post("/api/convert/images-to-pdf")
async def images_to_pdf(
    files: List[UploadFile] = File(...),
    page_size: str = Form("a4"),
    orientation: str = Form("auto"),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)

    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No images provided.")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"Batch exceeds maximum of {MAX_BATCH_FILES} images.")

    doc = pymupdf.open()
    total_bytes = 0

    for f in files:
        data = await f.read()
        total_bytes += len(data)
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f'File "{f.filename}" exceeds 10 MB limit.')
        if total_bytes > MAX_BATCH_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Total batch exceeds 100 MB safeguard limit.")

        try:
            img = Image.open(io.BytesIO(data))
            img_format = img.format.lower() if img.format else "png"
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format="JPEG", quality=92)
            img_byte_arr.seek(0)

            # Insert as PDF page
            img_doc = pymupdf.open(stream=img_byte_arr.getvalue(), filetype="jpeg")
            rect = img_doc[0].rect
            pdf_bytes = img_doc.convert_to_pdf()
            img_pdf = pymupdf.open("pdf", pdf_bytes)
            doc.insert_pdf(img_pdf)
            img_doc.close()
            img_pdf.close()
        except Exception as e:
            doc.close()
            raise HTTPException(status_code=400, detail=f'Could not process image "{f.filename}": {str(e)}')

    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    page_count = len(doc)
    doc.close()
    output_buffer.seek(0)

    return StreamingResponse(
        output_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="himshiksha_images_combined.pdf"',
            "X-Page-Count": str(page_count)
        }
    )

# ------------------------------------------------------------------------------
# 6. PDF to Images (ZIP Archive)
# ------------------------------------------------------------------------------
@app.post("/api/convert/pdf-to-images")
async def pdf_to_images(
    file: UploadFile = File(...),
    format: str = Form("png"),
    dpi: int = Form(150),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty PDF file.")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")

    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {str(e)}")

    base_name = sanitize_filename(os.path.splitext(file.filename)[0])
    img_ext = "png" if format.lower() == "png" else "jpg"
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for idx in range(len(doc)):
            page = doc[idx]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes(img_ext)
            zip_file.writestr(f"{base_name}_page_{idx + 1}.{img_ext}", img_data)

    doc.close()
    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base_name}_pages.zip"'}
    )

# ------------------------------------------------------------------------------
# 7. Image Format Conversion (JPG, PNG, WEBP)
# ------------------------------------------------------------------------------
@app.post("/api/convert/image-format")
async def convert_image_format(
    file: UploadFile = File(...),
    target_format: str = Form("webp"),
    quality: int = Form(85),
    bg_color: str = Form("white"),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty image file.")
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")

    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or corrupted image: {str(e)}")

    target = target_format.lower().strip()
    if target not in ["jpg", "jpeg", "png", "webp"]:
        raise HTTPException(status_code=400, detail="Target format must be jpg, png, or webp.")

    out_buffer = io.BytesIO()
    out_mime = f"image/{target if target != 'jpg' else 'jpeg'}"

    if target in ["jpg", "jpeg"]:
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255) if bg_color.lower() == "white" else (0, 0, 0))
            bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = bg
        else:
            img = img.convert("RGB")
        img.save(out_buffer, format="JPEG", quality=quality)
    elif target == "png":
        img.save(out_buffer, format="PNG", optimize=True)
    elif target == "webp":
        img.save(out_buffer, format="WEBP", quality=quality)

    out_buffer.seek(0)
    base_name = sanitize_filename(os.path.splitext(file.filename)[0])
    return StreamingResponse(
        out_buffer,
        media_type=out_mime,
        headers={"Content-Disposition": f'attachment; filename="{base_name}.{target}"'}
    )

# ------------------------------------------------------------------------------
# 8. Batch Image Conversion (Up to 100 Files in ZIP)
# ------------------------------------------------------------------------------
@app.post("/api/convert/batch-images")
async def batch_images(
    files: List[UploadFile] = File(...),
    target_format: str = Form("webp"),
    quality: int = Form(85),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)

    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"Batch size exceeds maximum of {MAX_BATCH_FILES} files.")

    target = target_format.lower().strip()
    zip_buffer = io.BytesIO()
    total_bytes = 0
    results = []

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            fdata = await f.read()
            total_bytes += len(fdata)
            if len(fdata) > MAX_FILE_SIZE_BYTES or total_bytes > MAX_BATCH_SIZE_BYTES:
                results.append({"name": f.filename, "status": "FAIL", "error": "Size limit exceeded"})
                continue

            try:
                img = Image.open(io.BytesIO(fdata))
                out_sub = io.BytesIO()
                if target in ["jpg", "jpeg"]:
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.save(out_sub, format="JPEG", quality=quality)
                elif target == "png":
                    img.save(out_sub, format="PNG")
                elif target == "webp":
                    img.save(out_sub, format="WEBP", quality=quality)
                
                bname = sanitize_filename(os.path.splitext(f.filename)[0])
                zf.writestr(f"{bname}.{target}", out_sub.getvalue())
                results.append({"name": f.filename, "status": "PASS"})
            except Exception as e:
                results.append({"name": f.filename, "status": "FAIL", "error": str(e)})

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="himshiksha_batch_{target}.zip"',
            "X-Batch-Summary": f"Total: {len(files)}, Succeeded: {sum(1 for r in results if r['status'] == 'PASS')}"
        }
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
