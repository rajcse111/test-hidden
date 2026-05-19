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
```

## Common Commands

### Setup
```bash
# Windows one-shot setup
.\scripts\setup.ps1

# Manual (Windows)
npm install
python -m venv .venv
.venv\Scripts\activate
pip install -r apps\backend\requirements.txt
copy .env.example .env
```

### Development
```bash
# Backend — activate venv first, then run (Windows)
.venv\Scripts\activate
npm run backend:dev

# Desktop renderer (Vite dev server at :5173)
npm run dev --workspace @interview/desktop

# Both via Makefile (spawns two PowerShell windows via scripts/dev.ps1)
make dev
```

### Testing
```bash
# Backend tests (asyncio_mode = "auto" — all async tests work without extra decorators)
.venv/Scripts/pytest apps/backend/tests

# Single backend test file
.venv/Scripts/pytest apps/backend/tests/test_prompt_builder.py

# Desktop tests (Vitest, run once)
npm run test --workspace @interview/desktop

# Single desktop test file
npx vitest run apps/desktop/src/ui/App.test.tsx
```

### Linting
```bash
make lint
# or:
.venv/Scripts/ruff check apps/backend
npm run lint
```

### Build & Package
```bash
npm run build --workspace @interview/desktop
npm run desktop:package        # Electron Builder → NSIS/DMG/AppImage
make docker-up                 # Backend-only Docker
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
Defined in `packages/shared/src/index.ts`. **Client sends:** `audio.chunk`, `transcript.manual`, `assistant.cancel`, `context.screen`. **Server sends:** `session.ready`, `transcript.final`, `transcript.partial`, `assistant.delta`, `assistant.error`, `pong`.

### Electron IPC Boundary
The preload script (`apps/desktop/electron/preload.ts`) exposes a narrow `window.interview` API via `contextBridge`. The renderer **never** calls `ipcRenderer` directly. Main process handles `overlay:set-click-through`, `overlay:set-invisible`, and `screen:capture`.

Global shortcuts: `Ctrl+Shift+Space` (toggle visibility), `Ctrl+Shift+L` (listening), `Ctrl+Shift+S` (screenshot), `Ctrl+Shift+X` (click-through), `Ctrl+Shift+P` (screen-capture protection toggle).

### Backend Services
- `app/services/llm.py` — `LlmOrchestrator` dispatches to `OpenAIProvider`, `OllamaProvider`, `GeminiProvider`, `OpenRouterProvider`. All providers implement `async stream()` returning `AsyncIterator[str]`.
- `app/services/stt.py` — `WhisperService` wraps faster-whisper; loads model once, processes raw PCM bytes.
- `app/services/prompt_builder.py` — Builds OpenAI-style message lists for modes: `interview`, `coding`, `system-design`.
- `app/services/session_manager.py` — In-memory `LiveSession` registry; holds `mode`, `provider`, `model`, rolling `transcript`, `screen_context`.
- `app/services/ocr.py` — `OcrService` wraps pytesseract + Pillow; processes base64 PNG frames sent as `context.screen` messages.
- `app/services/runtime.py` — `RuntimeState` singleton initialized at lifespan; holds references to all services and is injected into route handlers via FastAPI dependency.
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

## Environment Variables

See `.env.example` for the full list. Key ones:
- `DEFAULT_PROVIDER` / `DEFAULT_MODEL` — starting provider and model for new sessions
- `WHISPER_MODEL` — `tiny` | `base` | `medium` | `large-v3`
- `VITE_BACKEND_URL` / `VITE_WS_URL` — must match running backend for the renderer
- `LOCAL_ONLY` — `true` restricts to Ollama only
- `TRANSCRIPT_PERSISTENCE` — `true` to persist transcripts to SQLite
