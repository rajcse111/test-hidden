"""
vector_store.py — Thin ChromaDB wrapper.

Keeps ChromaDB details isolated here so the rest of the codebase never
imports chromadb directly.  Swapping to Qdrant later only requires
rewriting this file.

Uses a PersistentClient so the collection survives restarts — ingestion is
done once, not on every run.

Cosine similarity: we use HNSW with cosine distance so shorter/longer
documents don't dominate by raw dot-product magnitude.
"""

from pathlib import Path
from typing import Any


class RetrievedChunk:
    """A chunk returned from a similarity search, with its metadata and score."""

    def __init__(self, text: str, metadata: dict[str, Any], distance: float):
        self.text = text
        self.metadata = metadata
        self.distance = distance  # 0 = identical, 2 = opposite (cosine)

    @property
    def source(self) -> str:
        return str(self.metadata.get("source", "unknown"))

    @property
    def page(self) -> str | int:
        return self.metadata.get("page", "?")


class VectorStore:
    """ChromaDB collection wrapper with upsert, query, reset, and list operations."""

    def __init__(self, chroma_path: Path | str, collection_name: str):
        try:
            import chromadb
        except ImportError:
            raise ImportError("Run: pip install chromadb")

        self._path = Path(chroma_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._path))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},  # cosine distance for all queries
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert or update chunks by their id (upsert = no duplicates on re-ingest)."""
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def reset(self) -> None:
        """Delete the entire collection.  Call from CLI `reset` command."""
        name = self._collection.name
        self._client.delete_collection(name)
        self._collection = self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def query(
        self,
        query_embedding: list[float],
        k: int = 4,
    ) -> list[RetrievedChunk]:
        """Return the k most similar chunks to the query embedding.

        Args:
            query_embedding: Vector produced by embed_query().
            k: Maximum number of results.  Actual results may be fewer if
               the collection has fewer than k chunks.

        Returns:
            List of RetrievedChunk sorted by ascending distance (best first).
        """
        n = min(k, self.count())
        if n == 0:
            return []
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        chunks: list[RetrievedChunk] = []
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]
        for doc, meta, dist in zip(docs, metas, dists):
            chunks.append(RetrievedChunk(text=doc, metadata=meta, distance=dist))
        return chunks

    def count(self) -> int:
        """Return total number of chunks currently stored."""
        return self._collection.count()

    def list_sources(self) -> list[str]:
        """Return deduplicated list of source filenames in the collection."""
        if self.count() == 0:
            return []
        result = self._collection.get(include=["metadatas"])
        sources: set[str] = set()
        for meta in result["metadatas"]:
            src = meta.get("source")
            if src:
                sources.add(str(src))
        return sorted(sources)

    def ids_for_file(self, filename: str) -> list[str]:
        """Return all chunk IDs whose source metadata matches filename."""
        if self.count() == 0:
            return []
        result = self._collection.get(
            where={"source": filename},
            include=["metadatas"],
        )
        return result["ids"]
