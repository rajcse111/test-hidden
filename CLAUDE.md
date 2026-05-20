# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Answer Assistant Overlay — a production desktop app combining an Electron transparent overlay, real-time microphone streaming, FastAPI WebSockets, Whisper transcription, OCR screen context, and streaming LLM answers.

## Repository Layout

```
apps/
  backend/       # Python FastAPI backend (uvicorn, asyncio, SQLAlchemy)
  desktop/       # Electron + React + TypeScript overlay app (Vite) — has its own CLAUDE.md
packages/
  shared/        # Shared TypeScript types (ClientMessage, ServerMessage, OverlayMode, etc.)
  ui/            # Shared UI component library
scripts/         # PowerShell setup/dev scripts
wscript/         # Windows VBScript launchers — start backend/frontend/Ollama in hidden windows; stop-cleanup.vbs kills all processes and removes runtime files
data/            # SQLite DB written here at runtime (gitignored)
logs/            # Log files written here at runtime (gitignored)
```

## Common Commands

### Setup
```powershell
# Windows one-shot setup (prefers requirements.lock; falls back to requirements.txt)
.\scripts\setup.ps1

# Manual — use requirements.lock for pinned production versions, requirements.txt for testing
npm install
python -m venv .venv
.venv\Scripts\pip install -r apps\backend\requirements.lock   # pinned
# or:
.venv\Scripts\pip install -r apps\backend\requirements.txt    # loose ranges, fine for testing
copy .env.example .env
```

### Development
```powershell
# Run both backend and desktop (spawns two PowerShell windows)
.\scripts\dev.ps1

# Backend only — activate venv first
.venv\Scripts\uvicorn app.main:app --reload --app-dir apps/backend --host 0.0.0.0 --port 8000
# or via npm script:
npm run backend:dev

# Desktop renderer only (Vite dev server at :5173)
npm run dev --workspace @interview/desktop

# Full desktop app with Electron
npm run electron:dev --workspace @interview/desktop
```

### Testing
```powershell
# Backend tests (asyncio_mode = "auto" in pyproject.toml — all async tests work without decorators)
.venv\Scripts\pytest apps/backend/tests

# Single backend test file
.venv\Scripts\pytest apps/backend/tests/test_prompt_builder.py

# Desktop tests (Vitest, run once)
npm run test --workspace @interview/desktop

# Single desktop test file
npx vitest run apps/desktop/src/ui/App.test.tsx
```

### Linting & Formatting
```powershell
make lint
# or individually:
.venv\Scripts\ruff check apps/backend   # ruff config in pyproject.toml (line-length=120, py311)
npm run lint                            # ESLint over src/**/*.{ts,tsx} and electron/**/*.ts
npm run format                          # Prettier (root-level, covers all workspaces)
```

### Build & Package
```powershell
npm run build --workspace @interview/desktop
npm run desktop:package        # Electron Builder → NSIS/DMG/AppImage
make docker-up                 # Backend-only Docker (sqlite data persisted to ./data/)
```

### CI (`.github/workflows/ci.yml`)
Two independent jobs run on every push: **backend** (Python 3.11, `ruff check`, `pytest` against `requirements.lock`) and **desktop** (Node 20, `npm run lint`, `npm run test`, `npm run build`). Both must pass before merging.

## Architecture

### Real-Time Pipeline

Two separate paths flow through the WebSocket connection:

**Audio → Transcript only** (no LLM trigger):
```
Microphone → audioCapture.ts → base64 PCM chunks (audio.chunk)
  → AudioBuffer.push(pcm)   [energy VAD; flushes on 1 s trailing silence or 5 s max]
  → WhisperService.transcribe_pcm()   [CPU, int8, English-only, beam_size=1]
  → transcript.final back over WS
  → assistantStore transcript segments
```

**Transcript → LLM answer** (triggered by transcript.manual):
```
liveSpeech.ts (Web Speech API) or manual input → transcript.manual message
  → PromptBuilder.build()
  → LlmOrchestrator.stream()   [new instance per WS connection]
  → assistant.delta tokens back over WS
  → assistantStore.appendAnswer()
```

`liveSpeech.ts` sends `transcript.manual` when the user stops speaking, merging Web Speech API text with any audioCapture text. `audio.chunk` messages are for STT only — they never directly trigger the LLM.

### WebSocket Message Protocol
Defined in `packages/shared/src/index.ts`. **Client sends:** `audio.chunk`, `transcript.manual`, `assistant.cancel`, `context.screen`, `ping`. **Server sends:** `session.ready`, `transcript.final`, `transcript.partial`, `assistant.delta`, `assistant.error`, `pong`.

The WS handler (`app/api/websocket.py`) validates `INTERVIEW_AUTH_TOKEN` before accepting the connection — token can be supplied as the `x-interview-token` header **or** as a `?token=` query param. On connect it immediately creates an in-memory `LiveSession` and sends `session.ready`.

### REST API Endpoints
All under `/api` prefix. Token auth via `X-Interview-Token` header when `INTERVIEW_AUTH_TOKEN` is set.
- `GET /api/models` — returns known providers + live Ollama tags
- `POST /api/settings` — persists key/value pairs to SQLite `settings` table and hot-reloads `RuntimeState`
- `POST /api/ocr` — accepts base64 PNG, returns extracted text
- `POST /api/session/start` — creates `Session` row, registers `LiveSession`
- `POST /api/session/{id}/end` / `POST /api/session/end` — marks session ended
- `GET /health` — liveness check

### Electron IPC Boundary
The preload script (`apps/desktop/electron/preload.ts`) exposes a narrow `window.interview` API via `contextBridge`. The renderer **never** calls `ipcRenderer` directly. Main process handles `overlay:set-click-through`, `overlay:set-invisible`, `overlay:set-content-protection`, `overlay:get-content-protection`, and `screen:capture`.

Global shortcuts: `Ctrl+Shift+Space` (toggle visibility), `Ctrl+Shift+L` (listening), `Ctrl+Shift+S` (screenshot), `Ctrl+Shift+X` (click-through), `Ctrl+Shift+P` (screen-capture protection toggle).

`electron-store` persists three overlay flags between sessions: `clickThrough` (default `false`), `invisible` (default `false`), `contentProtection` (default `true`). Content protection starts ON — the overlay is hidden from screen recordings unless explicitly toggled.

Hardware acceleration is intentionally disabled in `electron/main.ts` (`app.disableHardwareAcceleration()`). GPU compositing of transparent layered windows fails silently on many Windows driver configurations; software rendering handles transparency correctly across all setups.

### Desktop TypeScript Compilation
Two compiled targets co-exist in `apps/desktop` — do not mix their tsconfig settings:

| Target | Source | Output | tsconfig | `moduleResolution` |
|--------|--------|--------|----------|--------------------|
| Renderer (React/Vite) | `src/` | `dist/` | `tsconfig.json` | `Bundler` |
| Electron main | `electron/` | `dist-electron/` | `tsconfig.electron.json` | `NodeNext` |

### Backend Services
- `app/services/llm.py` — `LlmOrchestrator` dispatches to `OpenAIProvider`, `OllamaProvider`, `GeminiProvider`, `OpenRouterProvider`. All providers implement `async stream()` returning `AsyncIterator[str]`. A new `LlmOrchestrator` is instantiated per WebSocket connection (not a singleton). `GeminiProvider` calls the Gemini REST API directly via httpx SSE — it does not use the Gemini Python SDK. `OllamaProvider` has 3-attempt retry with exponential backoff and hardcodes `keep_alive: -1` (model stays loaded) and `num_predict: 800`.
- `app/services/stt.py` — Two classes. `WhisperService` is a singleton in `app.state.stt`; the faster-whisper model loads lazily via `@cached_property` (once per process). Always CPU, int8 (`device="cpu"`, `compute_type="int8"`), English-only, `beam_size=1` for latency. `AudioBuffer` is instantiated per WebSocket connection — it accumulates raw PCM frames using energy-based VAD (`SPEECH_THRESHOLD=100` RMS), discards pre-speech silence, and flushes to `transcribe_pcm()` when 1 s of trailing silence is detected (or 5 s max). Also contains `_has_repetition()` to detect and drop Whisper hallucination loops.
- `app/services/prompt_builder.py` — Builds OpenAI-style message lists for modes: `interview`, `coding`, `system-design`.
- `app/services/session_manager.py` — In-memory `LiveSession` registry; holds `mode`, `provider`, `model`, rolling `transcript`, `screen_context`.
- `app/services/ocr.py` — `OcrService` wraps pytesseract + Pillow; processes base64 PNG frames sent as `context.screen` messages.
- `app/services/runtime.py` — `RuntimeState` holds only `settings: Settings` (not services — those live directly on `app.state`). `RuntimeState.update()` remaps incoming keys `provider` → `default_provider` and `model` → `default_model` before calling `model_copy` — use those short names when posting to `/api/settings`.
- `app/core/security.py` — `require_websocket_token(websocket, settings)` checks the `x-interview-token` header or `?token=` query param for WebSocket auth. `enforce_auth` is a FastAPI dependency for HTTP routes. Both are no-ops when `INTERVIEW_AUTH_TOKEN` is unset.
- `app/core/config.py` — `Settings` loaded via pydantic-settings from `.env`. All config accessed through `get_settings()` (cached).

### Frontend Services
- `src/services/interviewSocket.ts` — singleton WebSocket client with auto-reconnect (exponential backoff, 30 s cap). Messages queue while disconnected.
- `src/services/audioCapture.ts` — AudioWorklet pipeline streaming 16 kHz mono PCM as base64. Requires `/audio-worklet.js` to be served by Vite at the renderer root.
- `src/services/liveSpeech.ts` — wraps Web Speech API. `App.tsx` prefers this over `audioCapture` when `isSupported()` returns true; stop handler merges both text sources before sending `transcript.manual`.
- `src/services/backend.ts` — HTTP client for `/api/models` and `/api/ocr`. Adds `X-Interview-Token` header when `VITE_BACKEND_TOKEN` is set.
- `src/state/assistantStore.ts` — single Zustand store for connection state, overlay mode, transcript segments (capped at 100), streaming answer, and active tab.

## Key Design Constraints

- `LOCAL_ONLY=true` blocks all cloud providers; only Ollama is permitted.
- `TRANSCRIPT_PERSISTENCE=false` by default; transcripts are written to SQLite only when explicitly enabled.
- Electron is configured with `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true` — keep renderer code free of Node APIs.
- All new LLM providers must implement the `LlmProvider` ABC in `llm.py` and be registered in `LlmOrchestrator.providers`.
- Audio chunks are base64-encoded PCM. The server's `AudioBuffer` handles VAD and utterance detection server-side, so small frames (250 ms) work fine — `sampleRate` and `channels` in each `audio.chunk` message must match the recorded audio.
- On Windows 11, `WDA_EXCLUDEFROMCAPTURE` hides the overlay from screen recordings. Toggled at runtime via `Ctrl+Shift+P`; do not remove this when modifying window creation logic.
- CSP in `electron/main.ts` only allows `connect-src` to `localhost:8000` and `127.0.0.1:8000`. Update it if the backend port changes.
- `CORS_ORIGINS` defaults to `["http://localhost:5173"]`. Add entries (comma-separated in `.env`) if the renderer runs elsewhere.
- `requirements.lock` pins exact versions (production); `requirements.txt` uses loose ranges and is fine for local testing. `setup.ps1` and `make install` prefer the lock file but fall back to `requirements.txt` automatically.

## Environment Variables

See `.env.example` for the full list. Key ones:
- `DEFAULT_PROVIDER` / `DEFAULT_MODEL` — starting provider and model for new sessions
- `WHISPER_MODEL` — `tiny` | `base` | `medium` | `large-v3`
- `PRELOAD_WHISPER_MODEL` — `true` loads Whisper at startup instead of on first audio chunk
- `VITE_BACKEND_URL` / `VITE_WS_URL` — must match running backend for the renderer
- `VITE_BACKEND_TOKEN` — sent as `X-Interview-Token`; must match `INTERVIEW_AUTH_TOKEN` on backend
- `OLLAMA_HOST` — Ollama API base URL (default `http://localhost:11434`)
- `OPENROUTER_API_KEY` — API key for OpenRouter provider
- `LOCAL_ONLY` — `true` restricts to Ollama only
- `TRANSCRIPT_PERSISTENCE` — `true` to persist transcripts to SQLite (`data/interview_assistant.db`)
- `TRANSCRIPT_CONTEXT_SEGMENTS` — rolling window size fed into prompts (default 60)
- `LOG_LEVEL` — passed to Loguru; `DEBUG` | `INFO` | `WARNING` | `ERROR`
