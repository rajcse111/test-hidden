"""
rag_retriever.py -- Bridges the backend Settings to the local-rag library.

Builds a RAGSettings from the backend's Settings, initialises VectorStore,
and exposes retrieve() and ingest_file() with graceful degradation when the
local-rag package is not importable (RAG disabled silently).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from app.core.config import Settings

# Insert local-rag into the import path at module load time.
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

# Module-level VectorStore cache. Invalidated when the document count changes so
# that documents ingested by Streamlit (or any other process) are always visible,
# while avoiding the ~100 ms ChromaDB init cost on every query.
_store_cache: "VectorStore | None" = None
_store_cache_count: int = -1


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
        distance_threshold=settings.rag_distance_threshold,
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


def _get_or_refresh_store(settings: "Settings") -> "VectorStore | None":
    """Return the cached VectorStore, recreating it only when the document count changes.

    ChromaDB's HNSW index is held in memory after the first open. Reusing the same
    VectorStore avoids ~100 ms of disk I/O per query. The count check detects when
    documents are added (by Streamlit or the documents API) and triggers a reload.
    """
    global _store_cache, _store_cache_count
    if _store_cache is not None:
        try:
            current_count = _store_cache.count()
            if current_count == _store_cache_count and current_count > 0:
                return _store_cache
        except Exception:
            pass
    # Cache miss, empty store, or count changed -- reload HNSW from disk.
    _store_cache = make_vector_store(settings)
    _store_cache_count = _store_cache.count() if _store_cache else 0
    return _store_cache


def warmup_embed_model(settings: "Settings") -> None:
    """Pre-load nomic-embed-text in Ollama to eliminate cold-start on first query.

    Called once at backend startup in a thread executor (non-blocking).
    """
    if not _RAG_AVAILABLE:
        return
    rag_settings = make_rag_settings(settings)
    if rag_settings is None:
        return
    try:
        from rag_core.embeddings import embed_query
        embed_query("warmup", rag_settings.embed_model, rag_settings.ollama_host)
        logger.info("RAG embed model warmed up | model={}", rag_settings.embed_model)
    except Exception as exc:
        logger.debug("RAG embed warmup skipped (Ollama not ready) | error={}", exc)


def retrieve_chunks(
    question: str,
    store: Any,  # kept for API compatibility; internal cache is used instead
    settings: "Settings",
) -> list[dict[str, Any]]:
    """Retrieve top-k chunks for a question.

    Uses a cached VectorStore that is only reloaded when the document count changes,
    so cross-process ingestion (Streamlit) is visible without per-query disk I/O.
    """
    if not _RAG_AVAILABLE:
        return []
    rag_settings = make_rag_settings(settings)
    if rag_settings is None:
        return []
    cached_store = _get_or_refresh_store(settings)
    if cached_store is None:
        return []
    try:
        chunks = _retrieve(question, cached_store, rag_settings)
        if not chunks:
            logger.info("RAG: no relevant chunks found, LLM will answer from general knowledge | question={!r}", question[:60])
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
