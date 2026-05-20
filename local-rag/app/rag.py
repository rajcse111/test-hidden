"""
rag.py — Top-level entry point: retrieve + prompt + stream answer.

answer() is the function called by both the CLI and the Streamlit web UI.
It returns a generator of string tokens so both interfaces can stream
output to the user in real time.

The function also returns the retrieved citations as a side-channel so
the caller can display source attributions alongside the streamed answer.
"""

from collections.abc import Iterator
from typing import Any

from app.config import RAGSettings, get_settings
from app.prompt import build_citations, build_messages
from app.retriever import retrieve
from app.vector_store import RetrievedChunk, VectorStore


def answer(
    question: str,
    store: VectorStore,
    settings: RAGSettings | None = None,
) -> tuple[Iterator[str], list[dict[str, Any]]]:
    """Retrieve relevant chunks and stream an answer from Ollama.

    Args:
        question: The user's question.
        store: An initialised VectorStore instance.
        settings: Optional RAGSettings; uses get_settings() if not provided.

    Returns:
        (token_iterator, citations_list)
        token_iterator — yields str tokens as they arrive from Ollama.
        citations_list — list of citation dicts (source, page, snippet, distance).

    The caller should iterate the token_iterator first, then use citations.
    Both are available immediately (citations before any streaming starts).
    """
    if settings is None:
        settings = get_settings()

    chunks: list[RetrievedChunk] = retrieve(question, store, settings)
    citations = build_citations(chunks)
    messages = build_messages(question, chunks)

    token_stream = _stream_ollama(messages, settings)
    return token_stream, citations


def _stream_ollama(
    messages: list[dict[str, str]],
    settings: RAGSettings,
) -> Iterator[str]:
    """Yield text tokens from Ollama's /api/chat endpoint via streaming.

    Uses the official ollama Python client which handles SSE parsing.
    """
    try:
        import ollama
    except ImportError:
        raise ImportError("Run: pip install ollama")

    try:
        stream = ollama.chat(
            model=settings.llm_model,
            messages=messages,
            stream=True,
            options={"temperature": settings.temperature},
        )
        for chunk in stream:
            token = chunk["message"]["content"]
            if token:
                yield token
    except Exception as exc:
        error_str = str(exc).lower()
        if "connection" in error_str or "connect" in error_str:
            raise RuntimeError(
                f"Cannot reach Ollama at {settings.ollama_host}. "
                "Make sure Ollama is running: `ollama serve`"
            )
        if "not found" in error_str or "model" in error_str:
            raise RuntimeError(
                f"Model '{settings.llm_model}' not found. "
                f"Pull it: `ollama pull {settings.llm_model}`"
            )
        raise
