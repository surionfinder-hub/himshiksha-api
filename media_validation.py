"""
HimShiksha - Media Validation and File Signature Detection Module
Validates magic numbers, header signatures, extension consistency, and file integrity.
"""

import os
import re
from typing import Optional, Tuple

# Supported audio format signatures
AUDIO_SIGNATURES = {
    "mp3": [b"ID3", b"\xff\xfb", b"\xff\xfa", b"\xff\xf3", b"\xff\xf2"],
    "wav": [b"RIFF"],   # Followed by 'WAVE' at offset 8
    "flac": [b"fLaC"],
    "ogg": [b"OggS"],
    "opus": [b"OggS"],
    "aiff": [b"FORM"],  # Followed by 'AIFF' or 'AIFC'
    "amr": [b"#!AMR"],
    "wma": [b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"],
    "m4a": [b"ftypM4A", b"ftypmp42", b"ftypisom"]
}

# Supported video format signatures
VIDEO_SIGNATURES = {
    "mp4": [b"ftypisom", b"ftypmp41", b"ftypmp42", b"ftypMSNV", b"ftypavc1", b"ftypdash", b"moov"],
    "mov": [b"ftypqt  ", b"moov", b"free", b"mdat", b"wide"],
    "mkv": [b"\x1a\x45\xdf\xa3"],
    "webm": [b"\x1a\x45\xdf\xa3"],
    "avi": [b"RIFF"],   # Followed by 'AVI ' at offset 8
    "wmv": [b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"],
    "flv": [b"FLV\x01"],
    "3gp": [b"ftyp3gp", b"ftyp3g2"],
    "ts": [b"\x47"],
    "mpg": [b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3"],
}

SUPPORTED_AUDIO_EXTENSIONS = {"mp3", "wav", "aac", "m4a", "flac", "ogg", "opus", "wma", "aiff", "aif", "amr"}
SUPPORTED_VIDEO_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "webm", "wmv", "flv", "mpeg", "mpg", "3gp", "m4v", "ts"}


class MediaValidationError(Exception):
    pass


def sanitize_filename(filename: str, default_ext: str = "bin") -> str:
    """
    Sanitize input filename to avoid path traversal or illegal characters.
    """
    if not filename:
        return f"himshiksha_media.{default_ext}"

    # Extract base name and remove directory separators
    base = os.path.basename(filename).strip()
    # Replace non-alphanumeric (except dot, underscore, hyphen)
    clean = re.sub(r"[^\w.\-_]+", "_", base)
    clean = re.sub(r"_{2,}", "_", clean)

    if not clean or clean.startswith("."):
        clean = f"himshiksha_media.{default_ext}"

    return clean[:128]


def validate_file_signature(file_path: str, claimed_ext: str) -> Tuple[bool, str]:
    """
    Examine magic numbers at the start of the file.
    Returns (is_valid, detected_or_matched_format).
    """
    if not os.path.exists(file_path):
        raise MediaValidationError("File does not exist for validation.")

    file_size = os.path.getsize(file_path)
    if file_size < 16:
        raise MediaValidationError("File is truncated or corrupted (less than 16 bytes).")

    with open(file_path, "rb") as f:
        header = f.read(128)

    ext = claimed_ext.lower().lstrip(".")

    # RIFF container (WAV or AVI)
    if header.startswith(b"RIFF"):
        sub_type = header[8:12]
        if sub_type == b"WAVE":
            return True, "wav"
        if sub_type == b"AVI ":
            return True, "avi"

    # EBML container (MKV or WebM)
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        if ext in ("mkv", "webm"):
            return True, ext
        return True, "mkv"

    # QuickTime / ISO Base Media (MP4, MOV, M4A, 3GP)
    if b"ftyp" in header[:32] or header[4:8] in (b"moov", b"free", b"mdat", b"wide"):
        if ext in ("mp4", "mov", "m4a", "3gp", "m4v"):
            return True, ext
        return True, "mp4"

    # FLAC
    if header.startswith(b"fLaC"):
        return True, "flac"

    # OGG / Opus
    if header.startswith(b"OggS"):
        if ext in ("ogg", "opus"):
            return True, ext
        return True, "ogg"

    # AIFF
    if header.startswith(b"FORM") and header[8:12] in (b"AIFF", b"AIFC"):
        return True, "aiff"

    # AMR
    if header.startswith(b"#!AMR"):
        return True, "amr"

    # FLV
    if header.startswith(b"FLV"):
        return True, "flv"

    # ASF (WMV / WMA)
    if header.startswith(b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"):
        if ext in ("wmv", "wma"):
            return True, ext
        return True, "wmv"

    # MP3 (ID3 or Frame Sync)
    if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
        return True, "mp3"

    # MPEG Video
    if header.startswith(b"\x00\x00\x01\xba") or header.startswith(b"\x00\x00\x01\xb3"):
        return True, "mpg"

    # TS stream
    if header[0] == 0x47 and len(header) >= 188 and header[188] == 0x47:
        return True, "ts"

    # If claimed extension is supported, allow ffprobe to do deep inspection
    if ext in SUPPORTED_AUDIO_EXTENSIONS or ext in SUPPORTED_VIDEO_EXTENSIONS:
        return True, ext

    return False, "unknown"
