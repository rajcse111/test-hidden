"""
config.py — Single source of truth for all RAG tunables.

Loaded from a .env file (or environment variables) via pydantic-settings.
Every other module imports from here; nothing hardcodes values directly.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGSettings(BaseSettings):
    # Ollama server
    ollama_host: str = "http://localhost:11434"

    # Models
    llm_model: str = "llama3.1:8b"
    embed_model: str = "nomic-embed-text"

    # ChromaDB persistence directory — defaults to local-rag/storage/ next to this package
    chroma_path: str = str(Path(__file__).parent.parent / "storage")
    collection_name: str = "documents"

    # Chunking
    chunk_size: int = 800
    chunk_overlap: int = 120

    # Retrieval
    top_k: int = 4
    # Cosine distance threshold: ChromaDB returns distance (0=identical, 2=opposite).
    # Chunks above this distance are too dissimilar and are dropped.
    retrieval_distance_threshold: float = 1.4

    # Generation
    temperature: float = 0.2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def chroma_path_resolved(self) -> Path:
        return Path(self.chroma_path).expanduser().resolve()


_settings: RAGSettings | None = None


def get_settings() -> RAGSettings:
    """Return a cached RAGSettings instance (safe to call repeatedly)."""
    global _settings
    if _settings is None:
        _settings = RAGSettings()
    return _settings
