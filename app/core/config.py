"""Configuración centralizada y tipada del microservicio mediante Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Entorno general
    app_env: str = Field(default="development", alias="APP_ENV")
    app_port: int = Field(default=8000, alias="APP_PORT")
    api_key: str = Field(default="datamind_api_secret_token_2026", alias="API_KEY")

    # Motor Ollama Local
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    llm_model: str = Field(default="qwen2.5:3b", alias="LLM_MODEL")
    embedding_model: str = Field(default="nomic-embed-text", alias="EMBEDDING_MODEL")
    ollama_timeout_seconds: float = Field(default=60.0, alias="OLLAMA_TIMEOUT_SECONDS")

    # PostgreSQL con pgvector
    postgres_host: str = Field(default="127.0.0.1", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="enterprise_rag", alias="POSTGRES_DB")
    postgres_pool_size: int = Field(default=10, alias="POSTGRES_POOL_SIZE")

    # Base de Datos Relacional Externa por Defecto (Opcional - solo si se especifica)
    mariadb_host: Optional[str] = Field(default=None, alias="MARIADB_HOST")
    mariadb_port: Optional[int] = Field(default=None, alias="MARIADB_PORT")
    mariadb_user: Optional[str] = Field(default=None, alias="MARIADB_USER")
    mariadb_password: Optional[str] = Field(default=None, alias="MARIADB_PASSWORD")
    mariadb_db: Optional[str] = Field(default=None, alias="MARIADB_DB")
    mariadb_max_rows: int = Field(default=500, alias="MARIADB_MAX_ROWS")
    mariadb_timeout_seconds: float = Field(default=5.0, alias="MARIADB_TIMEOUT_SECONDS")

    # Parámetros RAG y Caché de Datasets
    chunk_size: int = Field(default=600, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=80, alias="CHUNK_OVERLAP")
    dataset_cache_ttl_hours: int = Field(default=2, alias="DATASET_CACHE_TTL_HOURS")

    # Aprendizaje Implícito y Memoria Dinámica
    enable_dynamic_knowledge_injection: bool = Field(default=False, alias="ENABLE_DYNAMIC_KNOWLEDGE_INJECTION")
    knowledge_similarity_threshold: float = Field(default=0.75, alias="KNOWLEDGE_SIMILARITY_THRESHOLD")
    knowledge_top_k: int = Field(default=3, alias="KNOWLEDGE_TOP_K")

    @property
    def postgres_async_dsn(self) -> str:
        """DSN para conexión asíncrona mediante asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_sync_dsn(self) -> str:
        """DSN para operaciones síncronas o migraciones."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache()
def get_settings() -> Settings:
    """Retorna una instancia singleton de Settings cargada desde el entorno."""
    return Settings()
