"""
HimShiksha - Video Conversion Engine (FFmpeg)
Supports MP4, MOV, MKV, AVI, WebM, WMV, FLV, MPEG, 3GP, M4V, TS with:
1. Intelligent Stream Copy (-c copy) when codecs are compatible.
2. High-performance H.264/AAC and VP9/Opus transcoding.
3. Fast-start optimization for web streaming (-movflags +faststart).
4. Audio extraction to MP3 / WAV.
5. Resource guards & concurrency limits.
"""

import os
import shutil
import subprocess
import logging
from typing import Optional, Dict, Any, Tuple

from media_probe import get_media_info, MediaProbeError
from media_limits import (
    calculate_timeout,
    VideoJobSlot,
    MAX_VIDEO_DURATION_SECONDS
)
from audio_converter import convert_audio

logger = logging.getLogger("himshiksha.video_converter")

FFMPEG_BIN = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"


class VideoConversionError(Exception):
    pass


# Target video specifications and supported options
VIDEO_TARGET_SPECS: Dict[str, Dict[str, Any]] = {
    "mp4": {
        "vcodec": "libx264",
        "acodec": "aac",
        "ext": "mp4",
        "mime": "video/mp4",
        "extra_args": ["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        "stream_copy_vcodecs": ["h264", "avc1"],
        "stream_copy_acodecs": ["aac", "mp3"]
    },
    "webm": {
        "vcodec": "libvpx-vp9",
        "acodec": "libopus",
        "ext": "webm",
        "mime": "video/webm",
        "extra_args": ["-crf", "32", "-b:v", "0", "-b:a", "128k"],
        "stream_copy_vcodecs": ["vp8", "vp9", "av1"],
        "stream_copy_acodecs": ["opus", "vorbis"]
    },
    "mkv": {
        "vcodec": "libx264",
        "acodec": "aac",
        "ext": "mkv",
        "mime": "video/x-matroska",
        "extra_args": [],
        "stream_copy_vcodecs": ["h264", "hevc", "vp9", "av1"],
        "stream_copy_acodecs": ["aac", "mp3", "opus", "flac"]
    },
    "avi": {
        "vcodec": "mpeg4",
        "acodec": "mp3",
        "ext": "avi",
        "mime": "video/x-msvideo",
        "extra_args": ["-q:v", "5"],
        "stream_copy_vcodecs": ["mpeg4", "mjpeg"],
        "stream_copy_acodecs": ["mp3"]
    },
    "mov": {
        "vcodec": "libx264",
        "acodec": "aac",
        "ext": "mov",
        "mime": "video/quicktime",
        "extra_args": ["-pix_fmt", "yuv420p"],
        "stream_copy_vcodecs": ["h264", "hevc", "prores"],
        "stream_copy_acodecs": ["aac", "alac", "pcm_s16le"]
    }
}


def can_use_stream_copy(source_info: Dict[str, Any], target_fmt: str) -> Tuple[bool, bool]:
    """
    Check if video and audio streams can be copied losslessly without re-encoding.
    Returns (can_copy_video, can_copy_audio).
    """
    spec = VIDEO_TARGET_SPECS.get(target_fmt)
    if not spec:
        return False, False

    video_info = source_info.get("video") or {}
    audio_info = source_info.get("audio") or {}

    src_vcodec = (video_info.get("codec_name") or "").lower()
    src_acodec = (audio_info.get("codec_name") or "").lower()

    can_copy_video = src_vcodec in spec.get("stream_copy_vcodecs", [])
    can_copy_audio = (not audio_info) or (src_acodec in spec.get("stream_copy_acodecs", []))

    return can_copy_video, can_copy_audio


def convert_video(
    input_path: str,
    output_format: str,
    output_path: Optional[str] = None,
    resolution: Optional[str] = None,   # e.g. "1920x1080", "1280x720", "854x480"
    preset: str = "fast",
    crf: int = 23,
    timeout: Optional[int] = None
) -> Dict[str, Any]:
    """
    Execute video conversion with smart stream copy and safety throttling.
    """
    if not os.path.exists(input_path):
        raise VideoConversionError(f"Input file not found: {input_path}")

    fmt = output_format.lower().lstrip(".")

    # Handle Audio Extraction shortcut (e.g. output_format='mp3' or 'wav')
    if fmt in ("mp3", "wav", "aac", "m4a", "flac"):
        return convert_audio(input_path=input_path, output_format=fmt, output_path=output_path, timeout=timeout)

    if fmt not in VIDEO_TARGET_SPECS:
        raise VideoConversionError(
            f"Unsupported video target format: '{output_format}'. Supported formats: {', '.join(VIDEO_TARGET_SPECS.keys())}"
        )

    spec = VIDEO_TARGET_SPECS[fmt]

    # Inspect media with ffprobe
    try:
        probe_info = get_media_info(input_path)
    except MediaProbeError as e:
        raise VideoConversionError(f"Failed to probe video file: {str(e)}")

    if not probe_info.get("has_video"):
        raise VideoConversionError("Input file does not contain a recognizable video stream.")

    duration = probe_info.get("duration_seconds", 0.0)
    if duration > MAX_VIDEO_DURATION_SECONDS:
        raise VideoConversionError(
            f"Video duration ({round(duration / 60, 1)} minutes) exceeds maximum allowed limit of {MAX_VIDEO_DURATION_SECONDS // 60} minutes."
        )

    if not output_path:
        base_dir = os.path.dirname(input_path)
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(base_dir, f"{base_name}.{spec['ext']}")

    if os.path.abspath(input_path) == os.path.abspath(output_path):
        output_path = os.path.join(os.path.dirname(input_path), f"converted_{os.path.basename(output_path)}")

    input_size = os.path.getsize(input_path)
    if timeout is None:
        timeout = calculate_timeout("video", input_size, duration)

    # Check for stream copy eligibility (only if no resolution scaling is requested)
    copy_video, copy_audio = False, False
    if not resolution:
        copy_video, copy_audio = can_use_stream_copy(probe_info, fmt)

    # Build safe FFmpeg arguments
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-v", "error",
        "-nostdin",
        "-i", input_path
    ]

    # Video stream configuration
    if copy_video:
        cmd.extend(["-c:v", "copy"])
        mode_used = "stream_copy"
    else:
        cmd.extend(["-c:v", spec["vcodec"]])
        if spec["vcodec"] == "libx264":
            cmd.extend(["-preset", preset, "-crf", str(crf)])
        mode_used = "transcode"

        # Apply resolution filter if specified
        if resolution:
            # Validate resolution format e.g. 1280x720 or 720p
            if "x" in resolution:
                w, h = resolution.split("x", 1)
                if w.isdigit() and h.isdigit():
                    cmd.extend(["-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"])

    # Audio stream configuration
    if copy_audio:
        cmd.extend(["-c:a", "copy"])
    else:
        cmd.extend(["-c:a", spec["acodec"]])

    # Extra container options
    if spec["extra_args"]:
        cmd.extend(spec["extra_args"])

    cmd.append(output_path)

    logger.info(f"Executing video conversion: mode={mode_used}, fmt={fmt}, duration={duration:.1f}s")

    # Run inside concurrency limiter slot
    with VideoJobSlot(blocking=True, timeout=10.0):
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
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            raise VideoConversionError(f"Video conversion timed out after {timeout} seconds.")
        except Exception as e:
            raise VideoConversionError(f"Failed to execute video converter: {str(e)}")

    if proc.returncode != 0:
        err = proc.stderr.strip() or f"Process returned error code {proc.returncode}"
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        raise VideoConversionError(f"FFmpeg video conversion failed: {err}")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise VideoConversionError("Video conversion produced an empty output file.")

    out_size = os.path.getsize(output_path)

    return {
        "output_path": output_path,
        "format": fmt,
        "extension": spec["ext"],
        "mime_type": spec["mime"],
        "size_bytes": out_size,
        "size_mb": round(out_size / (1024 * 1024), 2),
        "duration_seconds": duration,
        "conversion_mode": mode_used
    }
