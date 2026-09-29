from fastapi import APIRouter

from app.api.v1 import areas, auth, ref, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(ref.router)
api_router.include_router(areas.router)
