# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Interview Assistant Overlay — a production desktop app combining an Electron transparent overlay, real-time microphone streaming, FastAPI WebSockets, Whisper transcription, OCR screen context, and streaming LLM answers.

## Repository Layout

```
apps/
  backend/       # Python FastAPI backend (uvicorn, asyncio, SQLAlchemy)
  desktop/       # Electron + React + TypeScript overlay app (Vite) — has its own CLAUDE.md
packages/
  shared/        # Shared TypeScript types (ClientMessage, ServerMessage, OverlayMode, etc.)
  ui/            # Shared UI component library
scripts/         # PowerShell setup/dev scripts
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

## Architecture

### Real-Time Pipeline
```
Microphone → audioCapture.ts → base64 PCM chunks
  → WebSocket (ws://localhost:8000/ws/interview)
  → WhisperService.transcribe_pcm()
  → PromptBuilder.build()
  → LlmOrchestrator.stream()
  → assistant.delta tokens back over WS
  → assistantStore.appendAnswer()
```

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
The preload script (`apps/desktop/electron/preload.ts`) exposes a narrow `window.interview` API via `contextBridge`. The renderer **never** calls `ipcRenderer` directly. Main process handles `overlay:set-click-through`, `overlay:set-invisible`, and `screen:capture`.

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
- `app/services/llm.py` — `LlmOrchestrator` dispatches to `OpenAIProvider`, `OllamaProvider`, `GeminiProvider`, `OpenRouterProvider`. All providers implement `async stream()` returning `AsyncIterator[str]`.
- `app/services/stt.py` — `WhisperService` wraps faster-whisper; loads model once, processes raw PCM bytes.
- `app/services/prompt_builder.py` — Builds OpenAI-style message lists for modes: `interview`, `coding`, `system-design`.
- `app/services/session_manager.py` — In-memory `LiveSession` registry; holds `mode`, `provider`, `model`, rolling `transcript`, `screen_context`.
- `app/services/ocr.py` — `OcrService` wraps pytesseract + Pillow; processes base64 PNG frames sent as `context.screen` messages.
- `app/services/runtime.py` — `RuntimeState` singleton initialized at lifespan; holds references to all services and is injected into route handlers via FastAPI dependency. `RuntimeState.update()` remaps incoming keys `provider` → `default_provider` and `model` → `default_model` before calling `model_copy` — use those short names when posting to `/api/settings`.
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
- Audio chunks must arrive as base64-encoded PCM, 1–2 seconds max, at the sample rate specified in the `audio.chunk` message.
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
- `LOCAL_ONLY` — `true` restricts to Ollama only
- `TRANSCRIPT_PERSISTENCE` — `true` to persist transcripts to SQLite (`data/interview_assistant.db`)
- `TRANSCRIPT_CONTEXT_SEGMENTS` — rolling window size fed into prompts (default 60)
- `LOG_LEVEL` — passed to Loguru; `DEBUG` | `INFO` | `WARNING` | `ERROR`
