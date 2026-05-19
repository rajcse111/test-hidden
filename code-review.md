# Code Review — AI Answer Assistant Overlay

**Reviewer:** Claude Code  
**Date:** 2026-05-18  
**Scope:** Full codebase (`apps/backend`, `apps/desktop`, `packages/shared`, infra)  
**Verdict:** Not production-ready. Several critical runtime bugs and architectural gaps must be fixed before shipping.

---

## Severity Key

| Label | Meaning |
|---|---|
| **P0 — Critical** | Runtime bug / data loss / security hole. Blocks production. |
| **P1 — High** | Major correctness or architectural issue. Needs fix before release. |
| **P2 — Medium** | Code quality, reliability, or maintainability gap. Fix in next iteration. |
| **P3 — Low** | Polish, minor risk, or best-practice deviation. |

---

## P0 — Critical

### 1. `docker-compose.yml` mounts `.env.example` as the env file

**File:** `docker-compose.yml:5`

```yaml
env_file:
  - .env.example   # ← reads the example file, not .env
```

All API keys and settings ship as empty strings in every Docker deployment. Anyone running `docker compose up` is using the example file. **Fix:** change to `.env` and add `.env` to `.gitignore` (it likely already is, but verify).

---

### 2. `OcrService.extract_text` blocks the asyncio event loop

**File:** `apps/backend/app/services/ocr.py:9–12`

```python
async def extract_text(self, image_base64: str) -> str:
    raw = base64.b64decode(image_base64)
    image = Image.open(io.BytesIO(raw))
    return pytesseract.image_to_string(image).strip()   # blocking
```

`pytesseract.image_to_string` is a blocking subprocess call. Running it directly inside an `async def` stalls every other coroutine for the duration of the OCR. **Fix:** wrap in `asyncio.to_thread`, the same pattern already used in `WhisperService`.

```python
async def extract_text(self, image_base64: str) -> str:
    raw = base64.b64decode(image_base64)
    return await asyncio.to_thread(self._run_ocr, raw)

def _run_ocr(self, raw: bytes) -> str:
    image = Image.open(io.BytesIO(raw))
    return pytesseract.image_to_string(image).strip()
```

---

### 3. Whisper model reloaded on every WebSocket connection

**File:** `apps/backend/app/api/websocket.py:33` and `apps/backend/app/services/stt.py:15–21`

```python
# websocket.py — called per connection
stt = WhisperService(settings)
```

`@cached_property` caches the model on the *instance*, not the class. Every new WebSocket connection creates a new `WhisperService` instance, so the model is loaded fresh for each connection. On large models (`medium`, `large-v3`) this costs several seconds and gigabytes of memory.

**Fix:** Make `WhisperService` a singleton, or load the model eagerly at startup in `lifespan`.

```python
# app/main.py — lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    ...
    app.state.stt = WhisperService(settings)
    app.state.stt.model   # eager load
    yield
```

Then inject it via `Request.app.state.stt` or a FastAPI dependency.

---

### 4. `@retry` on an async generator silently does nothing

**File:** `apps/backend/app/services/llm.py:51–64`

```python
@retry(wait=wait_exponential(...), stop=stop_after_attempt(3))
async def stream(self, messages, model) -> AsyncIterator[str]:
    ...
    async with client.stream(...) as response:
        async for line in response.aiter_lines():
            yield content
```

`tenacity.retry` does not support async generators. The decorator wraps the *generator factory*, not the iteration. A network error raised during `aiter_lines` will propagate immediately; the retry never fires. **Fix:** Extract the HTTP call into a separate `async def` that returns a collected list, or use a `while attempt < max` loop manually.

---

### 5. `websocket_db()` leaks the database session

**File:** `apps/backend/app/api/websocket.py:22–26`

```python
async def websocket_db() -> AsyncSession:
    async for session in get_db():
        return session          # exits the async-for mid-generator
    raise RuntimeError(...)
```

`get_db` yields inside `async with SessionLocal() as session`. Returning from the `async for` exits without resuming the generator, so the `async with` cleanup (`session.__aexit__`) never runs. The SQLite connection leaks for the lifetime of the process.

**Fix:** Use the dependency properly — receive the session as a FastAPI `Depends(get_db)` parameter on the WebSocket endpoint itself, or hold a reference via a try/finally in the endpoint body.

---

## P1 — High

### 6. `POST /api/settings` writes to DB but the running config never updates

**Files:** `apps/backend/app/api/routes.py:42–47`, `apps/backend/app/core/config.py:35–37`

`get_settings()` is `@lru_cache`. The `Settings` Pydantic object is frozen at startup. Calling `POST /api/settings` persists key-value pairs to SQLite, but nothing reads them back. Provider, model, whisper model, etc. remain unchanged at runtime until restart.

This means the settings UI is non-functional. **Fix:** Either invalidate the `lru_cache` after a write (call `get_settings.cache_clear()`), or maintain a mutable runtime-settings object that overrides the static one.

---

### 7. `GeminiProvider.stream` is not actually streaming

**File:** `apps/backend/app/services/llm.py:66–86`

```python
async with httpx.AsyncClient(timeout=60) as client:
    response = await client.post(...)   # waits for full response
    ...
    for word in text.split(" "):
        yield f"{word} "
```

This makes one blocking REST call, waits for the entire Gemini response, then fake-streams by yielding one word at a time — with no delay. The latency is identical to non-streaming. The Gemini API supports Server-Sent Events streaming; use `client.stream("POST", ..., json={..., "streamGenerateContent": True})`.

---

### 8. `ScriptProcessorNode` is deprecated; audio chunks are too small

**File:** `apps/desktop/src/services/audioCapture.ts:18–36`

`createScriptProcessor` has been deprecated since Chrome 66. It runs on the main thread and degrades UI performance under load. It should be replaced with `AudioWorkletProcessor`.

Additionally, at 16kHz with 4096 samples per buffer, each chunk is ~256ms of audio. The README recommends 1–2 second chunks. Sending 256ms fragments to Whisper produces poor transcription — Whisper's VAD and beam search need at least 1 second of context. **Fix:** either accumulate chunks client-side before sending, or switch to `AudioWorkletProcessor` with an accumulator buffer.

---

### 9. No authentication on the WebSocket or admin endpoints

**Files:** `apps/backend/app/api/websocket.py`, `apps/backend/app/api/routes.py`

`POST /api/settings` allows any caller on the network to change the backend's provider, model, and `local_only` flag. `POST /api/ocr` accepts arbitrary base64 images. `/ws/interview` accepts audio from any origin. CORS is set to `http://localhost:5173` only, which provides browser-level origin enforcement but not network-level authentication.

For a local-only desktop app this is low risk, but if `BACKEND_HOST=0.0.0.0` exposes the port on a shared network, these endpoints are open. Consider adding a shared secret header (e.g., `X-Interview-Token`) verified by middleware, generated at startup and passed via `VITE_BACKEND_TOKEN`.

---

### 10. Dockerfile runs as root; no multi-stage build

**File:** `apps/backend/Dockerfile`

The container runs as root (`USER` directive is absent). If there is a path traversal or RCE in any dependency, the attacker has full container root. Also, test dependencies (`pytest`, `ruff`) are installed into the runtime image because there is only one stage.

```dockerfile
# Recommended structure
FROM python:3.11-slim AS builder
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
RUN useradd -r -u 1001 appuser
USER appuser
```

---

### 11. `datetime.utcnow()` is deprecated

**File:** `apps/backend/app/api/routes.py:76`

```python
ended_at=datetime.utcnow()
```

`datetime.utcnow()` is deprecated in Python 3.12 and returns a naïve datetime. Use `datetime.now(timezone.utc)` instead, which returns a timezone-aware datetime consistent with the `DateTime(timezone=True)` column definition.

---

### 12. No restart policy in `docker-compose.yml`

**File:** `docker-compose.yml`

Without `restart: unless-stopped`, if the backend crashes (e.g., first Whisper load OOM), the container stops and stays stopped. Add `restart: unless-stopped`.

---

## P2 — Medium

### 13. `logs/` directory not guaranteed to exist

**File:** `apps/backend/app/core/logging.py:17`

Loguru adds a file sink at `logs/backend.log`. If the directory does not exist (clean checkout, Docker), loguru raises `FileNotFoundError` at startup. **Fix:** add `Path("logs").mkdir(exist_ok=True)` before `logger.add(...)`.

---

### 14. `cors_origins` default cannot be overridden via environment variable

**File:** `apps/backend/app/core/config.py:23`

```python
cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
```

`default_factory` bypasses pydantic-settings env-variable parsing for list fields. To override via `CORS_ORIGINS=http://host1,http://host2`, the field must be declared as a plain default or use a JSON env value. This makes the backend impossible to configure for production without code changes.

---

### 15. `end_session_by_body` returns HTTP 200 on missing input

**File:** `apps/backend/app/api/routes.py:82–87`

```python
if not session_id:
    return {"status": "missing-session"}   # HTTP 200
```

Clients cannot distinguish success from this error without inspecting the body. Should raise `HTTPException(status_code=400, detail="session_id is required")`.

---

### 16. `Setting.updated_at` `onupdate` won't fire in SQLite

**File:** `apps/backend/app/models.py:38`

```python
updated_at: Mapped[datetime] = mapped_column(..., onupdate=func.now())
```

`onupdate` with `func.now()` is a *server-side* expression. SQLite does not execute `onupdate` automatically on UPDATE statements; the column stays at its original `server_default` value. To track updates reliably, handle the timestamp in Python before committing.

---

### 17. No Pydantic validation on incoming WebSocket messages

**File:** `apps/backend/app/api/websocket.py:48–78`

Messages are consumed as raw `dict` with `.get()` everywhere. A malformed message (missing `payloadBase64`, `type` as an integer, etc.) either silently no-ops or causes an unhandled exception that tears down the connection. **Fix:** define Pydantic discriminated union models for `ClientMessage` (the type already exists in `packages/shared`) and validate with `model_validate` at the top of the loop.

---

### 18. `InterviewSocket` reconnect uses a fixed 1.2s delay with no backoff

**File:** `apps/desktop/src/services/interviewSocket.ts:47–53`

If the backend is unreachable (not started, crash loop), the client will reconnect every 1.2 seconds indefinitely with no increase in delay. **Fix:** implement exponential backoff with a cap (e.g., 1.2s → 2.4s → 4.8s → max 30s).

---

### 19. `toBase64` in `audioCapture.ts` will stack-overflow for large buffers

**File:** `apps/desktop/src/services/audioCapture.ts:51–55`

```typescript
for (const byte of bytes) binary += String.fromCharCode(byte);
return window.btoa(binary);
```

`String.fromCharCode` called once per byte via string concatenation is O(n²) due to string immutability. For larger Whisper models that require longer audio chunks this becomes slow. Use `btoa` with a chunk-safe approach or `Buffer.from(buffer).toString("base64")` in the Electron renderer (where `Buffer` is available via the preload context).

---

### 20. Session transcript capped at 20 segments with no configuration

**File:** `apps/backend/app/services/session_manager.py:18`

```python
return "\n".join(self.transcript[-20:])
```

For a 90-minute interview, 20 segments is approximately 2–3 minutes of context. The LLM loses all earlier conversation history. This is a hard-coded number with no setting. Consider making it configurable or implementing a sliding-window with summarisation.

---

### 21. `session_manager` singleton is a module-level object in `routes.py`, imported by `websocket.py`

**Files:** `apps/backend/app/api/routes.py:16`, `apps/backend/app/api/websocket.py:11`

```python
# routes.py
session_manager = SessionManager()

# websocket.py
from app.api.routes import session_manager
```

This is a circular-import risk and an architectural smell. `SessionManager` is a shared dependency; it should live in `app/services/session_manager.py` (it does) and be registered as an `app.state` object in `lifespan`, then injected via `Request.app.state`. The current design also means a separate test invocation of `routes.py` gets its own `session_manager`, silently decoupled from the WebSocket one.

---

## P3 — Low

### 22. Test coverage is minimal

Three tests exist: 1 prompt-builder unit test, 1 health-check integration test, 1 WebSocket smoke test, 1 React smoke test. There are no tests for:
- LLM provider streaming (including error paths and cancellation)
- `WhisperService` PCM → WAV → transcript pipeline
- `SessionManager` concurrency / transcript windowing
- `AudioCapture` start/stop lifecycle
- WebSocket reconnect logic
- Audio-chunk-to-transcript-to-answer end-to-end flow

Aim for at least the happy path and one error path per service boundary.

---

### 23. No dependency lock file

`requirements.txt` uses `>=` version ranges. A `pip install` on a new day could pull in a breaking minor release of `faster-whisper`, `openai`, or `httpx`. Add `pip-compile` (from `pip-tools`) to produce a deterministic `requirements.lock` and pin the lock in CI.

---

### 24. CI installs Python dependencies without a pip cache

**File:** `.github/workflows/ci.yml:12`

```yaml
- run: pip install -r apps/backend/requirements.txt
```

With packages like `faster-whisper`, `pillow`, and `sqlalchemy`, cold install takes 60–90 seconds every run. Add `cache: pip` to `actions/setup-python`.

---

### 25. No `Content-Security-Policy` in Electron `webPreferences`

**File:** `apps/desktop/electron/main.ts`

Electron does not set a CSP by default. Although `nodeIntegration: false` and `sandbox: true` are correctly set, a missing CSP leaves the renderer open to injected inline scripts from malicious content. Add a `session.defaultSession.webRequest.onHeadersReceived` handler to inject `Content-Security-Policy: default-src 'self' ws://localhost:8000 http://localhost:8000; script-src 'self'`.

---

### 26. `GeminiProvider` does not use the Gemini SDK; is not streamed or typed

**File:** `apps/backend/app/services/llm.py:66–86`

The implementation uses raw `httpx` with a manually constructed REST call to a v1beta endpoint. The Gemini API URL, response structure, and auth scheme will break on model or API changes. Use the official `google-generativeai` SDK for a stable, typed interface and real streaming.

---

### 27. No `pyproject.toml` for pytest configuration

Running `pytest apps/backend/tests` works, but without a `[tool.pytest.ini_options]` section, `asyncio_mode` isn't set and async tests need `@pytest.mark.asyncio` decorators. The test file `test_api.py` uses `TestClient` (synchronous), which is correct; but future async tests will fail silently without this config.

---

### 28. `electron-store` in `dependencies` instead of the main process only

**File:** `apps/desktop/package.json:18`

`electron-store` is a Node.js package used only in the Electron main process. Listing it in `dependencies` (bundled by Vite) rather than as a devDependency or Electron-specific dependency causes Vite to attempt to bundle a Node.js module into the renderer, which will fail at build time unless Vite is configured to externalize it.

---

## Summary Table

| # | Severity | Area | Issue |
|---|---|---|---|
| 1 | P0 | DevOps | `docker-compose.yml` reads `.env.example` |
| 2 | P0 | Backend | `OcrService` blocks event loop |
| 3 | P0 | Backend | Whisper model reloaded per WS connection |
| 4 | P0 | Backend | `@retry` on async generator is a no-op |
| 5 | P0 | Backend | WebSocket DB session leaked |
| 6 | P1 | Backend | Settings endpoint doesn't update running config |
| 7 | P1 | Backend | Gemini provider fakes streaming |
| 8 | P1 | Frontend | Deprecated `ScriptProcessorNode`; 256ms audio chunks too small |
| 9 | P1 | Security | No authentication on settings/OCR/WebSocket |
| 10 | P1 | DevOps | Dockerfile runs as root; single-stage |
| 11 | P1 | Backend | `datetime.utcnow()` deprecated |
| 12 | P1 | DevOps | No Docker restart policy |
| 13 | P2 | Backend | `logs/` dir not created |
| 14 | P2 | Backend | `cors_origins` can't be overridden from env |
| 15 | P2 | Backend | `end_session_by_body` returns HTTP 200 on error |
| 16 | P2 | Backend | `Setting.updated_at` onupdate broken in SQLite |
| 17 | P2 | Backend | No Pydantic validation on WebSocket messages |
| 18 | P2 | Frontend | No reconnect backoff |
| 19 | P2 | Frontend | `toBase64` O(n²) string concatenation |
| 20 | P2 | Backend | Transcript window hard-coded to 20 |
| 21 | P2 | Backend | `session_manager` singleton via module import |
| 22 | P3 | Testing | Minimal test coverage |
| 23 | P3 | DevOps | No pip lock file |
| 24 | P3 | DevOps | No pip cache in CI |
| 25 | P3 | Security | No Content-Security-Policy in Electron |
| 26 | P3 | Backend | Gemini raw HTTP instead of SDK |
| 27 | P3 | Testing | No `pyproject.toml` pytest config |
| 28 | P3 | Frontend | `electron-store` in wrong dependency group |

---

## Recommended Fix Order

1. **P0 fixes first** (issues 1–5) — none of these require significant redesign; all are targeted, isolated changes.
2. **P1: Settings live reload (6)** — the settings endpoint is a user-facing feature; fix or document it as restart-required.
3. **P1: Audio pipeline (8)** — move to `AudioWorkletProcessor` with chunk accumulation; this touches the most user-visible latency.
4. **P1: Gemini streaming (7)** — swap to SDK.
5. **P2 sweep** — batch the medium items in a single PR; none are blocking individually but they compound.
6. **P3 / test coverage** — establish a baseline of meaningful tests before the next feature iteration.
