from datetime import UTC, datetime

import httpx
from app.core.config import Settings
from app.db import get_db
from app.models import Session, Setting
from app.schemas import ModelInfo, OcrRequest, OcrResponse, SessionResponse, SessionStartRequest, SettingsPayload
from app.services.session_manager import LiveSession, SessionManager
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_runtime_settings(request: Request) -> Settings:
    return request.app.state.runtime.settings


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager


async def enforce_auth(
    settings: Settings = Depends(get_runtime_settings),
    x_interview_token: str | None = Header(default=None),
) -> None:
    if settings.interview_auth_token and x_interview_token != settings.interview_auth_token:
        raise HTTPException(status_code=401, detail="Invalid interview token")


@router.get("/models", response_model=list[ModelInfo])
async def models(settings: Settings = Depends(get_runtime_settings)) -> list[ModelInfo]:
    known = [
        ModelInfo(provider="openai", id="gpt-4.1"),
        ModelInfo(provider="openai", id="gpt-4o"),
        ModelInfo(provider="gemini", id="gemini-2.5-pro"),
        ModelInfo(provider="anthropic", id="claude-opus-5"),
        ModelInfo(provider="anthropic", id="claude-sonnet-5"),
        ModelInfo(provider="anthropic", id="claude-haiku-4-5"),
        ModelInfo(provider="openrouter", id="deepseek/deepseek-chat"),
        ModelInfo(provider="ollama", id="llama3", local=True),
        ModelInfo(provider="ollama", id="qwen2.5", local=True),
        ModelInfo(provider="ollama", id="deepseek-r1", local=True),
    ]
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            response.raise_for_status()
            for model in response.json().get("models", []):
                known.append(ModelInfo(provider="ollama", id=model["name"], local=True))
    except Exception:
        pass
    return known


@router.post("/settings")
async def save_settings(
    payload: SettingsPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(enforce_auth),
) -> dict[str, str]:
    now = datetime.now(UTC)
    values = payload.model_dump(exclude_none=True)
    for key, value in values.items():
        await db.merge(Setting(key=key, value=str(value), updated_at=now))
    await db.commit()
    request.app.state.runtime.update(values)
    return {"status": "ok"}


@router.post("/ocr", response_model=OcrResponse)
async def ocr(
    payload: OcrRequest,
    request: Request,
    _auth: None = Depends(enforce_auth),
) -> OcrResponse:
    text = await request.app.state.ocr.extract_text(payload.image_base64)
    return OcrResponse(text=text)


@router.post("/session/start", response_model=SessionResponse)
async def start_session(
    payload: SessionStartRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_runtime_settings),
    session_manager: SessionManager = Depends(get_session_manager),
    _auth: None = Depends(enforce_auth),
) -> SessionResponse:
    session = Session(
        mode=payload.mode,
        provider=payload.provider or settings.default_provider,
        model=payload.model or settings.default_model,
    )
    db.add(session)
    await db.commit()
    live = LiveSession(id=session.id, mode=session.mode, provider=session.provider, model=session.model)
    session_manager.upsert(live)
    return SessionResponse(id=session.id, mode=session.mode, provider=session.provider, model=session.model)


@router.post("/session/{session_id}/end")
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
    _auth: None = Depends(enforce_auth),
) -> dict[str, str]:
    await db.execute(update(Session).where(Session.id == session_id).values(ended_at=datetime.now(UTC)))
    await db.commit()
    session_manager.end(session_id)
    return {"status": "ended"}


@router.post("/session/end")
async def end_session_by_body(
    payload: dict[str, str],
    db: AsyncSession = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
    _auth: None = Depends(enforce_auth),
) -> dict[str, str]:
    session_id = payload.get("session_id") or payload.get("sessionId")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    await db.execute(update(Session).where(Session.id == session_id).values(ended_at=datetime.now(UTC)))
    await db.commit()
    session_manager.end(session_id)
    return {"status": "ended"}
