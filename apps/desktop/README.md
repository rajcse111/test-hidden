# AI Interview Assistant — Desktop

A frameless, always-on-top Electron overlay that wraps the React UI for an interview-assistant. The overlay window is **excluded from screen-capture** on Windows 10 2004+ and macOS, so it's visible to you on your monitor but invisible to Zoom / Teams / Meet / OBS / Snipping Tool when you share your screen.

---

## "Wait, is this still a React app running in a browser?"

This is the most important thing to understand about the project, so it gets its own section.

**No.** When you run `npm run electron:dev`, the React app does not open in Chrome, Edge, or any browser tab. It runs inside an **Electron window**, which is a real native Windows application. Concretely:

- `electron.exe` is a Win32 executable. When it starts, it spawns a **main process** (Node.js) and one or more **renderer processes** (Chromium).
- The main process (our `electron/main.ts`) calls `new BrowserWindow(...)`. That creates a real native **Win32 window** — a real `HWND` that the operating system tracks, with its own entry in Task Manager and Alt-Tab.
- That `HWND` hosts an embedded Chromium instance — essentially Chrome's renderer engine running in-process, *not* as a separate browser application.
- The main process tells that Chromium instance to load `http://localhost:5173` (in dev) or `file://.../dist/index.html` (in production). Your React app's HTML/CSS/JS then renders inside that window.

So your React app is still React. What changed is **where** it runs. Instead of being painted into a tab inside Chrome's process tree, it's painted into a Win32 window that Electron owns. From the operating system's perspective, the thing on your desktop is `electron.exe`, not `chrome.exe`. That's what makes this a "desktop application" — there's a real native window with a real `HWND`, registered with the OS, and we can call Win32 APIs against it.

```
                     Your screen
   ┌────────────────────────────────────────────────┐
   │                                                │
   │   ┌──────────────────┐    ┌─────────────────┐  │
   │   │  electron.exe    │    │  zoom.exe       │  │
   │   │  (HWND #1234)    │    │  (HWND #5678)   │  │
   │   │                  │    │                 │  │
   │   │  ┌────────────┐  │    │  share screen → │  │
   │   │  │ Chromium   │  │    │  ┌───────────┐  │  │
   │   │  │ rendering  │  │    │  │ DWM frame │  │  │
   │   │  │ your React │  │    │  │ minus     │  │  │
   │   │  │ App.tsx    │  │    │  │ HWND 1234 │  │  │
   │   │  └────────────┘  │    │  └───────────┘  │  │
   │   └──────────────────┘    └─────────────────┘  │
   │                                                │
   └────────────────────────────────────────────────┘
            ▲
            │  setContentProtection(true) on HWND 1234
            │  → SetWindowDisplayAffinity(HWND, WDA_EXCLUDEFROMCAPTURE)
            │  → DWM excludes HWND 1234 from all capture frames
```

**Yes, your React app is now invisible to the remote viewer.** Because the React app renders inside `HWND 1234`, and `HWND 1234` has the `WDA_EXCLUDEFROMCAPTURE` flag set, the DWM (the Windows compositor) excludes `HWND 1234` from every frame it hands to capture clients. Zoom asks "what's on the screen?" → DWM hands back a frame that has your wallpaper, your IDE, your browser, your Slack — but the rectangle where `HWND 1234` lives is filled in with whatever was behind it. Zoom encodes that frame and ships it to the remote viewer. The remote viewer sees no overlay. You, looking at your physical monitor, still see the overlay because the GPU is composing it onto the actual display.

### The two run modes (this is where confusion happens)

This repo has two `npm` scripts and they do very different things:

| Script | What runs | Where the React UI shows up | Protected from screen share? |
|---|---|---|---|
| `npm run dev` | Vite dev server only | You manually open `http://localhost:5173` in **your normal browser** (Chrome/Edge) | **No.** Your browser has no special HWND; it's just a regular browser tab inside `chrome.exe`. Anything in a chrome.exe window will be captured normally. |
| `npm run electron:dev` | Vite dev server + `electron.exe` | A dedicated frameless Electron window appears in the top-right of your primary monitor | **Yes.** Electron's window has `setContentProtection(true)` applied. Capture clients receive frames with that window cut out. |

If you want to verify the desktop-app effect, you **must** use `npm run electron:dev`. Running `npm run dev` and opening localhost in Chrome will show the UI but will not give you any capture protection — Chrome is a normal program and its windows show up in screen shares like everything else.

### Why we don't / can't do this with just a browser

The capture-exclusion API is a Win32 / macOS / window-server API that operates on a native window handle. A browser tab is not a window — it's a region inside a window that the browser owns. There is no public web API a JavaScript page can call to say "hide me from screen capture." So a pure web app, no matter how good, fundamentally cannot do this — you need a native shell. Electron, Tauri, .NET WPF, Qt, Win32 C++ — any of these would work because they all give you direct access to your own `HWND`. We chose Electron because it lets us keep your existing React code unchanged.

### So where is "the Windows app"?

It's `electron.exe` plus its bundled resources. In dev mode it lives in `node_modules\electron\dist\electron.exe`. When you eventually run `npm run package`, electron-builder bundles your compiled React renderer + the Electron runtime + an NSIS installer into `release\AI Interview Assistant Setup.exe` — that single `.exe` is the shippable Windows desktop application you'd send to another user. They double-click it, NSIS installs it under `%LOCALAPPDATA%\Programs\AI Interview Assistant\`, and they get a Start-menu entry that launches the protected overlay. No browser involved at any point on the end-user's machine.

---

## Quick start (Windows 11)

You're on Windows 11 Home 25H2, build 26200 — that's well above the Windows 10 build 19041 cutoff, so `WDA_EXCLUDEFROMCAPTURE` is fully supported and the overlay will be invisible to screen sharing out of the box.

### Prerequisites

1. **Node.js 20 LTS or newer.** Install from <https://nodejs.org/en/download> or via winget:
   ```powershell
   winget install OpenJS.NodeJS.LTS
   ```
   Verify in a new PowerShell window: `node -v` should print `v20.x` or higher.
2. **Git** (optional, only if you're cloning). `winget install Git.Git`.
3. **A working backend on `http://localhost:8000`** that speaks the WebSocket protocol described in `src/types/shared.ts`. Without it the UI loads and the overlay window works, but transcription / AI answers stay idle. You can also point the renderer at any other backend via env vars (see below).

### Install and run — the protected desktop app

Open PowerShell in this folder (`C:\Users\Rajesh Kumar\Desktop\test_hidden\desktop`) and run two commands in **two separate terminals**:

Terminal 1 — start the Vite dev server that serves the React code:
```powershell
npm install      # only the first time
npm run dev
```

Terminal 2 — launch the Electron desktop window that loads it:
```powershell
npm run electron:dev
```

The first terminal stays running and prints `Local: http://localhost:5173`. The second terminal compiles `electron/*.ts` to `dist-electron/`, launches `electron.exe`, which opens a frameless overlay window in the top-right of your primary monitor. **That overlay window is the desktop app and it is invisible to screen sharing.** Do not open `http://localhost:5173` in Chrome/Edge — that browser tab is not protected and will show up in screen shares like any other browser content.

`npm install` will take a few minutes the first time — Electron is ~250 MB. Subsequent installs are cached.

### Optional: browser-only mode for UI iteration

If you're tweaking the React UI and don't care about the overlay behaviour for the moment, you can run only Terminal 1 (`npm run dev`) and open `http://localhost:5173` in your normal browser. This is **not** the desktop app — it's the same React code running inside Chrome/Edge. Faster reload, regular DevTools, but:

- `window.interview` is `undefined`, so the click-through, invisible-mode, capture-protection, and screen-capture buttons silently no-op.
- The page is not protected from screen capture — anything you do in this browser tab is fully visible in screen shares.

Use this mode for UI work only. Use `npm run electron:dev` whenever you want to test the actual desktop-app behaviour.

### Global keyboard shortcuts

Registered by the Electron main process; work even when the overlay isn't focused.

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+Space` | Show / hide the overlay |
| `Ctrl+Shift+L` | Toggle listening (mic capture + speech recognition) |
| `Ctrl+Shift+S` | Capture screen → OCR → push as context to the backend |
| `Ctrl+Shift+X` | Toggle click-through (overlay ignores mouse) |
| `Ctrl+Shift+P` | Toggle screen-capture protection on the overlay window |

---

## Architecture

There are two TypeScript compilation targets in one folder: a renderer (browser-side React) and an Electron main process (Node-side). They never share a build output and they use different module resolution strategies.

```
                            ┌──────────────────────────────────┐
                            │   electron/main.ts (Node, ESM)   │
                            │   - BrowserWindow setup          │
                            │   - setContentProtection(true)   │
                            │   - Global shortcuts             │
                            │   - desktopCapturer (screenshot) │
                            │   - electron-store (settings)    │
                            └──────────────┬───────────────────┘
                                           │ ipcMain.handle(...)
                                           │
                            ┌──────────────┴───────────────────┐
                            │   electron/preload.ts            │
                            │   - contextBridge.exposeInMain   │
                            │     World("interview", api)      │
                            └──────────────┬───────────────────┘
                                           │ window.interview.*
                                           │
                            ┌──────────────┴───────────────────┐
                            │   src/  (React + Vite renderer)  │
                            │                                  │
                            │   ui/App.tsx                     │
                            │     │                            │
                            │     ├─ state/assistantStore.ts   │
                            │     │   (Zustand)                │
                            │     │                            │
                            │     ├─ services/                 │
                            │     │   ├ interviewSocket.ts     │  WS  → backend :8000
                            │     │   ├ audioCapture.ts        │  WS  → backend :8000
                            │     │   ├ liveSpeech.ts          │  Web Speech API
                            │     │   └ backend.ts             │  HTTP → backend :8000
                            │     │                            │
                            │     └─ types/shared.ts           │
                            │         (ClientMessage / Server  │
                            │          Message contracts)      │
                            └──────────────────────────────────┘
```

### The two compilation targets

| Target | Source | Output | tsconfig | Module resolution |
|--------|--------|--------|----------|-------------------|
| Renderer (React/Vite) | `src/` | `dist/` (served by Vite in dev) | `tsconfig.json` | `Bundler` |
| Electron main | `electron/` | `dist-electron/` | `tsconfig.electron.json` | `NodeNext` |

Never mix imports across these two trees: the renderer must not `import "electron"`, and the main process must not import React. The bridge between them is `electron/preload.ts`, which exposes a typed object on `window.interview`.

### Screen-capture exclusion (the headline feature)

The overlay is invisible to screen-capture software because `electron/main.ts` calls:

```ts
mainWindow.setContentProtection(true);
```

`mainWindow` here is the `BrowserWindow` returned by Electron — and crucially, every `BrowserWindow` corresponds 1:1 to a native Win32 `HWND`. So calling `setContentProtection(true)` is really tagging that `HWND` with a flag. Electron implements it as `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` on Windows.

The flag is read by the **Desktop Window Manager** — the OS compositor that builds the final screen image out of all the visible windows. DWM continues to composite this window onto your physical display (so you see it), but it omits the window from any framebuffer it hands to a capture client. Zoom, Teams, Meet, OBS, the Windows Snipping Tool, Windows.Graphics.Capture, GDI BitBlt, Desktop Duplication API, DXGI capture, and PrintScreen all end up with a frame as if the window weren't there.

Your React app renders **inside** this window, so the protection is automatic — there is nothing you need to do in your React code, and there's no API a regular web page could call to opt into this. It works because Electron gives you a native HWND that you can flag from the Node side.

On macOS this maps to `NSWindowSharingNone`. On Linux it's a no-op (Wayland and X11 have no equivalent).

**Caveats — read these before assuming you're invisible.**

The protection only works against software capture going through documented OS APIs. It does **not** defeat:

- A physical camera pointed at your monitor.
- An HDMI capture card sitting between your GPU and display.
- Hypervisor-level capture (your OS running inside a VM whose host captures the framebuffer).
- Custom kernel-mode capture drivers reading GPU memory directly.

It also requires hardware GPU composition; if DWM is disabled or you fall back to software rendering, behaviour varies.

### IPC contract (`window.interview`)

Renderer code calls these — they're defined in `electron/preload.ts` and handled in `electron/main.ts`.

| Method | Direction | Effect |
|--------|-----------|--------|
| `setClickThrough(enabled)` | renderer → main | Window ignores mouse events when `true` |
| `setInvisible(enabled)` | renderer → main | Opacity drops to ~2%, hides from taskbar |
| `setContentProtection(enabled)` | renderer → main | Toggles `SetWindowDisplayAffinity` |
| `getContentProtection()` | renderer → main | Returns the current persisted state |
| `captureScreen()` | renderer → main | Returns a base64 PNG of the primary screen |
| `onToggleListening(cb)` | main → renderer | Fired by `Ctrl+Shift+L` |
| `onCaptureScreen(cb)` | main → renderer | Fired by `Ctrl+Shift+S` |
| `onContentProtectionChange(cb)` | main → renderer | Fired by `Ctrl+Shift+P` |

Settings persist between runs via `electron-store` (stored in `%APPDATA%\AI Interview Assistant\config.json` on Windows).

### React renderer

- **`src/ui/App.tsx`** — single-file UI. Hosts the header (status, connection indicator, action icons), tab nav, and panels for Audio Input, Transcript, Answers, Analysis, Notes, Settings. Wires global shortcuts to local handlers via `window.interview.onToggleListening` / `onCaptureScreen`.
- **`src/state/assistantStore.ts`** — Zustand store. Single source of truth for connection state, session id, transcript (capped at 100 segments), AI answer stream, click-through flag, overlay mode, active tab, notes.
- **`src/services/interviewSocket.ts`** — singleton WebSocket client. Reconnects with exponential backoff capped at 30 s. Messages queue while disconnected and flush on `onopen`. Strongly typed against `ClientMessage` / `ServerMessage`.
- **`src/services/audioCapture.ts`** — `getUserMedia` → `AudioWorkletNode` (`/audio-worklet.js`) pipeline that emits 16 kHz mono PCM chunks, base64-encoded, over the socket as `audio.chunk` messages.
- **`src/services/liveSpeech.ts`** — wraps Web Speech API (`webkitSpeechRecognition`). When available the UI uses this in preference to `audioCapture` for partial / final transcript display, because it runs locally and avoids round-tripping to the backend.
- **`src/services/backend.ts`** — plain `fetch` calls for `/api/models` and `/api/ocr`. Attaches `X-Interview-Token` if `VITE_BACKEND_TOKEN` is set.
- **`src/types/shared.ts`** — WebSocket message contracts (client → server and server → client). Was previously a sibling monorepo package; inlined here so this folder builds standalone.
- **`src/lib/logger.ts`** — thin `console.*` wrapper.

### Window properties

```ts
new BrowserWindow({
  width: 560, height: 680, x: <right edge>, y: 60,
  frame: false,            // no title bar
  transparent: true,        // alpha-blended background
  resizable: true,
  alwaysOnTop: true,        // promoted to "screen-saver" level
  hasShadow: false,
  backgroundColor: "#00000000",
  webPreferences: {
    preload: "preload.js",
    contextIsolation: true,
    nodeIntegration: false, // renderer cannot require()
    sandbox: true,
  },
});
mainWindow.setAlwaysOnTop(true, "screen-saver");
mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
mainWindow.setContentProtection(true); // ← the capture-exclusion bit
```

`screen-saver` is the highest stacking level on Windows; combined with `visibleOnFullScreen: true` this keeps the overlay above full-screen presenter mode in Teams/Zoom.

### CSP

The renderer is locked down by a Content-Security-Policy header injected from `main.ts`. By default it only allows network connections to `localhost:8000` and `127.0.0.1:8000` (HTTP + WS). If you point at a remote backend, edit the CSP — otherwise the WebSocket will be blocked by the browser engine.

---

## Configuration

All renderer config is via Vite env vars. Create a `.env.local` in this folder:

```
VITE_BACKEND_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws/interview
VITE_BACKEND_TOKEN=
```

| Variable | Default | Used by |
|----------|---------|---------|
| `VITE_BACKEND_URL` | `http://localhost:8000` | `src/services/backend.ts` |
| `VITE_WS_URL` | `ws://localhost:8000/ws/interview` | `src/services/interviewSocket.ts` |
| `VITE_BACKEND_TOKEN` | _(empty — auth disabled)_ | both, sent as `X-Interview-Token` |

Restart `npm run electron:dev` after changing env vars.

---

## Scripts

```powershell
npm run dev              # Vite renderer only — UI in browser at :5173 (no Electron, no overlay APIs)
npm run electron:dev     # Compile Electron + launch the full overlay app
npm run build            # Production build of renderer + Electron main
npm run package          # Full build + electron-builder → release\AI Interview Assistant Setup.exe
npm run lint             # ESLint over src/ and electron/
npm run test             # Vitest (jsdom + @testing-library/react)
npm run preview          # Serve the production-built renderer for sanity check
```

---

## Verifying screen-capture exclusion

The quickest way to prove it works:

1. Start the app: `npm run electron:dev`. The overlay appears in the top-right corner.
2. Open Zoom / Teams / Meet and start a meeting alone (or with yourself on another device).
3. Click **Share Screen → Entire Screen**. Look at the shared-screen preview thumbnail.
4. The overlay should be **gone** from the shared feed but **still visible** to you on your monitor.
5. Press `Ctrl+Shift+P` to toggle protection off; the overlay reappears in the shared feed. Press it again to hide.

You can also test with Windows Snipping Tool — press `Win+Shift+S`, drag a region over the overlay, and the captured image will show your wallpaper underneath where the overlay was.

---

## Troubleshooting

**`npm install` fails on `node-gyp` / Python errors.** This is usually `electron-store`'s native deps. Install build tools: `npm install --global windows-build-tools` (older Node) or rely on Node 20+ which bundles enough. Alternatively delete `node_modules` and `package-lock.json` and retry.

**The Electron window appears blank / white.** The renderer at `http://localhost:5173` isn't reachable. `npm run electron:dev` runs `electron:build` then launches Electron, but it doesn't start Vite for you — open a second terminal and run `npm run dev` first, then `npm run electron:dev` in the original terminal. If you want them combined, install `concurrently` and adjust the script.

**The overlay shows up in screen shares.** Check (a) you're on Windows 10 build 19041+ — you are; (b) DWM/hardware composition is enabled (it always is on stock Windows 11); (c) you didn't press `Ctrl+Shift+P` and toggle protection off. The persisted state in `%APPDATA%\AI Interview Assistant\config.json` survives restarts, so if you toggled it off once it'll come back off.

**"Cannot find module '@interview/shared'".** This folder used to be part of a monorepo. The shared types were inlined into `src/types/shared.ts`; the broken workspace deps were removed from `package.json`. If you see this error, you're probably looking at a pre-fix checkout — re-clone or re-pull.

**Global shortcuts don't fire.** Another app has registered the same combo. Pick a free combo and update `registerShortcuts()` in `electron/main.ts`. On Windows, `Ctrl+Shift+Space` sometimes conflicts with input-method switchers.

**Listening / transcription doesn't work.** The backend at `localhost:8000` isn't running or doesn't speak the WebSocket protocol in `src/types/shared.ts`. Open DevTools (Ctrl+Shift+I in Electron, or just use `npm run dev` in a browser) and watch the Network → WS tab.

---

## Security notes

- `contextIsolation: true` and `nodeIntegration: false`: the renderer cannot `require("fs")` or otherwise touch Node APIs. Anything it needs from Node comes through `electron/preload.ts`, which is explicitly typed and audited.
- `sandbox: true`: the renderer runs in a Chromium sandbox process.
- The CSP forbids inline `<script>` and only allows the configured backend origin.
- The screen-capture exclusion does not protect against malicious software running locally; it's a UX feature, not an anti-malware tool.

---

## File map

```
desktop/
├── electron/
│   ├── main.ts          # Electron main process — window, IPC, shortcuts, capture protection
│   └── preload.ts       # contextBridge → window.interview
├── src/
│   ├── main.tsx         # React entry
│   ├── styles.css       # Tailwind base + drag/no-drag regions
│   ├── config.ts        # Env-var read
│   ├── vite-env.d.ts    # window.interview type, vite/client refs
│   ├── ui/
│   │   ├── App.tsx
│   │   └── App.test.tsx
│   ├── state/
│   │   └── assistantStore.ts
│   ├── services/
│   │   ├── interviewSocket.ts
│   │   ├── audioCapture.ts
│   │   ├── liveSpeech.ts
│   │   └── backend.ts
│   ├── types/
│   │   └── shared.ts    # WS message contracts (inlined from former workspace pkg)
│   ├── lib/
│   │   └── logger.ts
│   └── test/setup.ts
├── public/
│   └── audio-worklet.js # 16 kHz PCM worklet served at /audio-worklet.js
├── index.html
├── vite.config.ts
├── vitest.config.ts
├── tailwind.config.ts
├── postcss.config.js
├── tsconfig.json          # Renderer (Bundler resolution)
├── tsconfig.electron.json # Main process (NodeNext resolution)
├── package.json
└── README.md
```
