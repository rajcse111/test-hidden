import re
import string
from dataclasses import dataclass
from time import time

from loguru import logger

_WH_LEAD = re.compile(
    r'^\s*(what|where|when|who|whom|whose|which|why|how)\b',
    re.IGNORECASE,
)
_WH_MID = re.compile(
    r'\b(what|where|when|who|whom|whose|which|why|how)\b',
    re.IGNORECASE,
)
_AUX_INVERSION = re.compile(
    r'^(can|could|would|should|do|does|did|is|are|was|were|have|has|had|will|shall|might|may|must)\s+\w+',
    re.IGNORECASE,
)
_QUESTION_MARK = re.compile(r'\?\s*$')
_TOPIC_SHIFT = re.compile(
    r'\b(tell\s+me\s+about|explain|describe|walk\s+me\s+through|talk\s+about|discuss|elaborate\s+on|'
    r'give\s+me\s+(an?\s+)?(example|overview|idea)|let(\'s|\s+us)\s+(talk|discuss|look))\b',
    re.IGNORECASE,
)

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


@dataclass(frozen=True)
class DetectionResult:
    detected: bool
    kind: str          # "question" | "topic_shift" | "none"
    confidence: float  # 0.0–1.0
    normalized: str    # lowercased, punctuation-stripped form used for dedup
    original: str


class QuestionDetector:
    """
    Heuristic detector for questions and topic shifts in transcribed speech.

    Instantiate once per WebSocket connection so dedup state is session-scoped.
    All detection is synchronous regex (~1 μs) — safe to call in the async event loop.
    """

    def __init__(
        self,
        confidence_threshold: float,
        min_words: int,
        topic_shift_min_words: int,
        dedup_window_seconds: float,
        similarity_threshold: float,
        cooldown_seconds: float,
    ) -> None:
        self._threshold = confidence_threshold
        self._min_words = min_words
        self._topic_min_words = topic_shift_min_words
        self._dedup_window = dedup_window_seconds
        self._sim_threshold = similarity_threshold
        self._cooldown = cooldown_seconds
        self._history: list[tuple[str, float]] = []  # (normalized_text, timestamp)
        self._last_trigger_at: float = 0.0

    def detect(self, text: str) -> DetectionResult:
        """
        Analyse one transcript utterance and return a DetectionResult.

        Returns detected=True only when:
          - enough words (>= min_words)
          - confidence >= threshold
          - not within cooldown window
          - not a duplicate of a recent utterance (Jaccard similarity)
        """
        words = text.split()
        if len(words) < self._min_words:
            return DetectionResult(detected=False, kind="none", confidence=0.0, normalized="", original=text)

        kind, score = self._score(text)

        if kind == "topic_shift" and len(words) < self._topic_min_words:
            return DetectionResult(detected=False, kind="none", confidence=0.0, normalized="", original=text)

        normalized = self._normalize(text)

        if score < self._threshold:
            return DetectionResult(detected=False, kind=kind, confidence=score, normalized=normalized, original=text)

        now = time()
        if (now - self._last_trigger_at) < self._cooldown:
            logger.debug("[QD] cooldown active, suppressing trigger | text={!r}", text[:60])
            return DetectionResult(detected=False, kind=kind, confidence=score, normalized=normalized, original=text)

        self._prune_history()
        if self._is_duplicate(normalized):
            logger.debug("[QD] duplicate suppressed | text={!r}", text[:60])
            return DetectionResult(detected=False, kind=kind, confidence=score, normalized=normalized, original=text)

        self._history.append((normalized, now))
        self._last_trigger_at = now
        return DetectionResult(detected=True, kind=kind, confidence=score, normalized=normalized, original=text)

    def _score(self, text: str) -> tuple[str, float]:
        base: float = 0.0
        kind: str = "none"
        has_q = bool(_QUESTION_MARK.search(text))

        if _WH_LEAD.search(text):
            base, kind = 0.9, "question"
        elif _AUX_INVERSION.match(text):
            base, kind = 0.85, "question"
        elif _TOPIC_SHIFT.search(text):
            base, kind = 0.75, "topic_shift"
        elif _WH_MID.search(text):
            # WH word mid-sentence is ambiguous ("I know what you mean") — needs "?" to fire
            base, kind = 0.55, "question"
        elif has_q:
            base, kind = 0.55, "question"

        if base > 0 and has_q:
            base = min(1.0, base + 0.1)

        return kind, base

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().strip().translate(_PUNCT_TABLE).split())

    def _jaccard(self, a: str, b: str) -> float:
        sa, sb = set(a.split()), set(b.split())
        union = sa | sb
        if not union:
            return 1.0
        return len(sa & sb) / len(union)

    def _is_duplicate(self, normalized: str) -> bool:
        return any(self._jaccard(normalized, past) >= self._sim_threshold for past, _ in self._history)

    def _prune_history(self) -> None:
        cutoff = time() - self._dedup_window
        self._history = [(t, ts) for t, ts in self._history if ts > cutoff]
