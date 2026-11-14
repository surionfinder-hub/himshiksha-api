"""
HimShiksha API - PDF Compression Service
Supports disk-based streaming compression for files up to 2GB.
Uses Ghostscript if available with PyMuPDF deflate optimization fallback.
"""

import os
import shutil
import subprocess
from typing import Tuple, Dict, Any
import pymupdf
from fastapi import HTTPException
from utils.upload_handler import create_temp_output_path


def compress_pdf_disk(input_path: str, preset: str = "balanced") -> Tuple[str, Dict[str, Any]]:
    """
    Compress PDF directly from disk file to temporary output on disk.
    Avoids reading large files (up to 2GB) into RAM.
    Returns (out_path, stats_dict).
    """
    orig_size = os.path.getsize(input_path)
    if orig_size == 0:
        raise HTTPException(status_code=400, detail="Input PDF is 0 bytes.")

    preset_clean = preset.lower().strip()
    gs_setting = "/ebook"
    if preset_clean in ["low", "screen", "maximum", "small"]:
        gs_setting = "/screen"
    elif preset_clean in ["high", "printer", "crisp", "mild"]:
        gs_setting = "/printer"
    else:
        gs_setting = "/ebook"

    gs_path = shutil.which("gs") or shutil.which("ghostscript")
    out_path = create_temp_output_path(prefix="hs_compressed_", suffix=".pdf")
    engine_used = "ghostscript"

    success = False
    if gs_path:
        cmd = [
            gs_path,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={gs_setting}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            "-dDetectDuplicateImages=true",
            f"-sOutputFile={out_path}",
            input_path
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
            if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                success = True
        except Exception:
            success = False

    if not success:
        # Fallback to PyMuPDF deflate / garbage collection
        engine_used = "pymupdf_deflate"
        try:
            doc = pymupdf.open(input_path)
            doc.save(
                out_path,
                garbage=4,
                deflate=True,
                clean=True
            )
            doc.close()
            success = True
        except Exception as e:
            if os.path.exists(out_path):
                os.remove(out_path)
            raise HTTPException(status_code=500, detail=f"PDF compression failed: {str(e)}")

    comp_size = os.path.getsize(out_path)
    savings_pct = round(((orig_size - comp_size) / orig_size) * 100, 2) if orig_size > 0 else 0.0

    # If compressed file is larger or savings <= 0, return optimal indication
    is_reduced = comp_size < orig_size

    stats = {
        "original_bytes": orig_size,
        "compressed_bytes": comp_size,
        "savings_percent": max(0.0, savings_pct),
        "is_reduced": is_reduced,
        "engine": engine_used,
        "preset": preset_clean
    }
    return out_path, stats
