"""
HimShiksha - Media Probing and Inspection Module (ffprobe)
Extracts container format, streams, codecs, duration, bitrate, resolution, and audio channels.
"""

import json
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger("himshiksha.media_probe")

FFPROBE_BIN = shutil.which("ffprobe") or "/usr/bin/ffprobe"


class MediaProbeError(Exception):
    pass


def get_media_info(file_path: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Execute ffprobe to extract complete JSON metadata for a media file.
    """
    if not os.path.exists(file_path):
        raise MediaProbeError(f"File not found for probing: {file_path}")

    if not os.path.isfile(file_path):
        raise MediaProbeError(f"Target is not a regular file: {file_path}")

    cmd = [
        FFPROBE_BIN,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-show_error",
        file_path
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
            check=False
        )
    except subprocess.TimeoutExpired:
        raise MediaProbeError("ffprobe timed out while analyzing media file.")
    except Exception as e:
        raise MediaProbeError(f"Failed to execute ffprobe: {str(e)}")

    if proc.returncode != 0 or not proc.stdout.strip():
        err_msg = proc.stderr.strip() or f"Process exited with code {proc.returncode}"
        raise MediaProbeError(f"ffprobe failed to analyze file: {err_msg}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise MediaProbeError(f"Invalid JSON output from ffprobe: {str(e)}")

    if "error" in data:
        error_info = data["error"]
        raise MediaProbeError(f"ffprobe reported error: {error_info.get('string', 'Unknown error')}")

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    duration = float(fmt.get("duration", 0.0) or 0.0)
    size_bytes = int(fmt.get("size", os.path.getsize(file_path)) or 0)
    bitrate = int(fmt.get("bit_rate", 0) or 0)

    primary_video = video_streams[0] if video_streams else None
    primary_audio = audio_streams[0] if audio_streams else None

    video_info = None
    if primary_video:
        video_info = {
            "codec_name": primary_video.get("codec_name", ""),
            "codec_long_name": primary_video.get("codec_long_name", ""),
            "width": int(primary_video.get("width", 0) or 0),
            "height": int(primary_video.get("height", 0) or 0),
            "fps": _parse_fps(primary_video.get("r_frame_rate", "0/1")),
            "pixel_format": primary_video.get("pix_fmt", ""),
            "bitrate": int(primary_video.get("bit_rate", 0) or 0)
        }

    audio_info = None
    if primary_audio:
        audio_info = {
            "codec_name": primary_audio.get("codec_name", ""),
            "codec_long_name": primary_audio.get("codec_long_name", ""),
            "channels": int(primary_audio.get("channels", 0) or 0),
            "channel_layout": primary_audio.get("channel_layout", ""),
            "sample_rate": int(primary_audio.get("sample_rate", 0) or 0),
            "bitrate": int(primary_audio.get("bit_rate", 0) or 0)
        }

    return {
        "format_name": fmt.get("format_name", ""),
        "format_long_name": fmt.get("format_long_name", ""),
        "duration_seconds": duration,
        "size_bytes": size_bytes,
        "overall_bitrate": bitrate,
        "has_video": len(video_streams) > 0,
        "has_audio": len(audio_streams) > 0,
        "video": video_info,
        "audio": audio_info,
        "tags": fmt.get("tags", {})
    }


def _parse_fps(rate_str: str) -> float:
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/", 1)
            den_val = float(den)
            return round(float(num) / den_val, 2) if den_val != 0 else 0.0
        return round(float(rate_str), 2)
    except Exception:
        return 0.0
