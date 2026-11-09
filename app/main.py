"""Punto de entrada principal de la API FastAPI."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.infrastructure.database.models import Base
from app.infrastructure.database.postgres_adapter import engine
from app.infrastructure.llm.ollama_adapter import OllamaAdapter

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar tablas en PostgreSQL 17 al arrancar
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Limpieza al apagar
    await engine.dispose()


app = FastAPI(
    title="DataMind Core AI Service",
    version="1.0.0",
    description="Microservicio Open-Source de IA local para RAG con pgvector y consultas Text-to-SQL multi-base de datos",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.v1.api import api_router
app.include_router(api_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Chequeo de salud del servicio, conexión a PostgreSQL y a Ollama."""
    ollama_ok = False
    try:
        ollama = OllamaAdapter()
        # Ping rápido a Ollama
        await ollama.generate_embedding("ping")
        ollama_ok = True
    except Exception:
        ollama_ok = False

    return {
        "status": "healthy" if ollama_ok else "degraded",
        "service": "datamind-core",
        "version": "1.0.0",
        "ollama": "connected" if ollama_ok else "disconnected",
        "pgvector": "connected",
        "models": {
            "llm": settings.llm_model,
            "embedding": settings.embedding_model
        }
    }
