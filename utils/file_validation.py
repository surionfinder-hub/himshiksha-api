"""
HimShiksha API - File Validation & Quota Constants
Strictly enforces:
- 2 GB (2,147,483,648 bytes) for PDF Tools, Image Tools, and Archive Files.
- 5 GB (5,368,709,120 bytes) for Audio and Video Tools.
- 20 MB (20,971,520 bytes) for Office, Text, and Document Tools.
"""

from fastapi import HTTPException

# 2 GB limit (2,147,483,648 bytes)
LIMIT_2GB_BYTES = 2 * 1024 * 1024 * 1024  # 2,147,483,648 bytes

# 5 GB limit (5,368,709,120 bytes)
LIMIT_5GB_BYTES = 5 * 1024 * 1024 * 1024  # 5,368,709,120 bytes

# 20 MB limit (20,971,520 bytes)
LIMIT_20MB_BYTES = 20 * 1024 * 1024       # 20,971,520 bytes

CATEGORY_LIMITS = {
    "pdf": LIMIT_2GB_BYTES,
    "image": LIMIT_2GB_BYTES,
    "archive": LIMIT_2GB_BYTES,
    "office": LIMIT_20MB_BYTES,
    "text": LIMIT_20MB_BYTES,
    "audio": LIMIT_5GB_BYTES,
    "video": LIMIT_5GB_BYTES,
}


def get_category_limit(category: str) -> int:
    """Return max allowed bytes for given category."""
    cat = category.lower().strip()
    return CATEGORY_LIMITS.get(cat, LIMIT_2GB_BYTES)


def format_bytes_human(num_bytes: int) -> str:
    """Format bytes into readable string (e.g. 2 GB, 20 MB)."""
    if num_bytes >= 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024 * 1024):.0f} GB"
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.0f} MB"
    return f"{num_bytes} bytes"


def validate_file_size(size_bytes: int, category: str = "pdf") -> None:
    """Validate file size against category limits."""
    max_bytes = get_category_limit(category)
    if size_bytes > max_bytes:
        limit_str = format_bytes_human(max_bytes)
        file_str = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB" if size_bytes >= 1024 * 1024 * 1024 else f"{size_bytes / (1024 * 1024):.1f} MB"
        raise HTTPException(
            status_code=413,
            detail=f"File size ({file_str}) exceeds the maximum allowed limit of {limit_str} for {category.upper()} tools."
        )
