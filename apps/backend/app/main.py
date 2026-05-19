from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.websocket import router as ws_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import init_db
from app.services.ocr import OcrService
from app.services.runtime import RuntimeState
from app.services.session_manager import SessionManager
from app.services.stt import WhisperService


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
    yield


app = FastAPI(title="AI Interview Assistant API", version="0.1.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
