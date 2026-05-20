"""
test_rag.py -- Smoke-test for the full ingest -> retrieve pipeline.

Uses a temporary Chroma directory so tests never pollute the real storage.
The test mocks the Ollama embed call so the suite runs without Ollama running.

What it verifies:
  1. A plain-text document can be ingested.
  2. The same document is not double-ingested (idempotency).
  3. Retrieval returns a chunk whose text includes expected content.
  4. Retrieval on an empty store returns an empty list.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure the local-rag package is importable when running pytest from the repo root
sys.path.insert(0, str(Path(__file__).parents[1]))

from rag_core.config import RAGSettings
from rag_core.ingest import ingest_file
from rag_core.retriever import retrieve
from rag_core.vector_store import VectorStore


SAMPLE_TEXT = (
    "The Retrieval-Augmented Generation (RAG) pattern grounds LLM answers in "
    "retrieved documents, reducing hallucinations and enabling citation. "
    "ChromaDB is a lightweight vector database that persists embeddings to disk. "
    "nomic-embed-text is an open-source embedding model designed for high-quality "
    "semantic search."
)

FAKE_EMBEDDING = [0.1] * 768  # nomic-embed-text produces 768-dim vectors


def make_settings(tmp_path: Path) -> RAGSettings:
    """Return a RAGSettings pointing at a temporary ChromaDB directory."""
    return RAGSettings(
        chroma_path=str(tmp_path / "chroma"),
        collection_name="test_col",
        ollama_host="http://localhost:11434",
        embed_model="nomic-embed-text",
        chunk_size=500,
        chunk_overlap=50,
        top_k=3,
        distance_threshold=2.0,  # wide threshold for test stability
    )


@pytest.fixture()
def sample_doc(tmp_path: Path) -> Path:
    doc = tmp_path / "sample.txt"
    doc.write_text(SAMPLE_TEXT, encoding="utf-8")
    return doc


@pytest.fixture()
def store_settings(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = VectorStore(settings.chroma_path_resolved, settings.collection_name)
    return store, settings


def test_empty_store_retrieval(store_settings):
    """Retrieval on an empty store must return an empty list (not raise)."""
    store, settings = store_settings
    with patch("rag_core.retriever.embed_query", return_value=FAKE_EMBEDDING):
        results = retrieve("What is RAG?", store, settings)
    assert results == []


def test_ingest_creates_chunks(store_settings, sample_doc):
    """Ingesting a text doc should create at least one chunk in the store."""
    store, settings = store_settings
    with patch("rag_core.ingest.embed_texts", return_value=[FAKE_EMBEDDING]):
        counts = ingest_file(sample_doc, store, settings)

    assert counts["added"] >= 1
    assert store.count() >= 1


def test_idempotent_ingest(store_settings, sample_doc):
    """Re-ingesting the same file should add 0 new chunks (pure skip)."""
    store, settings = store_settings
    with patch("rag_core.ingest.embed_texts", return_value=[FAKE_EMBEDDING]):
        first = ingest_file(sample_doc, store, settings)

    with patch("rag_core.ingest.embed_texts", return_value=[FAKE_EMBEDDING]):
        second = ingest_file(sample_doc, store, settings)

    assert second["added"] == 0
    assert second["skipped"] == first["added"]


def test_retrieval_finds_relevant_chunk(store_settings, sample_doc):
    """After ingestion, retrieval should return a chunk containing 'RAG'."""
    store, settings = store_settings
    with patch("rag_core.ingest.embed_texts", return_value=[FAKE_EMBEDDING]):
        ingest_file(sample_doc, store, settings)

    with patch("rag_core.retriever.embed_query", return_value=FAKE_EMBEDDING):
        results = retrieve("What is RAG?", store, settings)

    assert len(results) >= 1
    combined = " ".join(r.text for r in results)
    assert "RAG" in combined or "Retrieval" in combined


def test_list_sources(store_settings, sample_doc):
    """After ingestion, list_sources should include the sample filename."""
    store, settings = store_settings
    with patch("rag_core.ingest.embed_texts", return_value=[FAKE_EMBEDDING]):
        ingest_file(sample_doc, store, settings)

    sources = store.list_sources()
    assert sample_doc.name in sources


def test_reset_clears_store(store_settings, sample_doc):
    """After reset, the store should be empty."""
    store, settings = store_settings
    with patch("rag_core.ingest.embed_texts", return_value=[FAKE_EMBEDDING]):
        ingest_file(sample_doc, store, settings)

    assert store.count() > 0
    store.reset()
    assert store.count() == 0
