from app.core.config import Settings
from fastapi import Header, HTTPException, WebSocket, status


async def require_token(
    settings: Settings,
    x_interview_token: str | None = Header(default=None),
) -> None:
    if settings.interview_auth_token and x_interview_token != settings.interview_auth_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid interview token")


async def require_websocket_token(websocket: WebSocket, settings: Settings) -> bool:
    if not settings.interview_auth_token:
        return True
    token = websocket.headers.get("x-interview-token") or websocket.query_params.get("token")
    if token == settings.interview_auth_token:
        return True
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return False

