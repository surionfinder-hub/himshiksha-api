"""
HimShiksha API - Disk-Based Streaming Upload Handler
Streams large uploads (up to 2GB / 5GB) directly to disk in 8MB chunks.
Guarantees RAM usage stays minimal (<30MB) and never saturates server memory.
"""

import os
import tempfile
from fastapi import UploadFile, HTTPException
from utils.file_validation import LIMIT_2GB_BYTES, format_bytes_human


CHUNK_STREAM_SIZE = 8 * 1024 * 1024  # 8 MB streaming chunks


async def save_upload_to_disk(upload_file: UploadFile, max_bytes: int = LIMIT_2GB_BYTES, suffix: str = ".tmp") -> str:
    """
    Stream an UploadFile directly into a temporary file on disk.
    Enforces maximum size bounds during stream to abort early if exceeded.
    Returns the absolute path to the saved temporary file.
    """
    ext = os.path.splitext(upload_file.filename or "")[1].lower() or suffix
    fd, tmp_path = tempfile.mkstemp(prefix="hs_upload_", suffix=ext)
    total_written = 0

    try:
        with os.fdopen(fd, "wb") as f_out:
            while True:
                chunk = await upload_file.read(CHUNK_STREAM_SIZE)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > max_bytes:
                    limit_str = format_bytes_human(max_bytes)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed limit of {limit_str}."
                    )
                f_out.write(chunk)
        return tmp_path
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to stream upload to disk: {str(e)}")


def create_temp_output_path(prefix: str = "hs_out_", suffix: str = ".pdf") -> str:
    """Create an empty temporary file and return its path for tool output generation."""
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    return path
