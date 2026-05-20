from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.documents import router as documents_router
from app.api.routes import router as api_router
from app.api.websocket import router as ws_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import init_db
from app.services.ocr import OcrService
from app.services.rag_retriever import is_available as rag_available
from app.services.rag_retriever import make_vector_store
from app.services.runtime import RuntimeState
from app.services.session_manager import SessionManager
from app.services.stt import WhisperService
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    await init_db()
    app.state.runtime = RuntimeState(settings=settings)
    app.state.session_manager = SessionManager()
    app.state.ocr = OcrService()
    app.state.stt = WhisperService(settings)
    if settings.preload_whisper_model:
        _ = app.state.stt.model

    # RAG vector store — optional; degrades gracefully if local-rag/ is absent
    app.state.rag_store = None
    if settings.rag_enabled and rag_available():
        try:
            app.state.rag_store = make_vector_store(settings)
            count = app.state.rag_store.count() if app.state.rag_store else 0
            resolved_path = Path(settings.rag_chroma_path).expanduser().resolve()
            logger.info("RAG store initialised | chunks={} path={}", count, resolved_path)
        except Exception as exc:
            logger.warning("RAG store init failed (continuing without RAG) | error={}", exc)
            app.state.rag_store = None
    else:
        logger.info("RAG disabled (rag_enabled=False or local-rag not installed)")

    yield


app = FastAPI(title="AI Answer Assistant API", version="0.1.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(documents_router, prefix="/api/documents")
app.include_router(ws_router, prefix="/ws")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
