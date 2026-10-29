"""
HimShiksha - Media Resource Limits, Safety Guards, and Concurrency Manager
Enforces category-based size limits, disk space checks, timeout bounds, and concurrency throttling.
"""

import os
import shutil
import threading
from typing import Dict, Any, Optional

# Category File Size Limits in Bytes
CATEGORY_LIMITS = {
    "images": 20 * 1024 * 1024,        # 20 MB
    "pdf_docs": 20 * 1024 * 1024,      # 20 MB
    "office": 20 * 1024 * 1024,        # 20 MB
    "audio": 50 * 1024 * 1024,         # 50 MB
    "video": 500 * 1024 * 1024,       # 500 MB
}

# Video Specific Processing Safety Bounds
MAX_VIDEO_DURATION_SECONDS = 7200      # 2 hours max video length
MAX_CONCURRENT_VIDEO_JOBS = 2          # Throttle concurrent video encoding to protect Render RAM/CPU
MIN_DISK_FREE_BUFFER_BYTES = 500 * 1024 * 1024  # Require at least 500MB free disk space

# Global concurrency semaphore for heavy video conversions
_video_semaphore = threading.Semaphore(MAX_CONCURRENT_VIDEO_JOBS)
_active_video_jobs = 0
_lock = threading.Lock()


class MediaLimitExceededError(Exception):
    def __init__(self, message: str, limit_bytes: int, actual_bytes: int):
        super().__init__(message)
        self.limit_bytes = limit_bytes
        self.actual_bytes = actual_bytes


class MediaResourceError(Exception):
    pass


def get_category_limit(category: str) -> int:
    """Return max allowed bytes for given category."""
    return CATEGORY_LIMITS.get(category, 20 * 1024 * 1024)


def check_size_limit(category: str, actual_bytes: int) -> None:
    """Validate that actual size does not exceed the allowed category quota."""
    limit = get_category_limit(category)
    if actual_bytes > limit:
        limit_mb = round(limit / (1024 * 1024), 1)
        actual_mb = round(actual_bytes / (1024 * 1024), 2)
        raise MediaLimitExceededError(
            f"File size ({actual_mb} MB) exceeds maximum allowed limit for {category} ({limit_mb} MB).",
            limit_bytes=limit,
            actual_bytes=actual_bytes
        )


def check_disk_space(required_bytes: int, target_dir: str = "/tmp") -> None:
    """
    Ensure the target filesystem has sufficient space for input + output buffering.
    """
    try:
        usage = shutil.disk_usage(target_dir)
        needed = required_bytes + MIN_DISK_FREE_BUFFER_BYTES
        if usage.free < needed:
            free_mb = round(usage.free / (1024 * 1024), 1)
            raise MediaResourceError(
                f"Server temporary storage is low ({free_mb} MB available). Cannot safely allocate space for processing."
            )
    except Exception as e:
        if isinstance(e, MediaResourceError):
            raise
        # If disk_usage fails (e.g. permission or special fs), continue with warning


def calculate_timeout(category: str, file_size_bytes: int, duration_seconds: float = 0.0) -> int:
    """
    Calculate dynamic timeout based on media duration, file size, and operation type.
    """
    if category == "audio":
        # Base 30s + 5s per 10MB
        return min(180, max(45, int(30 + (file_size_bytes / (10 * 1024 * 1024)) * 5)))

    if category == "video":
        # Video encoding is CPU intensive:
        # Base 60s + factor of video duration or size
        size_factor = int((file_size_bytes / (50 * 1024 * 1024)) * 25)
        duration_factor = int(duration_seconds * 0.4) if duration_seconds > 0 else 60
        timeout = 60 + max(size_factor, duration_factor)
        # Cap between 90s and 600s (10 minutes)
        return min(600, max(90, timeout))

    return 60


class VideoJobSlot:
    """Context manager to acquire a concurrency slot for video encoding."""
    def __init__(self, blocking: bool = True, timeout: float = 5.0):
        self.blocking = blocking
        self.timeout = timeout
        self.acquired = False

    def __enter__(self):
        global _active_video_jobs
        self.acquired = _video_semaphore.acquire(blocking=self.blocking, timeout=self.timeout)
        if not self.acquired:
            raise MediaResourceError(
                "All video conversion slots are currently in use. Please wait a moment and retry."
            )
        with _lock:
            _active_video_jobs += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _active_video_jobs
        if self.acquired:
            with _lock:
                _active_video_jobs = max(0, _active_video_jobs - 1)
            _video_semaphore.release()
