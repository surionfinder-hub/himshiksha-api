"""
HimShiksha API - Archive Security & ZIP Bomb Protection
Prevents ZIP bombs, directory traversal attacks, and resource exhaustion.
"""

import os
import zipfile
from fastapi import HTTPException
from utils.security import is_safe_path

# ZIP Bomb & Extraction Safeguards
MAX_ARCHIVE_FILE_COUNT = 2000          # Max entries inside archive
MAX_UNCOMPRESSED_TOTAL_BYTES = 4 * 1024 * 1024 * 1024 # 4 GB max uncompressed total
MAX_COMPRESSION_RATIO = 100            # Max uncompressed / compressed ratio


def inspect_and_validate_zip(zip_path: str) -> None:
    """Inspect a ZIP file before extraction to verify safety and guard against zip bombs."""
    if not zipfile.is_zipfile(zip_path):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive.")

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            infolist = zf.infolist()

            if len(infolist) > MAX_ARCHIVE_FILE_COUNT:
                raise HTTPException(
                    status_code=400,
                    detail=f"Archive contains too many files ({len(infolist)}). Max allowed is {MAX_ARCHIVE_FILE_COUNT}."
                )

            total_uncompressed = sum(info.file_size for info in infolist)
            if total_uncompressed > MAX_UNCOMPRESSED_TOTAL_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Archive uncompressed content exceeds the 4 GB safety limit (potential zip bomb)."
                )

            compressed_size = os.path.getsize(zip_path) or 1
            ratio = total_uncompressed / compressed_size
            if ratio > MAX_COMPRESSION_RATIO and total_uncompressed > 50 * 1024 * 1024:
                raise HTTPException(
                    status_code=400,
                    detail="Abnormally high compression ratio detected (potential zip bomb rejected)."
                )

            # Check for path traversal in archive member names
            for member in infolist:
                norm_name = os.path.normpath(member.filename)
                if norm_name.startswith(("/", "\\")) or ".." in norm_name.split(os.sep):
                    raise HTTPException(
                        status_code=400,
                        detail="Archive contains unsafe file paths (path traversal rejected)."
                    )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Corrupted or invalid ZIP file.")


def safe_extract_zip(zip_path: str, extract_dir: str) -> list[str]:
    """Safely extract ZIP entries ensuring no file leaves extract_dir."""
    inspect_and_validate_zip(zip_path)
    extracted_files = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            dest = os.path.abspath(os.path.join(extract_dir, member.filename))
            if not is_safe_path(extract_dir, dest):
                raise HTTPException(status_code=400, detail="Unsafe entry path in archive.")
            if member.is_dir():
                os.makedirs(dest, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    while chunk := src.read(1024 * 1024):
                        dst.write(chunk)
                extracted_files.append(dest)
    return extracted_files
