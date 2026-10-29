"""
HimShiksha - Temporary File Lifecycle, Streaming Spooler & Cleanup Engine
Guarantees streaming chunk-by-chunk disk spooling without loading large files into RAM,
and provides robust temporary file garbage collection.
"""

import os
import time
import shutil
import tempfile
import logging
from typing import AsyncGenerator, Optional
from fastapi import UploadFile

logger = logging.getLogger("himshiksha.media_cleanup")

# Dedicated HimShiksha temporary scratch directory
HIMSHIKSHA_TEMP_DIR = os.path.join(tempfile.gettempdir(), "himshiksha_scratch")
os.makedirs(HIMSHIKSHA_TEMP_DIR, exist_ok=True)

CHUNK_SIZE = 64 * 1024  # 64 KB streaming chunk size


async def spool_upload_to_disk(upload_file: UploadFile, suffix: str = ".tmp") -> str:
    """
    Stream incoming file upload directly to disk in 64KB chunks.
    NEVER holds the entire file in RAM, making it safe for 50MB-500MB uploads.
    """
    fd, path = tempfile.mkstemp(suffix=suffix, dir=HIMSHIKSHA_TEMP_DIR)
    total_written = 0
    try:
        with os.fdopen(fd, "wb") as f_out:
            while True:
                chunk = await upload_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                f_out.write(chunk)
                total_written += len(chunk)
        return path
    except Exception as e:
        safe_remove(path)
        raise e


def safe_remove(path: Optional[str]) -> None:
    """Safely delete a file or directory if it exists."""
    if not path:
        return
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.warning(f"Could not remove temporary path {path}: {str(e)}")


def sweep_stale_temp_files(max_age_seconds: int = 1800) -> int:
    """
    Remove temporary files older than max_age_seconds (default 30 mins)
    to prevent disk accumulation on Render.
    """
    count = 0
    now = time.time()
    try:
        for entry in os.scandir(HIMSHIKSHA_TEMP_DIR):
            try:
                if entry.is_file():
                    stat = entry.stat()
                    if now - stat.st_mtime > max_age_seconds:
                        os.remove(entry.path)
                        count += 1
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"Error sweeping temp files: {str(e)}")
    return count
