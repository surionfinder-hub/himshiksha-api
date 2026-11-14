"""
HimShiksha Python Engine - Main Application Entrypoint
Modular FastAPI architecture connecting PDF, Image, Archive, Office, Media, and Print Studio engines.
"""

import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes import (
    health_router,
    pdf_router,
    image_router,
    archive_router,
    office_router,
    media_router,
    print_studio_router
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("himshiksha.api")

app = FastAPI(
    title="HimShiksha Python Conversion API",
    description="Modular high-performance backend supporting 2GB PDF/Image/Archive tools and 5GB Media Transcoding.",
    version="2.0.0"
)

# Enable CORS for trusted frontend origins and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register modular route collections
app.include_router(health_router)
app.include_router(pdf_router)
app.include_router(image_router)
app.include_router(archive_router)
app.include_router(office_router)
app.include_router(media_router)
app.include_router(print_studio_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error processing {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal conversion engine error: {str(exc)}"}
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting HimShiksha API server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
