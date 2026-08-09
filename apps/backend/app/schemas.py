from typing import Literal

from pydantic import BaseModel, Field


class SettingsPayload(BaseModel):
    provider: str | None = None
    model: str | None = None
    mode: str | None = None
    whisper_model: str | None = None
    local_only: bool | None = None
    transcript_persistence: bool | None = None


class ModelInfo(BaseModel):
    provider: str
    id: str
    local: bool = False


class SessionStartRequest(BaseModel):
    mode: str = "interview"
    provider: str | None = None
    model: str | None = None


class SessionResponse(BaseModel):
    id: str
    mode: str
    provider: str
    model: str


class OcrRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded PNG/JPEG bytes.")


class OcrResponse(BaseModel):
    text: str


class AudioChunkMessage(BaseModel):
    type: Literal["audio.chunk"]
    sessionId: str
    payloadBase64: str
    sampleRate: int = Field(default=16000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)


class ManualTranscriptMessage(BaseModel):
    type: Literal["transcript.manual"]
    sessionId: str
    text: str = Field(min_length=1)


class ScreenContextMessage(BaseModel):
    type: Literal["context.screen"]
    sessionId: str
    text: str


class AssistantCancelMessage(BaseModel):
    type: Literal["assistant.cancel"]
    sessionId: str


class PingMessage(BaseModel):
    type: Literal["ping"]
    sessionId: str | None = None

