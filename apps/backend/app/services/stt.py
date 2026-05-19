import asyncio
import io
import wave
from functools import cached_property

from app.core.config import Settings
from loguru import logger


class WhisperService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def model(self):
        from faster_whisper import WhisperModel

        logger.info("loading whisper model {}", self.settings.whisper_model)
        return WhisperModel(self.settings.whisper_model, device="cpu", compute_type="int8")

    async def transcribe_pcm(self, pcm: bytes, sample_rate: int, channels: int) -> str:
        if not pcm:
            return ""
        wav_bytes = await asyncio.to_thread(self._pcm_to_wav, pcm, sample_rate, channels)
        return await asyncio.to_thread(self._transcribe_wav, wav_bytes)

    def _transcribe_wav(self, wav_bytes: bytes) -> str:
        segments, _info = self.model.transcribe(
            io.BytesIO(wav_bytes),
            vad_filter=True,
            beam_size=5,
            language="en",
            temperature=0,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    @staticmethod
    def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return buffer.getvalue()

