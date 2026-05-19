# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Development
npm run dev              # Vite renderer only (port 5173) — for UI iteration
npm run electron:dev     # Build Electron main + launch full desktop app

# Build
npm run build            # Full build: tsc (renderer) + vite build + tsc (electron)
npm run package          # Full build + electron-builder → release/

# Quality
npm run lint             # ESLint over src/**/*.{ts,tsx} and electron/**/*.ts
npm run test             # Vitest (run once, no watch)
npx vitest run src/ui/App.test.tsx  # Run a single test file
```

## Architecture

This is a monorepo workspace package (`@interview/desktop`). The `@interview/shared` and `@interview/ui` packages are resolved via TypeScript path aliases pointing to `../../packages/shared/src/index.ts` and `../../packages/ui/src/index.ts` — those sibling packages must exist for the build to succeed.

### Two compiled targets

| Target | Source | Output | tsconfig |
|--------|--------|--------|----------|
| Renderer (React/Vite) | `src/` | `dist/` | `tsconfig.json` |
| Electron main | `electron/` | `dist-electron/` | `tsconfig.electron.json` |

The renderer uses `moduleResolution: Bundler`; the electron main uses `NodeNext`. Never mix them.

### Data flow

```
electron/main.ts  ──IPC──  electron/preload.ts  ──contextBridge──  window.interview
                                                                          │
                                                               src/ui/App.tsx
                                                                    │         │
                                                         interviewSocket   audioCapture
                                                                    │         │
                                                         backend WS :8000  backend HTTP :8000
```

- **`interviewSocket`** (`src/services/interviewSocket.ts`) — singleton WebSocket client. Handles auto-reconnect with exponential backoff (cap 30 s). Messages queue while disconnected. Types come from `@interview/shared`.
- **`audioCapture`** (`src/services/audioCapture.ts`) — AudioWorklet pipeline (`/audio-worklet.js` must be served by Vite) that streams 16 kHz mono PCM chunks as base64 over the WebSocket.
- **`liveSpeech`** (`src/services/liveSpeech.ts`) — wraps Web Speech API. `App.tsx` prefers this over `audioCapture` when `isSupported()` is true; the stop handler merges both text sources before sending `transcript.manual`.
- **`useAssistantStore`** (`src/state/assistantStore.ts`) — single Zustand store for all UI state. Transcript is capped at 100 segments.
- **`backend.ts`** (`src/services/backend.ts`) — HTTP calls for `/api/models` and `/api/ocr`. Uses `X-Interview-Token` header when `VITE_BACKEND_TOKEN` is set.

### Electron overlay specifics

The window is frameless, transparent, always-on-top (`screen-saver` level), visible on all workspaces including full-screen apps. Persistent settings (click-through, invisible) are stored via `electron-store`.

IPC channels exposed through `preload.ts` as `window.interview`:
- `overlay:set-click-through` / `overlay:set-invisible` — window behaviour
- `screen:capture` — uses `desktopCapturer`, returns PNG as base64 string
- `shortcut:listening` / `shortcut:screenshot` — fired by global shortcuts

Global shortcuts: `Ctrl+Shift+Space` (toggle visibility), `Ctrl+Shift+L` (listening), `Ctrl+Shift+S` (screenshot), `Ctrl+Shift+X` (click-through).

CSP (set in `main.ts`) only allows `connect-src` to `localhost:8000` and `127.0.0.1:8000`. Update it if the backend URL changes.

### Environment variables

| Variable | Default |
|----------|---------|
| `VITE_BACKEND_URL` | `http://localhost:8000` |
| `VITE_WS_URL` | `ws://localhost:8000/ws/interview` |
| `VITE_BACKEND_TOKEN` | _(empty — auth disabled)_ |

### Testing

Vitest + jsdom + `@testing-library/react`. Setup file: `src/test/setup.ts` (imports `@testing-library/jest-dom/vitest`). Tests guard against running real services by checking `import.meta.env.MODE === "test"` in `App.tsx`.
