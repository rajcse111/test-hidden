import { app, BrowserWindow, desktopCapturer, globalShortcut, ipcMain, nativeImage, screen, session, shell } from "electron";
import Store from "electron-store";
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isDev = !app.isPackaged;

// On Windows, GPU compositing of transparent layered windows fails silently
// on many driver configurations, leaving the window physically invisible.
// Software rendering handles transparency correctly on all Windows setups.
app.disableHardwareAcceleration();
const store = new Store<{ clickThrough: boolean; invisible: boolean; contentProtection: boolean }>({
  defaults: { clickThrough: false, invisible: false, contentProtection: true },
});

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

function startBackend(): void {
  if (!isDev) return; // packaged app bundles its own backend launch mechanism
  const projectRoot = path.join(__dirname, "..", "..", "..");
  const pythonExe =
    process.platform === "win32"
      ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
      : path.join(projectRoot, ".venv", "bin", "python");
  const backendDir = path.join(projectRoot, "apps", "backend");
  const startedAt = Date.now();

  backendProcess = spawn(
    pythonExe,
    ["-m", "uvicorn", "app.main:app", "--app-dir", backendDir, "--host", "0.0.0.0", "--port", "8000"],
    { cwd: projectRoot, env: { ...process.env, PYTHONPATH: backendDir } }
  );

  backendProcess.stderr?.on("data", (data: Buffer) => {
    console.error("[backend]", data.toString().trimEnd());
  });

  backendProcess.on("exit", (code) => {
    backendProcess = null;
    const lived = Date.now() - startedAt;
    if (lived >= 3000) {
      // Crash after running — restart after short delay
      console.log(`[backend] exited (code=${code}) after ${lived}ms — restarting in 2 s`);
      setTimeout(startBackend, 2000);
    } else {
      // Died immediately: port already in use or venv not found — don't loop
      console.log(`[backend] exited (code=${code}) after ${lived}ms — port in use or startup error, not restarting`);
    }
  });
}

function createWindow(): void {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width } = primaryDisplay.workAreaSize;

  mainWindow = new BrowserWindow({
    width: 560,
    height: 680,
    x: width - 600,
    y: 60,
    frame: false,
    transparent: false,
    resizable: true,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    backgroundColor: "#111827",
    titleBarStyle: "hidden",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.setAlwaysOnTop(true, "floating");
  mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  mainWindow.setIgnoreMouseEvents(store.get("clickThrough"), { forward: true });
  if (store.get("invisible")) mainWindow.setOpacity(0.02);
  store.set("contentProtection", true);
  mainWindow.setContentProtection(true);

  if (isDev) {
    void mainWindow.loadURL("http://localhost:5173");
  } else {
    void mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });
}

function registerShortcuts(): void {
  globalShortcut.register("CommandOrControl+Shift+Space", () => {
    if (!mainWindow) return;
    mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
  });

  globalShortcut.register("CommandOrControl+Shift+L", () => {
    mainWindow?.webContents.send("shortcut:listening");
  });

  globalShortcut.register("CommandOrControl+Shift+X", () => {
    const next = !store.get("clickThrough");
    store.set("clickThrough", next);
    mainWindow?.setIgnoreMouseEvents(next, { forward: true });
    mainWindow?.webContents.send("overlay:click-through", next);
  });

  globalShortcut.register("CommandOrControl+Shift+S", () => {
    mainWindow?.webContents.send("shortcut:screenshot");
  });

  // Toggle the screen-capture exclusion at runtime (Ctrl+Shift+P).
  // Useful for quickly proving the effect during a Zoom test: with it ON the
  // window vanishes in the shared screen feed; with it OFF the window appears.
  globalShortcut.register("CommandOrControl+Shift+P", () => {
    const next = !store.get("contentProtection");
    store.set("contentProtection", next);
    mainWindow?.setContentProtection(next);
    mainWindow?.webContents.send("overlay:content-protection", next);
  });
}

app.whenReady().then(() => {
  startBackend();

  // Grant microphone access to the renderer (required for both SpeechRecognition and getUserMedia).
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    callback(["media", "audioCapture"].includes(permission));
  });
  session.defaultSession.setPermissionCheckHandler((_webContents, permission) => {
    return (["media", "audioCapture"] as string[]).includes(permission);
  });

  if (!isDev) {
    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          "Content-Security-Policy": [
            "default-src 'self'; connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 ws://localhost:8000 ws://127.0.0.1:8000; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self';",
          ],
        },
      });
    });
  }
  createWindow();
  registerShortcuts();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("will-quit", () => {
  backendProcess?.kill();
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("overlay:set-click-through", (_event, enabled: boolean) => {
  store.set("clickThrough", enabled);
  mainWindow?.setIgnoreMouseEvents(enabled, { forward: true });
  return enabled;
});

ipcMain.handle("overlay:set-invisible", (_event, enabled: boolean) => {
  store.set("invisible", enabled);
  if (enabled) mainWindow?.setOpacity(0.02);
  else mainWindow?.setOpacity(1);
  return enabled;
});

ipcMain.handle("overlay:set-content-protection", (_event, enabled: boolean) => {
  store.set("contentProtection", enabled);
  mainWindow?.setContentProtection(enabled);
  return enabled;
});

ipcMain.handle("overlay:get-content-protection", () => store.get("contentProtection"));

ipcMain.handle("screen:capture", async () => {
  const sources = await desktopCapturer.getSources({
    types: ["screen", "window"],
    thumbnailSize: { width: 1920, height: 1080 },
  });
  const source = sources[0];
  if (!source) return null;
  const image = nativeImage.createFromDataURL(source.thumbnail.toDataURL());
  return image.toPNG().toString("base64");
});
