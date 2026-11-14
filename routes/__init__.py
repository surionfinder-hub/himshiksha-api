"""HimShiksha API Modular Routes Package"""
from routes.health_routes import router as health_router
from routes.pdf_routes import router as pdf_router
from routes.image_routes import router as image_router
from routes.archive_routes import router as archive_router
from routes.office_routes import router as office_router
from routes.media_routes import router as media_router
from routes.print_studio_routes import router as print_studio_router

__all__ = [
    "health_router",
    "pdf_router",
    "image_router",
    "archive_router",
    "office_router",
    "media_router",
    "print_studio_router"
]
