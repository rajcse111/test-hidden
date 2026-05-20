"""
embeddings.py — Text → vector conversion via Ollama's nomic-embed-text.

Uses the Ollama /api/embed endpoint directly via httpx (synchronous).
The same model is used for both indexing and querying — this is essential:
mixing models would produce incomparable vectors.

Batching: Ollama's /api/embed accepts a list of strings, so we send all
texts in one HTTP round-trip rather than one request per chunk.

Performance notes:
- A module-level httpx.Client is reused across calls to avoid TCP setup
  overhead on every embed request (~5-15 ms per new connection).
- embed_query results are LRU-cached (32 entries) so identical queries
  skip the ~200 ms network round-trip entirely.
"""

from functools import lru_cache
from typing import Sequence

import httpx

# Persistent client — reused across all embed calls to avoid TCP setup cost.
_http_client: httpx.Client | None = None


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=120.0)
    return _http_client


def embed_texts(texts: Sequence[str], model: str, ollama_host: str) -> list[list[float]]:
    """Embed a batch of texts and return a list of float vectors.

    Args:
        texts: Non-empty list of strings to embed.
        model: Ollama model name (e.g. "nomic-embed-text").
        ollama_host: Base URL of the Ollama server.

    Returns:
        List of embedding vectors, one per input text, in the same order.

    Raises:
        RuntimeError: If Ollama is unreachable or the model is not pulled.
    """
    if not texts:
        return []

    url = f"{ollama_host.rstrip('/')}/api/embed"
    try:
        response = _get_http_client().post(
            url,
            json={"model": model, "input": list(texts)},
        )
        response.raise_for_status()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot reach Ollama at {ollama_host}. "
            "Make sure Ollama is running: `ollama serve`"
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise RuntimeError(
                f"Model '{model}' not found in Ollama. "
                f"Pull it first: `ollama pull {model}`"
            )
        raise RuntimeError(f"Ollama embed request failed: {exc}")

    data = response.json()
    # Ollama returns {"embeddings": [[float, ...]]} for batch input
    embeddings = data.get("embeddings") or data.get("embedding")
    if not embeddings:
        raise RuntimeError(f"Unexpected Ollama embed response: {data}")
    # Normalise: single-text requests may return a flat list
    if isinstance(embeddings[0], float):
        return [embeddings]  # type: ignore[list-item]
    return embeddings


@lru_cache(maxsize=32)
def _embed_query_cached(text: str, model: str, ollama_host: str) -> tuple[float, ...]:
    """Cached embed for a single query string.

    Returns a tuple (hashable) so lru_cache can store it. Repeated questions
    — common in testing or follow-up queries — skip the ~200 ms embed call.
    Cache key includes model and host so changing either busts the cache.
    """
    vectors = embed_texts([text], model, ollama_host)
    return tuple(vectors[0])


def embed_query(text: str, model: str, ollama_host: str) -> list[float]:
    """Embed a single query string — cached convenience wrapper around embed_texts."""
    return list(_embed_query_cached(text, model, ollama_host))
