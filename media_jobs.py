"""
HimShiksha - Asynchronous Media Job Management Engine
Allows long-running video and audio conversions to process safely in the background,
avoiding HTTP gateway timeouts and enabling live client status polling.
"""

import os
import time
import uuid
import threading
import logging
from typing import Dict, Any, Optional

from video_converter import convert_video, VideoConversionError
from audio_converter import convert_audio, AudioConversionError
from media_cleanup import safe_remove, HIMSHIKSHA_TEMP_DIR

logger = logging.getLogger("himshiksha.media_jobs")

# In-memory job registry with thread-safe lock
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def create_job(
    media_type: str,            # 'video' or 'audio'
    input_path: str,
    output_format: str,
    original_filename: str,
    options: Optional[Dict[str, Any]] = None
) -> str:
    """Register a new media job and start processing in a background worker."""
    job_id = f"him_mjob_{uuid.uuid4().hex[:16]}"
    now = time.time()

    job_record = {
        "job_id": job_id,
        "media_type": media_type,
        "input_path": input_path,
        "output_format": output_format,
        "original_filename": original_filename,
        "options": options or {},
        "status": "queued",
        "progress_percent": 0,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None
    }

    with _jobs_lock:
        _jobs[job_id] = job_record

    # Start background execution thread
    worker = threading.Thread(target=_process_job, args=(job_id,), daemon=True)
    worker.start()

    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve job status information."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        # Return a copy without internal sensitive references
        return {
            "job_id": job["job_id"],
            "media_type": job["media_type"],
            "status": job["status"],
            "progress_percent": job["progress_percent"],
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "completed_at": job["completed_at"],
            "result": job["result"],
            "error": job["error"],
            "original_filename": job["original_filename"],
            "output_format": job["output_format"]
        }


def get_job_output_path(job_id: str) -> Optional[str]:
    """Return local path to the generated output file if completed."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job.get("status") != "completed":
            return None
        res = job.get("result") or {}
        return res.get("output_path")


def _process_job(job_id: str) -> None:
    """Background worker that executes the audio or video conversion."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "processing"
        job["started_at"] = time.time()
        job["progress_percent"] = 15

    input_path = job["input_path"]
    fmt = job["output_format"]
    media_type = job["media_type"]
    opts = job.get("options") or {}

    try:
        if media_type == "audio":
            result = convert_audio(
                input_path=input_path,
                output_format=fmt,
                bitrate=opts.get("bitrate"),
                sample_rate=opts.get("sample_rate"),
                channels=opts.get("channels")
            )
        else:
            result = convert_video(
                input_path=input_path,
                output_format=fmt,
                resolution=opts.get("resolution"),
                preset=opts.get("preset", "fast"),
                crf=int(opts.get("crf", 23))
            )

        with _jobs_lock:
            job["status"] = "completed"
            job["progress_percent"] = 100
            job["completed_at"] = time.time()
            job["result"] = result

    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        with _jobs_lock:
            job["status"] = "failed"
            job["error"] = str(e)
            job["completed_at"] = time.time()

    finally:
        # Clean up input temporary file
        safe_remove(input_path)


def cleanup_expired_jobs(max_age_seconds: int = 7200) -> int:
    """Remove expired jobs and delete their output files."""
    now = time.time()
    expired_ids = []
    with _jobs_lock:
        for jid, j in list(_jobs.items()):
            if now - j.get("created_at", now) > max_age_seconds:
                expired_ids.append(jid)
                out_path = None
                if j.get("result"):
                    out_path = j["result"].get("output_path")
                if out_path:
                    safe_remove(out_path)
                del _jobs[jid]
    return len(expired_ids)
