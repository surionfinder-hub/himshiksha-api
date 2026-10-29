"""
HimShiksha - Audio Conversion Engine (FFmpeg)
Supports bidirectional conversion between MP3, WAV, AAC, M4A, FLAC, OGG, Opus, WMA, AIFF, AMR,
as well as audio extraction from video tracks.
"""

import os
import shutil
import subprocess
import logging
from typing import Optional, Dict, Any

from media_probe import get_media_info
from media_limits import calculate_timeout

logger = logging.getLogger("himshiksha.audio_converter")

FFMPEG_BIN = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"


class AudioConversionError(Exception):
    pass


# Map format name to optimal FFmpeg codec and container flags
AUDIO_CODEC_MAP: Dict[str, Dict[str, Any]] = {
    "mp3": {
        "codec": "libmp3lame",
        "ext": "mp3",
        "mime": "audio/mpeg",
        "default_bitrate": "192k",
        "extra_args": ["-id3v2_version", "3"]
    },
    "wav": {
        "codec": "pcm_s16le",
        "ext": "wav",
        "mime": "audio/wav",
        "default_bitrate": None,
        "extra_args": []
    },
    "aac": {
        "codec": "aac",
        "ext": "aac",
        "mime": "audio/aac",
        "default_bitrate": "192k",
        "extra_args": []
    },
    "m4a": {
        "codec": "aac",
        "ext": "m4a",
        "mime": "audio/mp4",
        "default_bitrate": "192k",
        "extra_args": ["-f", "ipod"]
    },
    "flac": {
        "codec": "flac",
        "ext": "flac",
        "mime": "audio/flac",
        "default_bitrate": None,
        "extra_args": ["-compression_level", "5"]
    },
    "ogg": {
        "codec": "libvorbis",
        "ext": "ogg",
        "mime": "audio/ogg",
        "default_bitrate": "160k",
        "extra_args": []
    },
    "opus": {
        "codec": "libopus",
        "ext": "opus",
        "mime": "audio/opus",
        "default_bitrate": "128k",
        "extra_args": ["-vbr", "on"]
    },
    "wma": {
        "codec": "wmav2",
        "ext": "wma",
        "mime": "audio/x-ms-wma",
        "default_bitrate": "128k",
        "extra_args": []
    },
    "aiff": {
        "codec": "pcm_s16be",
        "ext": "aiff",
        "mime": "audio/aiff",
        "default_bitrate": None,
        "extra_args": ["-f", "aiff"]
    },
    "amr": {
        "codec": "libopencore_amrnb",
        "ext": "amr",
        "mime": "audio/amr",
        "default_bitrate": "12.2k",
        "extra_args": ["-ar", "8000", "-ac", "1"]
    }
}


def convert_audio(
    input_path: str,
    output_format: str,
    output_path: Optional[str] = None,
    bitrate: Optional[str] = None,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
    timeout: Optional[int] = None
) -> Dict[str, Any]:
    """
    Convert an audio or video file to the specified target audio format.
    Returns metadata dict with output_path, format, size, duration, mime.
    """
    if not os.path.exists(input_path):
        raise AudioConversionError(f"Input file not found: {input_path}")

    fmt = output_format.lower().lstrip(".")
    if fmt not in AUDIO_CODEC_MAP:
        raise AudioConversionError(
            f"Unsupported audio target format: '{output_format}'. Supported formats: {', '.join(AUDIO_CODEC_MAP.keys())}"
        )

    spec = AUDIO_CODEC_MAP[fmt]

    if not output_path:
        base_dir = os.path.dirname(input_path)
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(base_dir, f"{base_name}.{spec['ext']}")

    # Prevent overwriting identical input file
    if os.path.abspath(input_path) == os.path.abspath(output_path):
        output_path = os.path.join(os.path.dirname(input_path), f"converted_{os.path.basename(output_path)}")

    # Calculate timeout if not provided
    input_size = os.path.getsize(input_path)
    if timeout is None:
        timeout = calculate_timeout("audio", input_size)

    # Build FFmpeg command safely using argument list (never shell=True)
    cmd = [
        FFMPEG_BIN,
        "-y",               # Overwrite output without asking
        "-v", "error",       # Log errors only
        "-nostdin",         # Disable standard input
        "-i", input_path,   # Input file
        "-vn"               # Discard any video streams (audio only)
    ]

    # Audio codec selection
    cmd.extend(["-c:a", spec["codec"]])

    # Bitrate
    target_bitrate = bitrate or spec["default_bitrate"]
    if target_bitrate and spec["default_bitrate"]:
        # Normalize e.g. 192 -> 192k
        b_str = str(target_bitrate)
        if not b_str.endswith("k") and not b_str.endswith("K"):
            b_str += "k"
        cmd.extend(["-b:a", b_str])

    # Sample rate (e.g. 44100, 48000)
    if sample_rate and sample_rate in (8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000):
        cmd.extend(["-ar", str(sample_rate)])

    # Channels (1 = mono, 2 = stereo)
    if channels and channels in (1, 2):
        cmd.extend(["-ac", str(channels)])

    # Extra container arguments
    if spec["extra_args"]:
        cmd.extend(spec["extra_args"])

    cmd.append(output_path)

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
        raise AudioConversionError(f"Audio conversion timed out after {timeout} seconds.")
    except Exception as e:
        raise AudioConversionError(f"Failed to execute audio converter: {str(e)}")

    if proc.returncode != 0:
        err = proc.stderr.strip() or f"Process returned error code {proc.returncode}"
        # Clean up partial output
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        raise AudioConversionError(f"FFmpeg audio conversion failed: {err}")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise AudioConversionError("Conversion produced an empty or missing output file.")

    out_size = os.path.getsize(output_path)

    return {
        "output_path": output_path,
        "format": fmt,
        "extension": spec["ext"],
        "mime_type": spec["mime"],
        "size_bytes": out_size,
        "size_mb": round(out_size / (1024 * 1024), 2)
    }
