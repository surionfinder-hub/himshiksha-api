"""
HimShiksha API - Media (Audio & Video) Endpoints
Supports up to 5 GB (5,368,709,120 bytes) via chunked upload manager and live FFmpeg transcoding.
"""

import os
import json
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import StreamingResponse

from utils.security import verify_api_key, sanitize_filename, make_content_disposition
from utils.file_validation import LIMIT_5GB_BYTES
from utils.upload_handler import save_upload_to_disk
from utils.cleanup import remove_file_silent

import chunk_manager
import media_jobs
from media_probe import get_media_info
from video_converter import convert_video, VIDEO_TARGET_SPECS
from audio_converter import convert_audio, AUDIO_CODEC_MAP
from media_limits import CATEGORY_LIMITS

router = APIRouter(tags=["Media Audio & Video"])


def stream_file_and_cleanup(file_path: str):
    """Generator to stream file in 64KB chunks and delete upon completion."""
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk
    finally:
        remove_file_silent(file_path)


# 1. Media Configuration Limits
@router.get("/api/media/limits")
async def get_media_limits_endpoint():
    return {
        "status": "active",
        "limits": {
            "images_max_bytes": CATEGORY_LIMITS["images"],
            "images_max_mb": CATEGORY_LIMITS["images"] // (1024 * 1024),
            "pdf_docs_max_bytes": CATEGORY_LIMITS["pdf_docs"],
            "pdf_docs_max_mb": CATEGORY_LIMITS["pdf_docs"] // (1024 * 1024),
            "office_max_bytes": CATEGORY_LIMITS["office"],
            "office_max_mb": CATEGORY_LIMITS["office"] // (1024 * 1024),
            "audio_max_bytes": CATEGORY_LIMITS["audio"],
            "audio_max_mb": CATEGORY_LIMITS["audio"] // (1024 * 1024),
            "video_max_bytes": CATEGORY_LIMITS["video"],
            "video_max_mb": CATEGORY_LIMITS["video"] // (1024 * 1024)
        },
        "supported_audio_formats": list(AUDIO_CODEC_MAP.keys()),
        "supported_video_formats": list(VIDEO_TARGET_SPECS.keys())
    }


# 2. Media Metadata Probe
@router.post("/api/media/probe")
async def probe_media_endpoint(
    file: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    spooled_path = await save_upload_to_disk(file, max_bytes=LIMIT_5GB_BYTES, suffix="_probe.tmp")
    try:
        info = get_media_info(spooled_path)
        return {"success": True, "info": info}
    finally:
        remove_file_silent(spooled_path)


# 3. Unified Audio Converter
@router.post("/api/convert/audio")
async def convert_audio_endpoint(
    file: UploadFile = File(...),
    target_format: str = Form("mp3"),
    bitrate: Optional[str] = Form(None),
    sample_rate: Optional[int] = Form(None),
    channels: Optional[int] = Form(None),
    async_mode: bool = Form(False),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    spooled_path = await save_upload_to_disk(file, max_bytes=LIMIT_5GB_BYTES, suffix=f"_{file.filename}")
    file_size = os.path.getsize(spooled_path)

    if async_mode or file_size > (10 * 1024 * 1024):
        job_id = media_jobs.create_job(
            media_type="audio",
            input_path=spooled_path,
            output_format=target_format,
            original_filename=file.filename or "audio_input",
            options={"bitrate": bitrate, "sample_rate": sample_rate, "channels": channels}
        )
        return {
            "success": True,
            "async": True,
            "job_id": job_id,
            "status": "queued",
            "message": "Audio conversion is processing in background.",
            "status_url": f"/api/media/jobs/{job_id}",
            "download_url": f"/api/media/jobs/{job_id}/download"
        }

    try:
        result = convert_audio(
            input_path=spooled_path,
            output_format=target_format,
            bitrate=bitrate,
            sample_rate=sample_rate,
            channels=channels
        )
    finally:
        remove_file_silent(spooled_path)

    out_path = result["output_path"]
    base = sanitize_filename(os.path.splitext(file.filename or "audio")[0])
    out_filename = f"{base}.{result['extension']}"

    return StreamingResponse(
        stream_file_and_cleanup(out_path),
        media_type=result["mime_type"],
        headers={
            "Content-Disposition": make_content_disposition(out_filename),
            "X-Format": result["format"],
            "X-Output-Bytes": str(result["size_bytes"]),
            "Access-Control-Expose-Headers": "X-Format, X-Output-Bytes"
        }
    )


# 4. Unified Video Converter
@router.post("/api/convert/video")
async def convert_video_endpoint(
    file: UploadFile = File(...),
    target_format: str = Form("mp4"),
    resolution: Optional[str] = Form(None),
    preset: str = Form("fast"),
    crf: int = Form(23),
    async_mode: bool = Form(False),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    spooled_path = await save_upload_to_disk(file, max_bytes=LIMIT_5GB_BYTES, suffix=f"_{file.filename}")
    file_size = os.path.getsize(spooled_path)

    if async_mode or file_size > (25 * 1024 * 1024):
        job_id = media_jobs.create_job(
            media_type="video",
            input_path=spooled_path,
            output_format=target_format,
            original_filename=file.filename or "video_input",
            options={"resolution": resolution, "preset": preset, "crf": crf}
        )
        return {
            "success": True,
            "async": True,
            "job_id": job_id,
            "status": "processing",
            "message": "Video conversion is processing in background. Poll /api/media/jobs/{job_id} for status.",
            "status_url": f"/api/media/jobs/{job_id}",
            "download_url": f"/api/media/jobs/{job_id}/download"
        }

    try:
        result = convert_video(
            input_path=spooled_path,
            output_format=target_format,
            resolution=resolution,
            preset=preset,
            crf=crf
        )
    finally:
        remove_file_silent(spooled_path)

    out_path = result["output_path"]
    base = sanitize_filename(os.path.splitext(file.filename or "video")[0])
    out_filename = f"{base}.{result['extension']}"

    return StreamingResponse(
        stream_file_and_cleanup(out_path),
        media_type=result["mime_type"],
        headers={
            "Content-Disposition": make_content_disposition(out_filename),
            "X-Format": result["format"],
            "X-Output-Bytes": str(result["size_bytes"]),
            "X-Mode": result["conversion_mode"],
            "Access-Control-Expose-Headers": "X-Format, X-Output-Bytes, X-Mode"
        }
    )


# 5. Chunked Upload Endpoints
@router.post("/api/media/upload/chunk-init")
async def chunk_init_endpoint(
    upload_id: str = Form(...),
    filename: str = Form(...),
    total_size: int = Form(...),
    total_chunks: int = Form(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    try:
        meta = chunk_manager.init_chunked_upload(upload_id, filename, total_size, total_chunks)
        return {"success": True, "meta": meta}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/media/upload/chunk-append")
async def chunk_append_endpoint(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk_data: UploadFile = File(...),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    try:
        content = await chunk_data.read()
        meta = chunk_manager.append_chunk(upload_id, chunk_index, content)
        return {"success": True, "meta": meta}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/media/upload/chunk-complete")
async def chunk_complete_endpoint(
    upload_id: str = Form(...),
    media_type: str = Form("video"),
    target_format: str = Form("mp4"),
    options: Optional[str] = Form(None),
    x_himshiksha_key: Optional[str] = Header(None)
):
    verify_api_key(x_himshiksha_key)
    try:
        assembled_path = chunk_manager.finalize_chunked_upload(upload_id)
        parsed_opts = json.loads(options) if options else {}
        job_id = media_jobs.create_job(
            media_type=media_type,
            input_path=assembled_path,
            output_format=target_format,
            original_filename=os.path.basename(assembled_path),
            options=parsed_opts
        )
        return {
            "success": True,
            "async": True,
            "job_id": job_id,
            "status": "queued",
            "status_url": f"/api/media/jobs/{job_id}",
            "download_url": f"/api/media/jobs/{job_id}/download"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# 6. Job Status, Cancel & Download Endpoints
@router.get("/api/media/jobs/{job_id}")
async def get_media_job_status(job_id: str, x_himshiksha_key: Optional[str] = Header(None)):
    verify_api_key(x_himshiksha_key)
    job = media_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return {"success": True, "job": job}


@router.post("/api/media/jobs/{job_id}/cancel")
async def cancel_media_job_endpoint(job_id: str, x_himshiksha_key: Optional[str] = Header(None)):
    verify_api_key(x_himshiksha_key)
    success = media_jobs.cancel_job(job_id)
    return {"success": success, "message": "Job cancelled successfully" if success else "Could not cancel job"}


@router.get("/api/media/jobs/{job_id}/download")
async def download_media_job_output(job_id: str, x_himshiksha_key: Optional[str] = Header(None)):
    verify_api_key(x_himshiksha_key)
    out_path = media_jobs.get_job_output_path(job_id)
    if not out_path or not os.path.exists(out_path):
        raise HTTPException(status_code=404, detail="Output file not ready or job expired.")

    job = media_jobs.get_job(job_id) or {}
    orig_name = job.get("original_filename", "media_output")
    fmt = job.get("output_format", "bin")
    base = sanitize_filename(os.path.splitext(orig_name)[0])
    out_filename = f"{base}.{fmt}"

    mime = "application/octet-stream"
    if fmt in AUDIO_CODEC_MAP:
        mime = AUDIO_CODEC_MAP[fmt]["mime"]
    elif fmt in VIDEO_TARGET_SPECS:
        mime = VIDEO_TARGET_SPECS[fmt]["mime"]

    return StreamingResponse(
        stream_file_and_cleanup(out_path),
        media_type=mime,
        headers={"Content-Disposition": make_content_disposition(out_filename)}
    )


# 7. Dedicated Tool Endpoints (Aliases for Specific Converter Routes)
@router.post("/api/convert/audio-to-mp3")
async def convert_audio_to_mp3(file: UploadFile = File(...), bitrate: Optional[str] = Form(None), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_audio_endpoint(file=file, target_format="mp3", bitrate=bitrate, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/audio-to-wav")
async def convert_audio_to_wav(file: UploadFile = File(...), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_audio_endpoint(file=file, target_format="wav", x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/audio-to-aac")
async def convert_audio_to_aac(file: UploadFile = File(...), bitrate: Optional[str] = Form(None), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_audio_endpoint(file=file, target_format="aac", bitrate=bitrate, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/audio-to-flac")
async def convert_audio_to_flac(file: UploadFile = File(...), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_audio_endpoint(file=file, target_format="flac", x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/audio-to-ogg")
async def convert_audio_to_ogg(file: UploadFile = File(...), bitrate: Optional[str] = Form(None), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_audio_endpoint(file=file, target_format="ogg", bitrate=bitrate, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/audio-to-m4a")
async def convert_audio_to_m4a(file: UploadFile = File(...), bitrate: Optional[str] = Form(None), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_audio_endpoint(file=file, target_format="m4a", bitrate=bitrate, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/video-to-mp4")
async def convert_video_to_mp4(file: UploadFile = File(...), resolution: Optional[str] = Form(None), async_mode: bool = Form(False), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_video_endpoint(file=file, target_format="mp4", resolution=resolution, async_mode=async_mode, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/video-to-webm")
async def convert_video_to_webm(file: UploadFile = File(...), resolution: Optional[str] = Form(None), async_mode: bool = Form(False), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_video_endpoint(file=file, target_format="webm", resolution=resolution, async_mode=async_mode, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/video-to-mkv")
async def convert_video_to_mkv(file: UploadFile = File(...), resolution: Optional[str] = Form(None), async_mode: bool = Form(False), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_video_endpoint(file=file, target_format="mkv", resolution=resolution, async_mode=async_mode, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/video-to-avi")
async def convert_video_to_avi(file: UploadFile = File(...), resolution: Optional[str] = Form(None), async_mode: bool = Form(False), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_video_endpoint(file=file, target_format="avi", resolution=resolution, async_mode=async_mode, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/video-to-mov")
async def convert_video_to_mov(file: UploadFile = File(...), resolution: Optional[str] = Form(None), async_mode: bool = Form(False), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_video_endpoint(file=file, target_format="mov", resolution=resolution, async_mode=async_mode, x_himshiksha_key=x_himshiksha_key)

@router.post("/api/convert/video-extract-audio")
async def convert_video_extract_audio(file: UploadFile = File(...), target_format: str = Form("mp3"), bitrate: Optional[str] = Form("192k"), x_himshiksha_key: Optional[str] = Header(None)):
    return await convert_audio_endpoint(file=file, target_format=target_format, bitrate=bitrate, x_himshiksha_key=x_himshiksha_key)
