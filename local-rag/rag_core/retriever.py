"""
retriever.py — Embed a query and fetch the most relevant chunks.

Uses keyword-gated semantic search: topic words are extracted from the
question, ChromaDB's where_document filter restricts candidates to chunks
that literally contain those words, and then cosine similarity ranks within
that filtered set. This prevents format similarity ("What is X?" patterns)
from overriding content similarity on Q&A documents.

Falls back to pure semantic search when no chunks match the keyword filter,
so paraphrase queries and non-technical questions still get results.

The distance threshold filters out chunks that are too dissimilar to be
useful. Without this, even a question with no relevant document would
return the k "least bad" chunks, leading to hallucinated answers.
"""

import re

from rag_core.config import RAGSettings
from rag_core.embeddings import embed_query
from rag_core.vector_store import RetrievedChunk, VectorStore

# Common question words, articles, and prepositions stripped before keyword extraction.
_STOP_WORDS = frozenset({
    "what", "is", "the", "a", "an", "how", "why", "when", "where",
    "does", "do", "are", "can", "could", "would", "should", "explain",
    "describe", "define", "tell", "me", "about", "difference", "between",
    "and", "or", "in", "of", "to", "for", "vs", "with", "was", "were",
    "has", "have", "had", "will", "be", "been", "by", "at", "from",
    "give", "list", "name", "compare", "use", "used", "using", "work",
    "works", "working", "make", "get", "set",
})


def _extract_keyword(question: str) -> str | None:
    """Return a keyword phrase from the question for pre-filtering ChromaDB candidates.

    Strips punctuation, removes stop words, and joins the remaining content
    words. Returns None when the result would be empty or trivially short.

    Examples:
        "What is the Java Memory Model?" → "Java Memory Model"
        "What is JMM?"                   → "JMM"
        "How does HashMap work?"         → "HashMap"
        "Explain happens-before"         → "happens-before"
    """
    words = re.sub(r"[^\w\s-]", "", question).split()
    content = [w for w in words if w.lower() not in _STOP_WORDS and len(w) > 1]
    if not content:
        return None
    return " ".join(content)


def retrieve(
    question: str,
    store: VectorStore,
    settings: RAGSettings,
) -> list[RetrievedChunk]:
    """Return the top-k most relevant chunks for a question.

    Args:
        question: The user's natural-language query.
        store: Initialised VectorStore instance.
        settings: RAGSettings (uses top_k, distance_threshold,
                  embed_model, ollama_host).

    Returns:
        List of RetrievedChunk sorted by ascending distance (best first),
        filtered to distance <= distance_threshold.
        Empty list when no documents are ingested or nothing is relevant.
    """
    if store.count() == 0:
        return []

    query_vector = embed_query(question, settings.embed_model, settings.ollama_host)

    # Keyword-gated semantic search: restrict candidates to chunks containing
    # the topic phrase, then rank by cosine distance within that set.
    keyword = _extract_keyword(question)
    raw: list[RetrievedChunk] = []
    if keyword:
        try:
            raw = store.query(query_vector, k=settings.top_k, keyword_filter=keyword)
        except Exception:
            raw = []
    # Fallback to pure semantic when keyword filter returns nothing or question
    # has no extractable content words.
    if not raw:
        raw = store.query(query_vector, k=settings.top_k)

    # Apply distance threshold — drop anything too dissimilar
    filtered = [c for c in raw if c.distance <= settings.distance_threshold]
    return filtered
