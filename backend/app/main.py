from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers

settings = get_settings()

app = FastAPI(
    title="Savo SiteScout API",
    version="0.1.0",
    description="Expansion intelligence for Savomart Chennai: area → property → catchment.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(api_router)

media = Path(settings.media_dir)
media.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=media), name="media")
