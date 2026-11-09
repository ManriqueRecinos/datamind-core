"""Agrupador de routers de la versión 1 de la API."""

from fastapi import APIRouter
from app.api.v1.routers.chat import router as chat_router
from app.api.v1.routers.connections import router as connections_router
from app.api.v1.routers.export import router as export_router
from app.api.v1.routers.knowledge import router as knowledge_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat_router)
api_router.include_router(connections_router)
api_router.include_router(knowledge_router)
api_router.include_router(export_router)
