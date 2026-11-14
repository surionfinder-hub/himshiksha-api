"""
HimShiksha API - Modular QR Processing Router
Registered under prefix `/api/qr`.
Endpoints:
- POST /api/qr/generate: Server-side QR generation with custom colors, embedded logo, and high-res export (PNG, JPG, SVG).
- POST /api/qr/batch: Process CSV or list of QR items, generate individual QR files, assemble into a clean ZIP archive with manifest.
- POST /api/qr/scan-test: Decode an uploaded QR image using OpenCV cv2.QRCodeDetector() and verify payload against expected text.
- POST /api/qr/print-sheet: Generate a high-resolution print-ready PDF (A4/Letter, portrait/landscape, custom grid rows x cols, margins, labels) using ReportLab.
"""

import io
import json
import base64
from typing import Optional, List
from fastapi import APIRouter, Request, UploadFile, File, Form, Header, HTTPException, Response

from utils.security import verify_api_key, sanitize_filename, make_content_disposition
from schemas.qr_schemas import (
    QRGenerateRequest,
    QRBatchRequest,
    QRBatchItem,
    QRScanTestResponse,
    QRPrintSheetRequest,
    QRPrintSheetItem
)
from services.qr_generation_service import generate_qr_bytes
from services.qr_batch_service import parse_csv_items, process_qr_batch
from services.qr_scan_test_service import scan_and_verify_qr
from services.qr_print_service import generate_print_sheet_pdf

router = APIRouter(prefix="/api/qr", tags=["QR Studio"])


# ==============================================================================
# 1. POST /api/qr/generate
# ==============================================================================
@router.post("/generate")
async def api_qr_generate(
    request: Request,
    content: Optional[str] = Form(None),
    error_correction: str = Form("M"),
    box_size: int = Form(10),
    border: int = Form(4),
    fill_color: str = Form("#000000"),
    back_color: str = Form("#ffffff"),
    format: str = Form("png"),
    size_px: Optional[int] = Form(None),
    logo_size_ratio: float = Form(0.22),
    badge_radius: int = Form(12),
    logo: Optional[UploadFile] = File(None),
    x_himshiksha_key: Optional[str] = Header(None)
):
    """
    Generate a customized, high-resolution QR code (PNG, JPG, SVG, WebP).
    Supports multipart form data with file uploads or JSON payloads.
    """
    verify_api_key(x_himshiksha_key)

    logo_bytes: Optional[bytes] = None

    # Handle JSON payload if Content-Type is application/json
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            model = QRGenerateRequest(**body)
            content = model.content
            error_correction = model.error_correction
            box_size = model.box_size
            border = model.border
            fill_color = model.fill_color
            back_color = model.back_color
            format = model.format
            size_px = model.size_px
            logo_size_ratio = model.logo_size_ratio
            badge_radius = model.badge_radius

            if model.logo_base64:
                # Strip data URL prefix if present
                b64_data = model.logo_base64
                if "," in b64_data:
                    b64_data = b64_data.split(",", 1)[1]
                logo_bytes = base64.b64decode(b64_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON request body: {str(e)}")
    else:
        # Multipart form processing
        if not content:
            raise HTTPException(status_code=400, detail="The 'content' field is required for QR code generation.")

        if logo and logo.filename:
            logo_bytes = await logo.read()

    try:
        out_bytes, mime_type, ext = generate_qr_bytes(
            content=content,
            error_correction=error_correction,
            box_size=box_size,
            border=border,
            fill_color=fill_color,
            back_color=back_color,
            export_format=format,
            size_px=size_px,
            logo_bytes=logo_bytes,
            logo_size_ratio=logo_size_ratio,
            badge_radius=badge_radius
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QR generation failed: {str(e)}")

    clean_name = sanitize_filename(f"qrcode_{content[:16]}")
    download_filename = f"{clean_name}{ext}"

    return Response(
        content=out_bytes,
        media_type=mime_type,
        headers={"Content-Disposition": make_content_disposition(download_filename)}
    )


# ==============================================================================
# 2. POST /api/qr/batch
# ==============================================================================
@router.post("/batch")
async def api_qr_batch(
    request: Request,
    file: Optional[UploadFile] = File(None),
    csv_data: Optional[str] = Form(None),
    items_json: Optional[str] = Form(None),
    format: str = Form("png"),
    error_correction: str = Form("M"),
    box_size: int = Form(10),
    border: int = Form(4),
    fill_color: str = Form("#000000"),
    back_color: str = Form("#ffffff"),
    size_px: Optional[int] = Form(512),
    logo: Optional[UploadFile] = File(None),
    x_himshiksha_key: Optional[str] = Header(None)
):
    """
    Process CSV or list of QR items in batch, generate individualized QR files,
    and assemble into a clean ZIP archive with JSON & CSV manifests.
    """
    verify_api_key(x_himshiksha_key)

    items: List[QRBatchItem] = []
    logo_bytes: Optional[bytes] = None

    # Handle JSON payload
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            model = QRBatchRequest(**body)
            items = model.items
            format = model.format
            error_correction = model.error_correction
            box_size = model.box_size
            border = model.border
            fill_color = model.fill_color
            back_color = model.back_color
            size_px = model.size_px

            if model.logo_base64:
                b64_data = model.logo_base64
                if "," in b64_data:
                    b64_data = b64_data.split(",", 1)[1]
                logo_bytes = base64.b64decode(b64_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON request body: {str(e)}")
    else:
        # Multipart form: parse items from file upload, raw CSV text, or items_json
        if file and file.filename:
            file_bytes = await file.read()
            items = parse_csv_items(file_bytes)
        elif csv_data and csv_data.strip():
            items = parse_csv_items(csv_data)
        elif items_json and items_json.strip():
            try:
                parsed_json = json.loads(items_json)
                if isinstance(parsed_json, list):
                    items = [QRBatchItem(**it) for it in parsed_json]
                elif isinstance(parsed_json, dict) and "items" in parsed_json:
                    items = [QRBatchItem(**it) for it in parsed_json["items"]]
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse items_json: {str(e)}")

        if logo and logo.filename:
            logo_bytes = await logo.read()

    if not items:
        raise HTTPException(
            status_code=400,
            detail="No batch items provided. Upload a CSV file or provide items JSON."
        )

    try:
        zip_bytes, manifest = process_qr_batch(
            items=items,
            export_format=format,
            error_correction=error_correction,
            box_size=box_size,
            border=border,
            fill_color=fill_color,
            back_color=back_color,
            size_px=size_px,
            logo_bytes=logo_bytes
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing error: {str(e)}")

    headers = {
        "Content-Disposition": make_content_disposition("qr_batch_export.zip"),
        "X-Total-Items": str(manifest.total),
        "X-Succeeded-Items": str(manifest.succeeded),
        "X-Failed-Items": str(manifest.failed)
    }

    return Response(content=zip_bytes, media_type="application/zip", headers=headers)


# ==============================================================================
# 3. POST /api/qr/scan-test
# ==============================================================================
@router.post("/scan-test", response_model=QRScanTestResponse)
async def api_qr_scan_test(
    file: UploadFile = File(...),
    expected_text: Optional[str] = Form(None),
    x_himshiksha_key: Optional[str] = Header(None)
):
    """
    Decode an uploaded QR image using OpenCV cv2.QRCodeDetector() and verify
    payload against expected text, returning fidelity score and decoded content.
    """
    verify_api_key(x_himshiksha_key)

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="An image file is required for scan testing.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = scan_and_verify_qr(image_bytes=image_bytes, expected_text=expected_text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan test engine error: {str(e)}")


# ==============================================================================
# 4. POST /api/qr/print-sheet
# ==============================================================================
@router.post("/print-sheet")
async def api_qr_print_sheet(
    request: Request,
    file: Optional[UploadFile] = File(None),
    items_json: Optional[str] = Form(None),
    paper_size: str = Form("A4"),
    orientation: str = Form("portrait"),
    rows: int = Form(4),
    cols: int = Form(3),
    margin_pt: float = Form(36.0),
    show_labels: bool = Form(True),
    show_cut_lines: bool = Form(True),
    fill_color: str = Form("#000000"),
    back_color: str = Form("#ffffff"),
    error_correction: str = Form("M"),
    x_himshiksha_key: Optional[str] = Header(None)
):
    """
    Generate a high-resolution print-ready PDF (A4 or Letter, portrait/landscape,
    custom grid rows x cols, margins, labels) using ReportLab.
    """
    verify_api_key(x_himshiksha_key)

    items: List[QRPrintSheetItem] = []

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            model = QRPrintSheetRequest(**body)
            items = model.items
            paper_size = model.paper_size
            orientation = model.orientation
            rows = model.rows
            cols = model.cols
            margin_pt = model.margin_pt
            show_labels = model.show_labels
            show_cut_lines = model.show_cut_lines
            fill_color = model.fill_color
            back_color = model.back_color
            error_correction = model.error_correction
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON request body: {str(e)}")
    else:
        # Form submission: parse from CSV file or items_json
        if file and file.filename:
            file_bytes = await file.read()
            batch_items = parse_csv_items(file_bytes)
            items = [
                QRPrintSheetItem(
                    content=bi.content,
                    label=bi.name or bi.content[:24],
                    sublabel=bi.type if bi.type != "text" else None
                )
                for bi in batch_items if bi.content
            ]
        elif items_json and items_json.strip():
            try:
                parsed = json.loads(items_json)
                if isinstance(parsed, list):
                    items = [QRPrintSheetItem(**it) for it in parsed]
                elif isinstance(parsed, dict) and "items" in parsed:
                    items = [QRPrintSheetItem(**it) for it in parsed["items"]]
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse items_json: {str(e)}")

    if not items:
        raise HTTPException(
            status_code=400,
            detail="No items provided for print sheet. Upload a CSV file or provide items JSON."
        )

    try:
        pdf_bytes = generate_print_sheet_pdf(
            items=items,
            paper_size=paper_size,
            orientation=orientation,
            rows=rows,
            cols=cols,
            margin_pt=margin_pt,
            show_labels=show_labels,
            show_cut_lines=show_cut_lines,
            fill_color=fill_color,
            back_color=back_color,
            error_correction=error_correction
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate print sheet PDF: {str(e)}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": make_content_disposition("qr_print_sheet.pdf")}
    )
