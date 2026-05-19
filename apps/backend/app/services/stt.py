import asyncio
import io
import struct
import time
import wave
from collections import Counter
from functools import cached_property

from app.core.config import Settings
from loguru import logger


class AudioBuffer:
    """Per-connection utterance accumulator with energy-based VAD.

    Collects 250 ms PCM frames and signals when an utterance ends (speaker
    paused). This lets Whisper see a complete sentence rather than an
    arbitrary fixed-size chunk, which dramatically improves accuracy and
    eliminates boundary-word duplication.

    State machine: pre-speech silence → speech → trailing silence → flush.
    Pre-speech silence is dropped so Whisper never receives leading noise.
    """

    # 100 int16 RMS ≈ 0.003 float32 RMS — low enough to catch any real speech
    # even on quiet microphones; browser noise-suppression keeps true silence
    # well below this value so false-positives are handled by Silero VAD
    SPEECH_THRESHOLD = 100
    SILENCE_FLUSH_COUNT = 4   # consecutive silent frames before flush (4 × 250 ms = 1.0 s)
    MAX_BUFFER_SECONDS = 5    # force-flush fallback for noisy environments

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._chunks: list[bytes] = []
        self._silence_count = 0
        self._has_speech = False

    def push(self, pcm: bytes) -> bool:
        """Append a PCM frame. Returns True when the buffer should be flushed."""
        rms = self._rms(pcm)
        if rms >= self.SPEECH_THRESHOLD:
            if not self._has_speech:
                logger.debug("[VAD] speech onset | rms={:.0f}", rms)
            self._has_speech = True
            self._silence_count = 0
            self._chunks.append(pcm)
        elif self._has_speech:
            # Keep trailing silence so Whisper hears the natural end of the sentence
            self._chunks.append(pcm)
            self._silence_count += 1
            if self._silence_count >= self.SILENCE_FLUSH_COUNT:
                return True
        # else: pre-speech silence — drop to avoid leading noise in the utterance

        # Safety valve: flush if the buffer grows beyond the max duration
        total_bytes = sum(len(c) for c in self._chunks)
        total_seconds = total_bytes / (self.sample_rate * self.channels * 2)
        return total_seconds >= self.MAX_BUFFER_SECONDS

    def flush(self) -> bytes:
        """Return accumulated PCM and reset state."""
        data = b"".join(self._chunks)
        self._chunks.clear()
        self._silence_count = 0
        self._has_speech = False
        return data

    @property
    def has_speech(self) -> bool:
        return self._has_speech

    @staticmethod
    def _rms(pcm: bytes) -> float:
        n = len(pcm) // 2
        if n == 0:
            return 0.0
        samples = struct.unpack(f"<{n}h", pcm[: n * 2])
        return (sum(s * s for s in samples) / n) ** 0.5


class WhisperService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def model(self):
        from faster_whisper import WhisperModel

        logger.info("loading whisper model {}", self.settings.whisper_model)
        return WhisperModel(self.settings.whisper_model, device="cpu", compute_type="int8")

    async def transcribe_pcm(
        self, pcm: bytes, sample_rate: int, channels: int, *, initial_prompt: str = ""
    ) -> str:
        if not pcm:
            return ""
        wav_bytes = await asyncio.to_thread(self._pcm_to_wav, pcm, sample_rate, channels)
        t0 = time.perf_counter()
        text = await asyncio.to_thread(self._transcribe_wav, wav_bytes, initial_prompt)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("[STT] chunk={} bytes | inference={:.0f} ms | text_len={} chars", len(pcm), elapsed_ms, len(text))
        return text

    def _transcribe_wav(self, wav_bytes: bytes, initial_prompt: str) -> str:
        segments, _info = self.model.transcribe(
            io.BytesIO(wav_bytes),
            language="en",
            # beam_size=1 (greedy) is ~4× faster than beam_size=5 with negligible
            # accuracy loss on clean speech; critical for low-latency transcription
            beam_size=1,
            temperature=0,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 100, "speech_pad_ms": 30},
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            condition_on_previous_text=False,
            # Seed with recent transcript so the model has sentence context
            initial_prompt=initial_prompt or None,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    @staticmethod
    def _dedup_boundary(new_text: str, prev_text: str, max_overlap: int = 5) -> str:
        """Strip leading words from new_text that duplicate the tail of prev_text.

        Handles the edge case where a word straddles a flush boundary and appears
        in both the previous and current transcription.
        Returns "" when the entire result is a duplicate (caller should discard).
        """
        if not new_text or not prev_text:
            return new_text
        new_words = new_text.split()
        prev_words = prev_text.split()
        for overlap in range(min(max_overlap, len(new_words), len(prev_words)), 0, -1):
            if new_words[:overlap] == prev_words[-overlap:]:
                return " ".join(new_words[overlap:]).strip()
        return new_text

    @staticmethod
    def _has_repetition(text: str, max_word_freq: int = 3, max_bigram_freq: int = 2) -> bool:
        """Detect Whisper hallucination loops such as 'the the the the'.

        Returns True when any single word appears more than max_word_freq times
        or any consecutive word pair appears more than max_bigram_freq times.
        """
        words = text.lower().split()
        if not words:
            return False
        word_counts = Counter(words)
        if word_counts.most_common(1)[0][1] > max_word_freq:
            return True
        bigrams = [(words[i], words[i + 1]) for i in range(len(words) - 1)]
        if bigrams and Counter(bigrams).most_common(1)[0][1] > max_bigram_freq:
            return True
        return False

    @staticmethod
    def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return buffer.getvalue()
