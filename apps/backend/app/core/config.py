from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Answer Assistant"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./data/interview_assistant.db"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    ollama_host: str = "http://localhost:11434"
    default_provider: str = "ollama"
    default_model: str = "llama3"
    default_mode: str = "interview"
    whisper_model: str = "base"
    local_only: bool = False
    transcript_persistence: bool = False
    transcript_context_segments: int = 60
    interview_auth_token: str | None = None
    preload_whisper_model: bool = False
    stt_silence_frames: int = 2
    stt_partial_trigger_seconds: float = 2.0
    stt_partial_cooldown_seconds: float = 1.5
    log_level: str = "INFO"

    # RAG — local-rag/ module integration
    rag_enabled: bool = True
    rag_chroma_path: str = "./local-rag/storage"
    rag_collection_name: str = "documents"
    rag_embed_model: str = "nomic-embed-text"
    rag_llm_model: str = "llama3.1:8b"
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_top_k: int = 4
    rag_distance_threshold: float = 1.4
    rag_temperature: float = 0.2
    cors_origins: list[str] = ["http://localhost:5173"]

    # Question Detector — auto-answering from audio transcripts
    qd_enabled: bool = True
    qd_confidence_threshold: float = 0.6
    qd_min_words: int = 4
    qd_dedup_window_seconds: float = 30.0
    qd_dedup_similarity_threshold: float = 0.85
    qd_model: str = "llama3"
    qd_topic_shift_min_words: int = 6
    qd_cooldown_seconds: float = 5.0
    qd_log_detections: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sqlite_path(self) -> Path | None:
        prefix = "sqlite+aiosqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        return Path(self.database_url.removeprefix(prefix))

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
