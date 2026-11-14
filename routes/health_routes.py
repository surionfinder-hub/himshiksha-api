"""
HimShiksha API - Health and Root Information Endpoints
"""

import shutil
from fastapi import APIRouter
from utils.file_validation import LIMIT_2GB_BYTES, LIMIT_5GB_BYTES

router = APIRouter(tags=["Health"])


@router.get("/")
def read_root():
    """HimShiksha Python Engine API Information."""
    return {
        "service": "HimShiksha Python Engine API",
        "status": "online",
        "architecture": "modular",
        "limits": {
            "pdf_tools": "2 GB",
            "image_tools": "2 GB",
            "archive_tools": "2 GB",
            "media_tools": "5 GB"
        },
        "engines": {
            "pdf": "PyMuPDF (fitz) + pypdf",
            "image": "Pillow (PIL)",
            "office": "LibreOffice Headless + python-docx + openpyxl",
            "media": "FFmpeg"
        }
    }


@router.get("/health")
def health_check():
    """Health probe endpoint used by uptime monitors, PHP proxy, and Render orchestrators."""
    return {
        "status": "healthy",
        "libreoffice_available": shutil.which("soffice") is not None,
        "ghostscript_available": shutil.which("gs") is not None or shutil.which("ghostscript") is not None,
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "supported_limits": {
            "pdf_bytes": LIMIT_2GB_BYTES,
            "image_bytes": LIMIT_2GB_BYTES,
            "archive_bytes": LIMIT_2GB_BYTES,
            "media_bytes": LIMIT_5GB_BYTES
        }
    }
