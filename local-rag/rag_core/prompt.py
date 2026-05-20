"""
prompt.py — RAG system prompt template and context builder.

The system prompt explicitly instructs the model to:
  1. Answer ONLY from the provided context snippets.
  2. Cite sources in [filename, page] format.
  3. Admit when the context is insufficient rather than guessing.

Low temperature (set in rag.py / config.py) combined with these instructions
produces grounded, non-hallucinated answers.
"""

from rag_core.vector_store import RetrievedChunk


RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions strictly based on the provided document excerpts.

Rules you MUST follow:
1. Answer ONLY using the information in the context below.
2. Every factual claim must be supported by a context excerpt.
3. Cite sources inline as [filename, page] immediately after the relevant sentence.
4. If the context does not contain enough information to answer, respond with exactly:
   "I don't know based on the provided documents."
5. Do not invent, extrapolate, or rely on prior training knowledge — only use the context.
6. Write in a clear, conversational tone. Avoid bullet-point dumps unless the question explicitly calls for a list.

Context:
{context}"""


def build_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a labeled context block for the prompt.

    Each chunk is prefixed with its source and page so the model can cite
    them and the reader can verify the claim.
    """
    if not chunks:
        return "(no relevant document excerpts found)"

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        header = f"[{i}] Source: {chunk.source}, Page: {chunk.page}"
        parts.append(f"{header}\n{chunk.text}")
    return "\n\n---\n\n".join(parts)


def build_citations(chunks: list[RetrievedChunk]) -> list[dict[str, str | float]]:
    """Build a structured citations list suitable for UI display or JSON response.

    Returns:
        List of dicts with source, page, snippet (first 200 chars), and distance.
    """
    return [
        {
            "source": chunk.source,
            "page": str(chunk.page),
            "snippet": chunk.text[:200].replace("\n", " "),
            "distance": round(chunk.distance, 4),
        }
        for chunk in chunks
    ]


def build_messages(question: str, chunks: list[RetrievedChunk]) -> list[dict[str, str]]:
    """Assemble the full OpenAI-style message list for the LLM.

    Returns:
        [{"role": "system", "content": ...}, {"role": "user", "content": question}]
    """
    context = build_context(chunks)
    system = RAG_SYSTEM_PROMPT.format(context=context)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question.strip()},
    ]
