"""
rag_retriever.py — Bridges the backend Settings to the local-rag library.

Builds a RAGSettings from the backend's Settings, initialises VectorStore,
and exposes retrieve() and ingest_file() with graceful degradation when the
local-rag package is not importable (RAG disabled silently).

The VectorStore is created once at app startup (in main.py lifespan) and
stored on app.state.rag_store so all WebSocket connections share it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from app.core.config import Settings

# Insert local-rag into the import path at module load time.
# This module is imported during app startup so the path is set before
# any RAG function is called.
_local_rag_path = Path(__file__).parents[4] / "local-rag"
if str(_local_rag_path) not in sys.path:
    sys.path.insert(0, str(_local_rag_path))

_RAG_AVAILABLE = False
try:
    from rag_core.config import RAGSettings  # local-rag/rag_core/config.py
    from rag_core.retriever import retrieve as _retrieve
    from rag_core.vector_store import VectorStore
    _RAG_AVAILABLE = True
except ImportError:
    pass


def is_available() -> bool:
    """Return True if the local-rag package was successfully imported."""
    return _RAG_AVAILABLE


def make_rag_settings(settings: "Settings") -> "RAGSettings | None":
    """Build a RAGSettings from the backend's Settings object."""
    if not _RAG_AVAILABLE:
        return None
    return RAGSettings(
        ollama_host=settings.ollama_host,
        llm_model=settings.rag_llm_model,
        embed_model=settings.rag_embed_model,
        chroma_path=settings.rag_chroma_path,
        collection_name=settings.rag_collection_name,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        top_k=settings.rag_top_k,
        retrieval_distance_threshold=settings.rag_distance_threshold,
        temperature=settings.rag_temperature,
    )


def make_vector_store(settings: "Settings") -> "VectorStore | None":
    """Create and return a VectorStore, or None if RAG is unavailable."""
    if not _RAG_AVAILABLE:
        return None
    rag_settings = make_rag_settings(settings)
    if rag_settings is None:
        return None
    return VectorStore(rag_settings.chroma_path_resolved, rag_settings.collection_name)


def retrieve_chunks(
    question: str,
    store: Any,  # kept for API compatibility; a fresh store is created per call
    settings: "Settings",
) -> list[dict[str, Any]]:
    """Retrieve top-k chunks for a question.

    Returns an empty list if RAG is unavailable or no chunks pass the distance threshold.
    Creates a fresh VectorStore on every call so that documents ingested by other
    processes (e.g. Streamlit) are always visible — avoids stale in-memory HNSW index.
    """
    if not _RAG_AVAILABLE:
        return []
    rag_settings = make_rag_settings(settings)
    if rag_settings is None:
        return []
    fresh_store = make_vector_store(settings)
    if fresh_store is None:
        return []
    try:
        chunks = _retrieve(question, fresh_store, rag_settings)
        if not chunks:
            logger.debug("RAG: no chunks above distance threshold | question={!r}", question[:60])
            return []
        return [
            {
                "text": c.text,
                "source": c.source,
                "page": str(c.page),
                "distance": round(c.distance, 4),
            }
            for c in chunks
        ]
    except Exception as exc:
        logger.warning("RAG retrieve_chunks failed | error={}", exc)
        return []


def get_document_count(store: Any) -> int:
    """Return chunk count from the store, or 0 if unavailable."""
    if not _RAG_AVAILABLE or store is None:
        return 0
    try:
        return store.count()
    except Exception:
        return 0


def list_document_sources(store: Any) -> list[str]:
    """Return list of ingested source filenames, or [] if unavailable."""
    if not _RAG_AVAILABLE or store is None:
        return []
    try:
        return store.list_sources()
    except Exception:
        return []
