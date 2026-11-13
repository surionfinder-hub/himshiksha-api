"""
HimShiksha - Resumable Chunked Upload Manager for Large Files (up to 5GB)
Streams binary slices directly into dedicated scratch files, merging seamlessly
on final chunk and preventing server memory saturation.
"""

import os
import time
import tempfile
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("himshiksha.chunk_manager")

TEMP_CHUNK_DIR = os.path.join(tempfile.gettempdir(), "himshiksha_chunks")
os.makedirs(TEMP_CHUNK_DIR, exist_ok=True)

MAX_SUPPORTED_BYTES = 5368709120  # Exactly 5 GB (5,368,709,120 bytes)


def init_chunked_upload(upload_id: str, filename: str, total_size: int, total_chunks: int) -> Dict[str, Any]:
    if total_size > MAX_SUPPORTED_BYTES:
        raise ValueError(f"File size ({total_size} bytes) exceeds maximum 5GB limit ({MAX_SUPPORTED_BYTES} bytes).")

    upload_dir = os.path.join(TEMP_CHUNK_DIR, upload_id)
    os.makedirs(upload_dir, exist_ok=True)

    meta_file = os.path.join(upload_dir, "meta.json")
    import json
    meta = {
        "upload_id": upload_id,
        "filename": filename,
        "total_size": total_size,
        "total_chunks": total_chunks,
        "received_chunks": 0,
        "created_at": time.time(),
        "updated_at": time.time(),
        "completed": False
    }
    with open(meta_file, "w") as f:
        json.dump(meta, f)

    return meta


def append_chunk(upload_id: str, chunk_index: int, chunk_bytes: bytes) -> Dict[str, Any]:
    upload_dir = os.path.join(TEMP_CHUNK_DIR, upload_id)
    if not os.path.exists(upload_dir):
        raise ValueError("Upload session not found or expired.")

    chunk_file = os.path.join(upload_dir, f"chunk_{chunk_index:05d}.part")
    with open(chunk_file, "wb") as f:
        f.write(chunk_bytes)

    meta_file = os.path.join(upload_dir, "meta.json")
    import json
    with open(meta_file, "r") as f:
        meta = json.load(f)

    meta["updated_at"] = time.time()
    # Count parts
    parts = [p for p in os.listdir(upload_dir) if p.startswith("chunk_") and p.endswith(".part")]
    meta["received_chunks"] = len(parts)

    with open(meta_file, "w") as f:
        json.dump(meta, f)

    return meta


def finalize_chunked_upload(upload_id: str) -> str:
    """Merges all chunks sequentially into the final assembled file on disk."""
    upload_dir = os.path.join(TEMP_CHUNK_DIR, upload_id)
    if not os.path.exists(upload_dir):
        raise ValueError("Upload session not found.")

    meta_file = os.path.join(upload_dir, "meta.json")
    import json
    with open(meta_file, "r") as f:
        meta = json.load(f)

    total_chunks = meta["total_chunks"]
    final_path = os.path.join(TEMP_CHUNK_DIR, f"assembled_{upload_id}_{meta['filename']}")

    with open(final_path, "wb") as outfile:
        for idx in range(total_chunks):
            chunk_file = os.path.join(upload_dir, f"chunk_{idx:05d}.part")
            if not os.path.exists(chunk_file):
                raise ValueError(f"Missing chunk index {idx} in assembly.")
            with open(chunk_file, "rb") as infile:
                while block := infile.read(65536):
                    outfile.write(block)
            try:
                os.remove(chunk_file)
            except Exception:
                pass

    # Cleanup metadata & directory
    try:
        os.remove(meta_file)
        os.rmdir(upload_dir)
    except Exception:
        pass

    final_size = os.path.getsize(final_path)
    if final_size > MAX_SUPPORTED_BYTES:
        try:
            os.remove(final_path)
        except Exception:
            pass
        raise ValueError(f"Assembled file size ({final_size} bytes) exceeds the strict 5GB limit.")

    return final_path
