"""
HimShiksha - Advanced PDF Compression Engine
Multi-preset PDF compressor using Ghostscript CLI with PyMuPDF raster/stream optimization fallback.
Calculates size differential, percentage saved, preserves readability, and detects if file is already optimal.
"""

import os
import io
import shutil
import tempfile
import subprocess
from typing import Tuple, Dict, Any

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf


class CompressEngine:
    def __init__(self):
        self.gs_path = shutil.which("gs") or shutil.which("ghostscript")

    def is_ghostscript_available(self) -> bool:
        return self.gs_path is not None

    def compress_pdf(self, pdf_bytes: bytes, preset: str = "balanced") -> Tuple[bytes, Dict[str, Any]]:
        """
        Compress PDF according to preset.
        Presets:
          - 'low' / 'screen': 72 DPI, maximum compression, smallest size.
          - 'balanced' / 'ebook': 150 DPI, optimal balance for web & reading (Recommended).
          - 'high' / 'printer': 300 DPI, high resolution, mild compression.
        """
        orig_size = len(pdf_bytes)
        if orig_size == 0:
            raise ValueError("Input PDF is 0 bytes.")

        preset_clean = preset.lower().strip()
        gs_setting = "/ebook"
        if preset_clean in ["low", "screen", "maximum", "small"]:
            gs_setting = "/screen"
        elif preset_clean in ["high", "printer", "crisp", "mild"]:
            gs_setting = "/printer"
        else:
            gs_setting = "/ebook"

        compressed_bytes = None
        engine_used = "ghostscript"

        # 1. Attempt Ghostscript compression if available
        if self.is_ghostscript_available():
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    in_path = os.path.join(tmpdir, "input.pdf")
                    out_path = os.path.join(tmpdir, "output.pdf")

                    with open(in_path, "wb") as f:
                        f.write(pdf_bytes)

                    cmd = [
                        self.gs_path,
                        "-sDEVICE=pdfwrite",
                        "-dCompatibilityLevel=1.4",
                        f"-dPDFSETTINGS={gs_setting}",
                        "-dNOPAUSE",
                        "-dQUIET",
                        "-dBATCH",
                        "-dDetectDuplicateImages=true",
                        "-dCompressFonts=true",
                        f"-sOutputFile={out_path}",
                        in_path
                    ]

                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                        with open(out_path, "rb") as cf:
                            compressed_bytes = cf.read()
            except Exception as e:
                compressed_bytes = None

        # 2. PyMuPDF fallback if Ghostscript unavailable or failed
        if compressed_bytes is None:
            engine_used = "pymupdf_optimizer"
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            out_buf = io.BytesIO()
            # PyMuPDF deflate, garbage collection, and stream defragmentation
            doc.save(
                out_buf,
                deflate=True,
                garbage=4,
                clean=True,
                linear=True
            )
            doc.close()
            compressed_bytes = out_buf.getvalue()

        comp_size = len(compressed_bytes)

        # 3. Size comparison & Savings calculation
        # If compressed file is larger or equal, preserve original file
        if comp_size >= orig_size:
            return pdf_bytes, {
                "original_bytes": orig_size,
                "compressed_bytes": orig_size,
                "savings_bytes": 0,
                "savings_percent": 0.0,
                "is_reduced": False,
                "preset": preset_clean,
                "engine": engine_used,
                "message": "This PDF is already optimally compressed. No size reduction was possible without severe quality degradation."
            }

        savings_bytes = orig_size - comp_size
        savings_percent = round((savings_bytes / orig_size) * 100, 1)

        return compressed_bytes, {
            "original_bytes": orig_size,
            "compressed_bytes": comp_size,
            "savings_bytes": savings_bytes,
            "savings_percent": savings_percent,
            "is_reduced": True,
            "preset": preset_clean,
            "engine": engine_used,
            "message": f"Successfully reduced PDF by {savings_percent}% ({savings_bytes / 1024:.1f} KB saved)."
        }


compress_engine = CompressEngine()
