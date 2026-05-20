"""
chunker.py — Splits loader output into overlapping chunks for embedding.

Uses LangChain's RecursiveCharacterTextSplitter, which tries to split on
paragraph → sentence → word boundaries in that priority order, so chunks
stay semantically coherent rather than cutting mid-sentence.

Metadata (source, page) from loaders is carried forward to every child chunk
and a sequential chunk_index is added so each chunk has a unique identity.
"""

from app.loaders import Chunk


def split_chunks(raw_chunks: list[Chunk], chunk_size: int = 800, chunk_overlap: int = 120) -> list[Chunk]:
    """Split raw loader chunks into smaller overlapping pieces.

    Args:
        raw_chunks: Output of any loader in loaders.py.
        chunk_size: Target character count per chunk (not token count).
        chunk_overlap: Characters shared between consecutive chunks to
            preserve sentence context across boundaries.

    Returns:
        Flat list of chunks with carried metadata + chunk_index added.
    """
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        raise ImportError("Run: pip install langchain-text-splitters")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # These separators are tried in order: paragraph > sentence > word > char
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
        length_function=len,
    )

    result: list[Chunk] = []
    for raw in raw_chunks:
        pieces = splitter.split_text(raw["text"])
        for idx, piece in enumerate(pieces):
            piece = piece.strip()
            if len(piece) < 20:  # skip noise fragments
                continue
            result.append({
                "text": piece,
                "metadata": {**raw["metadata"], "chunk_index": idx},
            })
    return result
