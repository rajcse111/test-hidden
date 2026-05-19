from dataclasses import dataclass, field
from time import time


@dataclass
class LiveSession:
    id: str
    mode: str
    provider: str
    model: str
    transcript: list[str] = field(default_factory=list)
    screen_context: str | None = None
    started_at: float = field(default_factory=time)

    def append_transcript(self, text: str, context_segments: int) -> str:
        clean = text.strip()
        if clean:
            self.transcript.append(clean)
        return "\n".join(self.transcript[-context_segments:])


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, LiveSession] = {}

    def upsert(self, session: LiveSession) -> LiveSession:
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> LiveSession | None:
        return self._sessions.get(session_id)

    def end(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
