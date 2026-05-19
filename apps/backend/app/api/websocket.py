import asyncio
import base64
import binascii
import json
from time import time
from uuid import uuid4

from app.core.config import Settings
from app.core.security import require_websocket_token
from app.db import SessionLocal
from app.models import Transcript
from app.schemas import (
    AssistantCancelMessage,
    AudioChunkMessage,
    ManualTranscriptMessage,
    PingMessage,
    ScreenContextMessage,
)
from app.services.llm import LlmOrchestrator
from app.services.prompt_builder import PromptBuilder, PromptContext
from app.services.session_manager import LiveSession
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
ClientMessageAdapter = TypeAdapter(
    AudioChunkMessage | ManualTranscriptMessage | ScreenContextMessage | AssistantCancelMessage | PingMessage
)


@router.websocket("/interview")
async def interview_ws(websocket: WebSocket) -> None:
    settings = websocket.app.state.runtime.settings
    if not await require_websocket_token(websocket, settings):
        return
    await websocket.accept()
    session_manager = websocket.app.state.session_manager
    llm = LlmOrchestrator(settings)
    stt = websocket.app.state.stt
    prompts = PromptBuilder()
    generation_task: asyncio.Task[None] | None = None

    async with SessionLocal() as db:
        initial_id = str(uuid4())
        live = LiveSession(
            id=initial_id,
            mode="interview",
            provider=settings.default_provider,
            model=settings.default_model,
        )
        session_manager.upsert(live)
        await websocket.send_json({"type": "session.ready", "sessionId": initial_id})

        try:
            while True:
                try:
                    raw_message = await websocket.receive_json()
                    message = ClientMessageAdapter.validate_python(raw_message)
                except ValidationError as exc:
                    await websocket.send_json(
                        {
                            "type": "assistant.error",
                            "sessionId": live.id,
                            "message": f"Invalid message: {exc.errors()[0]['msg']}",
                        }
                    )
                    continue
                except json.JSONDecodeError:
                    await websocket.send_json(
                        {"type": "assistant.error", "sessionId": live.id, "message": "Invalid JSON message"}
                    )
                    continue

                session_id = getattr(message, "sessionId", live.id) or live.id
                live = session_manager.get(session_id) or live

                match message.type:
                    case "audio.chunk":
                        try:
                            pcm = base64.b64decode(message.payloadBase64, validate=True)
                        except binascii.Error:
                            await websocket.send_json(
                                {
                                    "type": "assistant.error",
                                    "sessionId": live.id,
                                    "message": "Invalid base64 audio payload",
                                }
                            )
                            continue
                        text = await stt.transcribe_pcm(pcm, message.sampleRate, message.channels)
                        if text:
                            clean = text.strip()
                            now = int(time() * 1000)
                            segment = {
                                "id": str(uuid4()),
                                "sessionId": live.id,
                                "speaker": "speaker",
                                "text": clean,
                                "startedAt": now,
                                "endedAt": now,
                                "isPartial": False,
                            }
                            await websocket.send_json({"type": "transcript.final", "segment": segment})
                            live.append_transcript(clean, settings.transcript_context_segments)
                    case "transcript.manual":
                        generation_task = await _handle_transcript(
                            websocket, db, settings, llm, prompts, live, message.text, generation_task
                        )
                    case "context.screen":
                        live.screen_context = message.text
                    case "assistant.cancel":
                        if generation_task and not generation_task.done():
                            generation_task.cancel()
                    case "ping":
                        await websocket.send_json({"type": "pong", "at": time()})
        except WebSocketDisconnect:
            logger.info("websocket disconnected")
        finally:
            if generation_task and not generation_task.done():
                generation_task.cancel()


async def _handle_transcript(
    websocket: WebSocket,
    db: AsyncSession,
    settings: Settings,
    llm: LlmOrchestrator,
    prompts: PromptBuilder,
    live: LiveSession,
    text: str,
    generation_task: asyncio.Task[None] | None,
) -> asyncio.Task[None] | None:
    clean = text.strip()
    if not clean:
        return generation_task

    now = int(time() * 1000)
    segment = {
        "id": str(uuid4()),
        "sessionId": live.id,
        "speaker": "speaker",
        "text": clean,
        "startedAt": now,
        "endedAt": now,
        "isPartial": False,
    }
    await websocket.send_json({"type": "transcript.final", "segment": segment})

    if settings.transcript_persistence:
        db.add(Transcript(session_id=live.id, text=clean, started_at_ms=now, ended_at_ms=now))
        await db.commit()

    transcript = live.append_transcript(clean, settings.transcript_context_segments)
    if generation_task and not generation_task.done():
        generation_task.cancel()

    prompt = prompts.build(PromptContext(mode=live.mode, transcript=transcript, screen_context=live.screen_context))
    return asyncio.create_task(_stream_answer(websocket, llm, live, prompt))


async def _stream_answer(
    websocket: WebSocket,
    llm: LlmOrchestrator,
    live: LiveSession,
    messages: list[dict[str, str]],
) -> None:
    try:
        async for token in llm.stream(live.provider, live.model, messages):
            await websocket.send_json(
                {"type": "assistant.delta", "delta": {"sessionId": live.id, "content": token, "done": False}}
            )
        await websocket.send_json(
            {"type": "assistant.delta", "delta": {"sessionId": live.id, "content": "", "done": True}}
        )
    except asyncio.CancelledError:
        await websocket.send_json(
            {
                "type": "assistant.delta",
                "delta": {"sessionId": live.id, "content": "\n\n[response cancelled]", "done": True},
            }
        )
    except Exception as exc:
        logger.exception("assistant stream failed")
        await websocket.send_json({"type": "assistant.error", "sessionId": live.id, "message": str(exc)})
