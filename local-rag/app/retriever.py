"""
retriever.py — Embed a query and fetch the most relevant chunks.

The distance threshold filters out chunks that are too dissimilar to be
useful.  Without this, even a question with no relevant document would
return the k "least bad" chunks, leading to hallucinated answers.

Early-exit when the collection is empty avoids a needless embed call
and provides a clear signal to the RAG layer that no documents exist yet.
"""

from app.config import RAGSettings
from app.embeddings import embed_query
from app.vector_store import RetrievedChunk, VectorStore


def retrieve(
    question: str,
    store: VectorStore,
    settings: RAGSettings,
) -> list[RetrievedChunk]:
    """Return the top-k most relevant chunks for a question.

    Args:
        question: The user's natural-language query.
        store: Initialised VectorStore instance.
        settings: RAGSettings (uses top_k, retrieval_distance_threshold,
                  embed_model, ollama_host).

    Returns:
        List of RetrievedChunk sorted by ascending distance (best first),
        filtered to distance <= retrieval_distance_threshold.
        Empty list when no documents are ingested or nothing is relevant.
    """
    if store.count() == 0:
        return []

    query_vector = embed_query(question, settings.embed_model, settings.ollama_host)
    raw = store.query(query_vector, k=settings.top_k)

    # Apply distance threshold — drop anything too dissimilar
    filtered = [c for c in raw if c.distance <= settings.retrieval_distance_threshold]
    return filtered
