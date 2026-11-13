"""
HimShiksha - Asynchronous Media Job Management Engine with Live Progress & Cancellation
Tracks live FFmpeg transcoding percentage, processed duration, cancel execution,
and safe resource cleanup.
"""

import os
import time
import uuid
import threading
import subprocess
import logging
from typing import Dict, Any, Optional, Callable

from video_converter import VIDEO_TARGET_SPECS, can_use_stream_copy, VideoConversionError, FFMPEG_BIN
from audio_converter import AUDIO_CODEC_MAP, AudioConversionError
from media_cleanup import safe_remove, HIMSHIKSHA_TEMP_DIR
from media_probe import get_media_info

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
        "stage": "preparing",
        "stage_label": "Preparing Conversion...",
        "progress_percent": 0,
        "processed_seconds": 0.0,
        "total_seconds": 0.0,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "process": None,       # Reference to active subprocess.Popen for cancellation
        "cancelled": False,
        "result": None,
        "error": None
    }

    with _jobs_lock:
        _jobs[job_id] = job_record

    # Start background execution thread
    worker = threading.Thread(target=_process_job, args=(job_id,), daemon=True)
    worker.start()

    return job_id


def cancel_job(job_id: str) -> bool:
    """Safely terminate ongoing FFmpeg process and clean temporary files."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return False

        if job["status"] in ("completed", "cancelled", "failed"):
            return False

        job["cancelled"] = True
        job["status"] = "cancelled"
        job["stage"] = "cancelled"
        job["stage_label"] = "Conversion Cancelled by User"
        proc = job.get("process")

    # Terminate background FFmpeg process
    if proc:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception as e:
            logger.warning(f"Error terminating process for job {job_id}: {e}")

    # Cleanup temp input & output if partially written
    input_path = job.get("input_path")
    if input_path:
        safe_remove(input_path)

    opts = job.get("options") or {}
    out_path = opts.get("custom_output_path")
    if out_path:
        safe_remove(out_path)

    return True


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve job status information."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        return {
            "job_id": job["job_id"],
            "media_type": job["media_type"],
            "status": job["status"],
            "stage": job.get("stage", "processing"),
            "stage_label": job.get("stage_label", "Converting Media..."),
            "progress_percent": job["progress_percent"],
            "processed_seconds": round(job.get("processed_seconds", 0.0), 1),
            "total_seconds": round(job.get("total_seconds", 0.0), 1),
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "completed_at": job["completed_at"],
            "result": job["result"],
            "error": job["error"],
            "cancelled": job.get("cancelled", False),
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
    """Background worker that executes the audio or video conversion with -progress pipe:1."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "processing"
        job["stage"] = "analyzing"
        job["stage_label"] = "Analyzing Media Streams..."
        job["started_at"] = time.time()

    input_path = job["input_path"]
    fmt = job["output_format"].lower().lstrip(".")
    media_type = job["media_type"]
    opts = job.get("options") or {}

    try:
        # 1. Probe total duration
        probe_info = get_media_info(input_path)
        total_duration = float(probe_info.get("duration_seconds", 0.0) or 0.0)
        with _jobs_lock:
            job["total_seconds"] = total_duration
            job["stage"] = "converting"
            job["stage_label"] = "Transcoding Media..."

        # 2. Build output path
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        ext = fmt
        if media_type == "video" and fmt in VIDEO_TARGET_SPECS:
            ext = VIDEO_TARGET_SPECS[fmt]["ext"]
        elif fmt in AUDIO_CODEC_MAP:
            ext = AUDIO_CODEC_MAP[fmt]["ext"]

        output_path = os.path.join(HIMSHIKSHA_TEMP_DIR, f"{base_name}_{job_id}.{ext}")
        opts["custom_output_path"] = output_path

        # 3. Build FFmpeg command with -progress pipe:1
        cmd = [FFMPEG_BIN, "-y", "-nostdin", "-i", input_path]

        if media_type == "audio":
            spec = AUDIO_CODEC_MAP.get(fmt, AUDIO_CODEC_MAP["mp3"])
            cmd.extend(["-vn", "-c:a", spec["codec"]])
            bitrate = opts.get("bitrate") or spec["default_bitrate"]
            if bitrate:
                b_str = str(bitrate)
                if not b_str.endswith("k") and not b_str.endswith("K"):
                    b_str += "k"
                cmd.extend(["-b:a", b_str])
            if opts.get("sample_rate"):
                cmd.extend(["-ar", str(opts["sample_rate"])])
            if opts.get("channels"):
                cmd.extend(["-ac", str(opts["channels"])])
            if spec.get("extra_args"):
                cmd.extend(spec["extra_args"])
        else:
            # Video
            spec = VIDEO_TARGET_SPECS.get(fmt, VIDEO_TARGET_SPECS["mp4"])
            resolution = opts.get("resolution")
            copy_video, copy_audio = False, False
            if not resolution or resolution == "original":
                copy_video, copy_audio = can_use_stream_copy(probe_info, fmt)

            if copy_video:
                cmd.extend(["-c:v", "copy"])
            else:
                cmd.extend(["-c:v", spec["vcodec"]])
                if spec["vcodec"] == "libx264":
                    preset = opts.get("preset", "fast")
                    crf = str(opts.get("crf", 23))
                    cmd.extend(["-preset", preset, "-crf", crf])

                if resolution and resolution != "original":
                    res_clean = resolution.lower().strip()
                    if res_clean == "1080p":
                        cmd.extend(["-vf", "scale=-2:1080"])
                    elif res_clean == "720p":
                        cmd.extend(["-vf", "scale=-2:720"])
                    elif res_clean == "480p":
                        cmd.extend(["-vf", "scale=-2:480"])
                    elif res_clean == "360p":
                        cmd.extend(["-vf", "scale=-2:360"])

            if copy_audio:
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", spec["acodec"]])

            if spec.get("extra_args"):
                cmd.extend(spec["extra_args"])

        cmd.extend(["-progress", "pipe:1", "-nostats", output_path])

        # 4. Launch subprocess and stream progress
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with _jobs_lock:
            job["process"] = proc

        for line in proc.stdout:
            if job.get("cancelled"):
                break
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                if k == "out_time_us":
                    try:
                        us = int(v)
                        sec = us / 1000000.0
                        if total_duration > 0:
                            pct = min(98, max(1, int((sec / total_duration) * 100)))
                        else:
                            pct = min(95, int(job.get("progress_percent", 0) + 1))
                        with _jobs_lock:
                            job["processed_seconds"] = sec
                            job["progress_percent"] = pct
                    except (ValueError, TypeError):
                        pass

        proc.wait()

        # Check if cancelled during conversion
        if job.get("cancelled"):
            safe_remove(output_path)
            return

        if proc.returncode != 0:
            err = proc.stderr.read().strip() or f"Process exited with code {proc.returncode}"
            safe_remove(output_path)
            raise RuntimeError(f"FFmpeg conversion failed: {err}")

        # Finalize Output
        with _jobs_lock:
            job["stage"] = "finalizing"
            job["stage_label"] = "Finalizing Output File..."
            job["progress_percent"] = 99

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Conversion produced an empty output file.")

        out_size = os.path.getsize(output_path)
        mime = "video/mp4"
        if media_type == "audio" and fmt in AUDIO_CODEC_MAP:
            mime = AUDIO_CODEC_MAP[fmt]["mime"]
        elif fmt in VIDEO_TARGET_SPECS:
            mime = VIDEO_TARGET_SPECS[fmt]["mime"]

        result_meta = {
            "output_path": output_path,
            "format": fmt,
            "extension": ext,
            "mime_type": mime,
            "size_bytes": out_size,
            "size_mb": round(out_size / (1024 * 1024), 2),
            "duration_seconds": total_duration
        }

        with _jobs_lock:
            job["status"] = "completed"
            job["stage"] = "completed"
            job["stage_label"] = "Conversion Complete!"
            job["progress_percent"] = 100
            job["completed_at"] = time.time()
            job["result"] = result_meta

    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        with _jobs_lock:
            if not job.get("cancelled"):
                job["status"] = "failed"
                job["stage"] = "failed"
                job["stage_label"] = "Conversion Failed"
                job["error"] = str(e)
                job["completed_at"] = time.time()
    finally:
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
