import asyncio
import base64
import binascii
import dataclasses
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
from app.services.rag_retriever import is_available as rag_available
from app.services.rag_retriever import retrieve_chunks
from app.services.session_manager import LiveSession
from app.services.question_detector import QuestionDetector
from app.services.stt import AudioBuffer, WhisperService
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
    partial_task: asyncio.Task[None] | None = None
    last_partial_at: float = 0.0
    audio_buf = AudioBuffer(silence_flush_count=settings.stt_silence_frames)
    question_detector: QuestionDetector | None = (
        QuestionDetector(
            confidence_threshold=settings.qd_confidence_threshold,
            min_words=settings.qd_min_words,
            topic_shift_min_words=settings.qd_topic_shift_min_words,
            dedup_window_seconds=settings.qd_dedup_window_seconds,
            similarity_threshold=settings.qd_dedup_similarity_threshold,
            cooldown_seconds=settings.qd_cooldown_seconds,
        )
        if settings.qd_enabled
        else None
    )

    async with SessionLocal() as db:
        initial_id = str(uuid4())
        live = LiveSession(
            id=initial_id,
            mode=settings.default_mode,
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
                        should_flush = audio_buf.push(pcm)
                        if not should_flush and audio_buf.has_speech:
                            now_t = time()
                            if (
                                audio_buf.speech_duration_seconds >= settings.stt_partial_trigger_seconds
                                and (now_t - last_partial_at) >= settings.stt_partial_cooldown_seconds
                            ):
                                if partial_task and not partial_task.done():
                                    partial_task.cancel()
                                partial_task = asyncio.create_task(
                                    _send_partial(
                                        websocket, stt, live,
                                        audio_buf.snapshot(),
                                        message.sampleRate, message.channels,
                                        " ".join(live.transcript[-3:])[-200:],
                                    )
                                )
                                last_partial_at = now_t
                        if should_flush:
                            if audio_buf.has_speech:
                                if partial_task and not partial_task.done():
                                    partial_task.cancel()
                                    partial_task = None
                                # Transcribe the full utterance — Whisper sees a complete
                                # sentence instead of an arbitrary fixed-size window
                                utterance_pcm = audio_buf.flush()
                                t0 = time()
                                initial_prompt = " ".join(live.transcript[-3:])[-200:]
                                text = await stt.transcribe_pcm(
                                    utterance_pcm,
                                    message.sampleRate,
                                    message.channels,
                                    initial_prompt=initial_prompt,
                                )
                                if text:
                                    clean = text.strip()
                                    if stt._has_repetition(clean):
                                        logger.debug("[WS] repetition detected, dropping | text={!r}", clean[:60])
                                        continue
                                    elapsed_ms = (time() - t0) * 1000
                                    logger.debug(
                                        "[WS] utterance → transcript.final | total={:.0f} ms | text={!r}",
                                        elapsed_ms,
                                        clean[:60],
                                    )
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
                                    last_partial_at = 0.0

                                    if question_detector is not None:
                                        result = question_detector.detect(clean)
                                        if settings.qd_log_detections:
                                            logger.debug(
                                                "[QD] detect | kind={} confidence={:.2f} detected={} | text={!r}",
                                                result.kind, result.confidence, result.detected, clean[:60],
                                            )
                                        if result.detected:
                                            logger.info(
                                                "[QD] trigger | kind={} confidence={:.2f} session={} | text={!r}",
                                                result.kind, result.confidence, live.id, clean[:60],
                                            )
                                            await websocket.send_json({
                                                "type": "assistant.question_detected",
                                                "sessionId": live.id,
                                                "question": clean,
                                                "kind": result.kind,
                                                "confidence": result.confidence,
                                            })
                                            qd_live = dataclasses.replace(
                                                live,
                                                provider=settings.qd_provider or live.provider,
                                                model=settings.qd_model or live.model,
                                            )
                                            generation_task = await _handle_transcript(
                                                websocket, db, settings, llm, prompts,
                                                qd_live, clean, generation_task,
                                                skip_transcript_send=True,
                                            )
                                        else:
                                            live.append_transcript(clean, settings.transcript_context_segments)
                                    else:
                                        live.append_transcript(clean, settings.transcript_context_segments)
                            else:
                                # Silence-only buffer (no speech detected) — just reset
                                audio_buf.flush()
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
            if partial_task and not partial_task.done():
                partial_task.cancel()


async def _send_partial(
    websocket: WebSocket,
    stt: WhisperService,
    live: LiveSession,
    pcm: bytes,
    sample_rate: int,
    channels: int,
    initial_prompt: str,
) -> None:
    try:
        text = await stt.transcribe_pcm(pcm, sample_rate, channels, initial_prompt=initial_prompt)
        if not text:
            return
        clean = text.strip()
        if stt._has_repetition(clean):
            return
        now = int(time() * 1000)
        segment = {
            "id": str(uuid4()),
            "sessionId": live.id,
            "speaker": "speaker",
            "text": clean,
            "startedAt": now,
            "endedAt": now,
            "isPartial": True,
        }
        await websocket.send_json({"type": "transcript.partial", "segment": segment})
        logger.debug("[WS] partial transcript sent | text={!r}", clean[:60])
    except asyncio.CancelledError:
        pass  # final transcription supersedes; silently drop


async def _handle_transcript(
    websocket: WebSocket,
    db: AsyncSession,
    settings: Settings,
    llm: LlmOrchestrator,
    prompts: PromptBuilder,
    live: LiveSession,
    text: str,
    generation_task: asyncio.Task[None] | None,
    *,
    skip_transcript_send: bool = False,
) -> asyncio.Task[None] | None:
    clean = text.strip()
    if not clean:
        return generation_task

    logger.info("question received | session={} preview={!r}", live.id, clean[:80])

    now = int(time() * 1000)
    if not skip_transcript_send:
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
        logger.info("aborting previous generation | session={}", live.id)
        generation_task.cancel()

    # RAG retrieval — runs in a thread executor so it doesn't block the event loop
    # (embed_texts is a synchronous httpx call; retrieve_chunks creates a fresh
    # VectorStore per call to pick up documents ingested by any process)
    rag_context: str | None = None
    citations: list[dict] = []
    rag_searched = settings.rag_enabled and rag_available()

    if rag_searched:
        try:
            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(
                None, retrieve_chunks, clean, None, settings
            )
            if chunks:
                # Build labeled context string for the prompt
                context_parts = []
                for i, chunk in enumerate(chunks, 1):
                    context_parts.append(
                        f"[{i}] Source: {chunk['source']}, Page: {chunk['page']}\n{chunk['text']}"
                    )
                rag_context = "\n\n---\n\n".join(context_parts)
                citations = [
                    {
                        "source": c["source"],
                        "page": c["page"],
                        "snippet": c["text"][:200].replace("\n", " "),
                        "distance": c["distance"],
                    }
                    for c in chunks
                ]
                logger.info(
                    "RAG retrieval | session={} chunks={} top_distance={}",
                    live.id, len(chunks), chunks[0]["distance"]
                )
                # Send citations before streaming so the frontend can render them
                await websocket.send_json({
                    "type": "assistant.citations",
                    "sessionId": live.id,
                    "citations": citations,
                })
            else:
                logger.info(
                    "RAG: no relevant chunks found, falling back to LLM general knowledge | session={} question={!r}",
                    live.id, clean[:60],
                )
        except Exception as exc:
            logger.warning("RAG retrieval failed (falling back to direct LLM) | error={}", exc)

    prompt = prompts.build(PromptContext(
        mode=live.mode,
        current_question=clean,
        transcript=transcript,
        screen_context=live.screen_context,
        rag_context=rag_context,
        rag_searched=rag_searched,
    ))
    logger.info("starting generation | session={} provider={} model={} rag={}",
                live.id, live.provider, live.model, rag_context is not None)
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
        logger.info("generation complete | session={}", live.id)
        await websocket.send_json(
            {"type": "assistant.delta", "delta": {"sessionId": live.id, "content": "", "done": True}}
        )
    except asyncio.CancelledError:
        logger.info("generation cancelled | session={}", live.id)
        await websocket.send_json(
            {
                "type": "assistant.delta",
                "delta": {"sessionId": live.id, "content": "\n\n[response cancelled]", "done": True},
            }
        )
    except Exception as exc:
        logger.exception("generation failed | session={}", live.id)
        await websocket.send_json({"type": "assistant.error", "sessionId": live.id, "message": str(exc)})
