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
local-rag/       # Standalone local RAG package (rag_core/); integrated by backend via sys.path injection
  rag_core/      # config, loaders, chunker, embeddings, vector_store, ingest, retriever, prompt, rag
  cli.py         # typer CLI: ingest <path>, chat, reset
  web.py         # Streamlit UI for standalone RAG use
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

Ruff rule set: `select = ["E", "F", "I", "UP", "B"]` (pycodestyle, pyflakes, isort, pyupgrade, bugbear), `ignore = ["B008"]` (function calls in default args — FastAPI `Depends()` pattern).

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
  ├─ (mid-speech, speech_duration >= stt_partial_trigger_seconds)
  │    → WhisperService.transcribe_pcm(snapshot)   [async task; cancelled if flush arrives first]
  │    → transcript.partial back over WS
  └─ (flush on silence/max)
       → WhisperService.transcribe_pcm(full utterance)
       → transcript.final back over WS
       → assistantStore transcript segments
```

**Transcript → LLM answer** (triggered by transcript.manual):
```
liveSpeech.ts (Web Speech API) or manual input → transcript.manual message
  → PromptBuilder.build()   [optionally with RAG context injected]
  → LlmOrchestrator.stream()   [new instance per WS connection]
  → assistant.delta tokens back over WS
  → assistantStore.appendAnswer()
```

**Audio → auto-answer** (triggered by QuestionDetector on Whisper transcript):
```
WhisperService.transcribe_pcm() → QuestionDetector.detect()
  → if detected: assistant.question_detected over WS
  → _handle_transcript() with provider=ollama, model=qd_model
  → same RAG + LLM streaming path as transcript.manual
```

`liveSpeech.ts` sends `transcript.manual` when the user stops speaking, merging Web Speech API text with any audioCapture text. `audio.chunk` messages are for STT only and only trigger the LLM indirectly if `QuestionDetector` fires on the resulting transcript.

When RAG is enabled, `_handle_transcript()` runs `retrieve_chunks()` in a thread executor before building the prompt, then sends `assistant.citations` before the first `assistant.delta`.

### WebSocket Message Protocol
Endpoint: `ws://host:8000/ws/interview`. Defined in `packages/shared/src/index.ts`. **Client sends:** `audio.chunk`, `transcript.manual`, `assistant.cancel`, `context.screen`, `ping`. **Server sends:** `session.ready`, `transcript.final`, `transcript.partial`, `assistant.delta`, `assistant.citations`, `assistant.question_detected`, `assistant.error`, `pong`.

- `assistant.citations` — sent before streaming when RAG retrieval finds chunks; carries `citations[]` with `source`, `page`, `snippet` (first 200 chars of chunk text), `distance`.
- `assistant.question_detected` — sent when `QuestionDetector` fires on a Whisper transcript; carries `question`, `kind` (`"question"` | `"topic_shift"`), `confidence`.

The WS handler (`app/api/websocket.py`) validates `INTERVIEW_AUTH_TOKEN` before accepting the connection — token can be supplied as the `x-interview-token` header **or** as a `?token=` query param. On connect it immediately creates an in-memory `LiveSession` and sends `session.ready`.

### REST API Endpoints
All under `/api` prefix. Token auth via `X-Interview-Token` header when `INTERVIEW_AUTH_TOKEN` is set.
- `GET /api/models` — returns known providers + live Ollama tags
- `POST /api/settings` — persists key/value pairs to SQLite `settings` table and hot-reloads `RuntimeState`; accepts only the fields in `SettingsPayload`: `provider`, `model`, `mode`, `whisper_model`, `local_only`, `transcript_persistence`
- `POST /api/ocr` — accepts base64 PNG, returns extracted text
- `POST /api/session/start` — creates `Session` row, registers `LiveSession`
- `POST /api/session/{id}/end` / `POST /api/session/end` — marks session ended
- `POST /api/documents/upload` — multipart upload; ingests PDF/DOCX/XLSX/TXT/MD into the RAG vector store; returns `{chunks_added, chunks_skipped, total_chunks}` (implemented in `app/api/documents.py`)
- `GET /api/documents` — lists ingested source filenames and total chunk count; returns 503 when RAG is not initialised
- `POST /api/documents/reset` — clears the entire ChromaDB collection
- `GET /health` — liveness check

The main REST routes (`/models`, `/settings`, `/ocr`, `/session/*`) live in `app/api/routes.py`; the document management routes live in the separate `app/api/documents.py` router.

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

### RAG Subsystem

`local-rag/` is a self-contained Python package injected into `sys.path` at runtime by `rag_retriever.py` (`Path(__file__).parents[4] / "local-rag"`). It is optional — the backend degrades gracefully when the package is absent or `RAG_ENABLED=false`.

**Pipeline:** file upload → `rag_core/loaders.py` (PDF/DOCX/XLSX/TXT) → `rag_core/chunker.py` (RecursiveCharacterTextSplitter, ~800 chars, ~120 overlap) → `rag_core/embeddings.py` (Ollama `nomic-embed-text`) → `rag_core/vector_store.py` (ChromaDB persistent client). Ingestion is idempotent — chunks are hashed so re-uploading an unchanged file skips duplicates.

**Retrieval in the backend:** `rag_retriever.py` caches the `VectorStore` in memory and only reloads when the chunk count changes (avoids ~100 ms ChromaDB HNSW init cost per query). `retrieve_chunks()` is always called in a thread executor so it doesn't block the async event loop. At startup, `warmup_embed_model()` is called in a thread executor to pre-load `nomic-embed-text` in Ollama, eliminating cold-start latency on the first real query.

**Standalone local-rag tools** (run from `local-rag/`):
```powershell
# Ingest a file or folder
python cli.py ingest ./data

# Interactive chat REPL (streaming, printed citations)
python cli.py chat

# Clear the vector store
python cli.py reset

# Streamlit web UI
streamlit run web.py
```

ChromaDB persists to `./local-rag/storage` by default (`RAG_CHROMA_PATH`). The backend and standalone tools share the same path, so documents ingested by either are immediately visible to the other.

### Question Detector

`app/services/question_detector.py` — `QuestionDetector` is instantiated once per WebSocket connection (session-scoped dedup state). It runs pure synchronous regex (~1 μs) and is safe to call in the async event loop.

**Scoring heuristic:**
- WH-word at sentence start (`what`, `how`, etc.) → 0.9 confidence, kind=`question`
- Auxiliary inversion (`Can you…`, `Is there…`) → 0.85
- Topic-shift phrases (`tell me about`, `explain`, `walk me through`) → 0.75, kind=`topic_shift`
- WH-word mid-sentence → 0.55 (needs `?` to fire)
- Trailing `?` alone → 0.55, and adds +0.1 bonus to any above score

A detection fires only when: confidence ≥ `QD_CONFIDENCE_THRESHOLD`, word count ≥ `QD_MIN_WORDS` (topic-shift: `QD_TOPIC_SHIFT_MIN_WORDS`), not within the cooldown window (`QD_COOLDOWN_SECONDS`), and not a Jaccard-duplicate of recent history (`QD_DEDUP_WINDOW_SECONDS`, `QD_DEDUP_SIMILARITY_THRESHOLD`).

When fired, the websocket handler sends `assistant.question_detected` and calls `_handle_transcript()` with `provider=ollama`, `model=qd_model` — overriding the session's configured provider. `_handle_transcript` is called with `skip_transcript_send=True` because the audio chunk handler already sent `transcript.final`; without this flag a duplicate `transcript.final` would be emitted.

### Backend Services
- `app/services/llm.py` — `LlmOrchestrator` dispatches to `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider`, `GeminiProvider`, `OpenRouterProvider`. All providers implement `async stream()` returning `AsyncIterator[str]`. A new `LlmOrchestrator` is instantiated per WebSocket connection (not a singleton). `OpenAIProvider` and `OpenRouterProvider` use the official `openai` Python SDK (`AsyncOpenAI`); `AnthropicProvider` and `GeminiProvider` call their respective REST APIs directly via httpx SSE — no official SDK. `OllamaProvider` keeps a **persistent** `httpx.AsyncClient` created at init (not per-request; `read=None` timeout, 5 s connect/write/pool to surface fast errors) with 3-attempt retry and exponential backoff; hardcodes `keep_alive: -1` (model stays loaded), `num_predict: 400`, and `num_ctx: 2048`. `GeminiProvider` also has 3-attempt retry with exponential backoff and handles 429 responses using the `Retry-After` header delay.
- `app/services/stt.py` — Two classes. `WhisperService` is a singleton in `app.state.stt`; the faster-whisper model loads lazily via `@cached_property` (once per process). Always CPU, int8 (`device="cpu"`, `compute_type="int8"`), English-only, `beam_size=1` for latency. `AudioBuffer` is instantiated per WebSocket connection — it accumulates raw PCM frames using energy-based VAD (`SPEECH_THRESHOLD=100` RMS), discards pre-speech silence, and flushes to `transcribe_pcm()` when 1 s of trailing silence is detected (or 5 s max). Also contains `_has_repetition()` to detect and drop Whisper hallucination loops.
- `app/services/prompt_builder.py` — Builds OpenAI-style message lists for modes: `interview`, `coding`, `system-design`, `senior-fullstack`. The `senior-fullstack` mode interprets any technical input — even brief keywords like "Kafka partition" — as an interview question and responds with a structured 6-part format (30-second answer, deep explanation, real-world scenario, architecture & trade-offs, common pitfalls, follow-up questions). `PromptContext.rag_searched` controls which addendum is appended to the system prompt: `rag_context` set → `_RAG_HIT_ADDENDUM` (cite docs, supplement with general knowledge); `rag_searched=True` but no chunks → `_RAG_MISS_ADDENDUM` (answer freely from general knowledge); `rag_searched=False` → no addendum. Transcript history is omitted when it equals the current question (avoids redundancy).
- `app/services/session_manager.py` — In-memory `LiveSession` registry; holds `mode`, `provider`, `model`, rolling `transcript`, `screen_context`.
- `app/services/ocr.py` — `OcrService` wraps pytesseract + Pillow; processes base64 PNG frames sent as `context.screen` messages.
- `app/services/runtime.py` — `RuntimeState` holds only `settings: Settings` (not services — those live directly on `app.state`). `RuntimeState.update()` remaps incoming keys `provider` → `default_provider` and `model` → `default_model` before calling `model_copy` — use those short names when posting to `/api/settings`.
- `app/core/security.py` — `require_websocket_token(websocket, settings)` checks the `x-interview-token` header or `?token=` query param for WebSocket auth; returns `False` and closes the socket with `WS_1008_POLICY_VIOLATION` when auth fails. Also exports `require_token`, a FastAPI dependency for HTTP routes. Both are no-ops when `INTERVIEW_AUTH_TOKEN` is unset. Note: `app/api/routes.py` defines its own local `enforce_auth` dependency (same logic) rather than importing `require_token` directly.
- `app/services/question_detector.py` — `QuestionDetector`; see [Question Detector](#question-detector) section above for full details.
- `app/core/config.py` — `Settings` loaded via pydantic-settings from `.env`. All config accessed through `get_settings()` (cached).

### Frontend Services
- `src/services/interviewSocket.ts` — singleton WebSocket client with auto-reconnect (exponential backoff, 30 s cap). Messages queue while disconnected.
- `src/services/audioCapture.ts` — AudioWorklet pipeline streaming 16 kHz mono PCM as base64. Requires `/audio-worklet.js` to be served by Vite at the renderer root.
- `src/services/liveSpeech.ts` — wraps Web Speech API. `App.tsx` prefers this over `audioCapture` when `isSupported()` returns true; stop handler merges both text sources before sending `transcript.manual`.
- `src/services/backend.ts` — HTTP client for backend REST calls. Exports `fetchModels`, `runOcr`, `uploadDocument`, `listDocuments`, `resetDocuments`, and `updateSetting`. Adds `X-Interview-Token` header when `VITE_BACKEND_TOKEN` is set.
- `src/types/shared.ts` — local type definitions used by all renderer services (`interviewSocket.ts`, `App.tsx`). These are **not** imported from `@interview/shared` — the renderer resolves types from this local file instead. Diverges slightly from `packages/shared/src/index.ts`: `TranscriptSegment.speaker` is a string union (`"interviewer" | "candidate" | "system"`) rather than a plain `string`, and `ServerMessage` omits `pong`. When updating the WS protocol, keep both files in sync.
- `src/state/assistantStore.ts` — single Zustand store for connection state, overlay mode, transcript segments (capped at 100), streaming answer, citations, and active tab.

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

See `.env.example` for the full list. Key ones (code defaults shown; `.env.example` ships with `DEFAULT_MODEL=llama3.2:3b`, `DEFAULT_MODE=senior-fullstack`, and tighter RAG chunking — copy it to `.env` as the baseline):
- `DEFAULT_PROVIDER` / `DEFAULT_MODEL` — starting provider and model for new sessions
- `DEFAULT_MODE` — starting assistant mode (`interview` | `coding` | `system-design` | `senior-fullstack`; default `interview`)
- `WHISPER_MODEL` — `tiny` | `base` | `medium` | `large-v3`
- `PRELOAD_WHISPER_MODEL` — `true` loads Whisper at startup instead of on first audio chunk
- `VITE_BACKEND_URL` / `VITE_WS_URL` — must match running backend for the renderer
- `VITE_BACKEND_TOKEN` — sent as `X-Interview-Token`; must match `INTERVIEW_AUTH_TOKEN` on backend
- `OLLAMA_HOST` — Ollama API base URL (default `http://localhost:11434`)
- `ANTHROPIC_API_KEY` — API key for `AnthropicProvider` (direct REST, no SDK)
- `GEMINI_API_KEY` — API key for `GeminiProvider` (direct REST, no SDK)
- `OPENROUTER_API_KEY` — API key for OpenRouter provider
- `LOCAL_ONLY` — `true` restricts to Ollama only
- `TRANSCRIPT_PERSISTENCE` — `true` to persist transcripts to SQLite (`data/interview_assistant.db`)
- `TRANSCRIPT_CONTEXT_SEGMENTS` — rolling window size fed into prompts (default 60)
- `LOG_LEVEL` — passed to Loguru; `DEBUG` | `INFO` | `WARNING` | `ERROR`

### STT env vars
- `STT_SILENCE_FRAMES` — number of consecutive silence frames before AudioBuffer flushes (default 2, ~500 ms at 250 ms frames)
- `STT_PARTIAL_TRIGGER_SECONDS` — seconds of accumulated speech before sending a `transcript.partial` (default 2.0)
- `STT_PARTIAL_COOLDOWN_SECONDS` — minimum interval between successive partial transcript sends (default 1.5)

### RAG env vars (prefix `RAG_`)
- `RAG_ENABLED` — `true` to enable the RAG subsystem (default `true`; degrades to no-op when `local-rag/` is absent)
- `RAG_CHROMA_PATH` — ChromaDB persistence directory (default `./local-rag/storage`). `.env.example` also sets `CHROMA_PATH` to the same value — this is read by the standalone `local-rag/` tools (cli.py / web.py) which use their own settings object; both vars must point to the same path when the backend and standalone tools coexist.
- `RAG_COLLECTION_NAME` — ChromaDB collection (default `documents`)
- `RAG_EMBED_MODEL` — Ollama embedding model (default `nomic-embed-text`)
- `RAG_LLM_MODEL` — model used for Streamlit/CLI RAG chat (default `llama3.1:8b`); the backend WS path uses the session's model
- `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` — splitter config (code defaults 800 / 120; `.env.example` ships 350 / 50 for tighter retrieval)
- `RAG_TOP_K` — number of chunks to retrieve (code default 4; `.env.example` ships 5)
- `RAG_DISTANCE_THRESHOLD` — ChromaDB cosine distance cutoff; chunks above this are dropped (default 1.4; lower = stricter)
- `RAG_TEMPERATURE` — generation temperature for standalone RAG chat (default 0.2)

### Question Detector env vars (prefix `QD_`)
These are **not** in `.env.example` — they are code defaults only. Add them manually to `.env` to override.
- `QD_ENABLED` — `true` to enable auto-answer from audio transcripts (default `true`)
- `QD_CONFIDENCE_THRESHOLD` — minimum score to trigger (default 0.6)
- `QD_MIN_WORDS` — minimum word count for questions (default 4)
- `QD_TOPIC_SHIFT_MIN_WORDS` — minimum word count for topic-shift phrases (default 6)
- `QD_DEDUP_WINDOW_SECONDS` — how long to remember recent triggers for dedup (default 30)
- `QD_DEDUP_SIMILARITY_THRESHOLD` — Jaccard similarity above which a new trigger is suppressed (default 0.85)
- `QD_MODEL` — Ollama model used for auto-answered questions (default `llama3`)
- `QD_COOLDOWN_SECONDS` — minimum seconds between auto-triggers (default 5)
- `QD_LOG_DETECTIONS` — `true` to debug-log every detector result (default `true`)
