"""
HimShiksha API - Security & Sanitation Utilities
Enforces API key verification, safe filename generation, and path traversal protections.
"""

import os
import re
from typing import Optional
from fastapi import HTTPException, Header

EXPECTED_API_KEY = os.getenv("HIMSHIKSHA_RENDER_API_KEY", "himshiksha_render_secret_key_2026")


def verify_api_key(x_himshiksha_key: Optional[str] = Header(None)) -> None:
    """Validate secret API key between PHP proxy / trusted callers and Render API."""
    if not x_himshiksha_key or x_himshiksha_key.strip() != EXPECTED_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing X-HimShiksha-Key header."
        )


def sanitize_filename(filename: str, default: str = "document") -> str:
    """Sanitize user-supplied filename to prevent path traversal, control chars, and shell injections."""
    if not filename:
        return default
    clean = re.sub(r'[\r\n\t\\/\0:\*\?"<>\|]+', '_', filename).strip('. ')
    clean = re.sub(r'\s+', '_', clean)
    clean = clean.strip('_')
    return clean if clean else default


def make_content_disposition(filename: str) -> str:
    """Generate RFC 6266 Content-Disposition header with safe ASCII fallback and UTF-8 encoding."""
    import urllib.parse
    safe_ascii = re.sub(r'[^\w\.\-\_]', '_', filename)
    encoded = urllib.parse.quote(filename)
    return f'attachment; filename="{safe_ascii}"; filename*=UTF-8\'\'{encoded}'


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """Ensure target path is strictly contained within base directory (guards against directory traversal)."""
    abs_base = os.path.abspath(base_dir)
    abs_target = os.path.abspath(target_path)
    return os.path.commonpath([abs_base, abs_target]) == abs_base
