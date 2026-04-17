from __future__ import annotations

import os
from urllib.parse import urlparse

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _sync_pg_components() -> dict[str, str]:
    """
    Parse the asyncpg DATABASE_URL into components for psycopg2-based clients.

    PGVectorStore (LlamaIndex) uses psycopg2 internally, so we need to extract
    host/port/user/password/database from the asyncpg URL format.
    """
    raw = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(raw)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "database": parsed.path.lstrip("/").split("?")[0],
        "user": parsed.username or "",
        "password": parsed.password or "",
    }


def get_embed_model():
    """
    Return a configured HuggingFaceEmbedding instance.

    Model name comes from settings. Runs fully locally — no API key required.
    The model is downloaded once and cached by sentence-transformers.
    """
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # type: ignore[import]

    return HuggingFaceEmbedding(
        model_name=settings.embedding_model,
        embed_batch_size=32,
    )


def get_vector_store():
    """
    Return a PGVectorStore connected to the configured pgvector database.

    Sets PGSSLMODE=require so psycopg2 uses SSL when connecting to Neon.
    Collection name and dimensions come from settings.
    """
    from llama_index.vector_stores.postgres import PGVectorStore  # type: ignore[import]

    # psycopg2 respects this env var for SSL — required for Neon
    os.environ.setdefault("PGSSLMODE", "require")

    parts = _sync_pg_components()
    return PGVectorStore.from_params(
        host=parts["host"],
        port=parts["port"],
        database=parts["database"],
        user=parts["user"],
        password=parts["password"],
        table_name=settings.vector_store_collection_name,
        embed_dim=settings.embedding_dimensions,
        perform_setup=True,
    )


def get_index(embed_model=None):
    """
    Return a VectorStoreIndex backed by the pgvector collection.

    If embed_model is not provided, a new one is created. Reusing the same
    embed_model instance across calls avoids redundant API client setup.
    """
    from llama_index.core import StorageContext, VectorStoreIndex  # type: ignore[import]

    em = embed_model or get_embed_model()
    vs = get_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vs)
    return VectorStoreIndex.from_vector_store(
        vector_store=vs,
        storage_context=storage_context,
        embed_model=em,
    )
