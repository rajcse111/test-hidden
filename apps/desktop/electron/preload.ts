import { contextBridge, ipcRenderer } from "electron";

const api = {
  setClickThrough: (enabled: boolean): Promise<boolean> => ipcRenderer.invoke("overlay:set-click-through", enabled),
  setInvisible: (enabled: boolean): Promise<boolean> => ipcRenderer.invoke("overlay:set-invisible", enabled),
  setContentProtection: (enabled: boolean): Promise<boolean> =>
    ipcRenderer.invoke("overlay:set-content-protection", enabled),
  getContentProtection: (): Promise<boolean> => ipcRenderer.invoke("overlay:get-content-protection"),
  captureScreen: (): Promise<string | null> => ipcRenderer.invoke("screen:capture"),
  onToggleListening: (callback: () => void): (() => void) => {
    const listener = (): void => callback();
    ipcRenderer.on("shortcut:listening", listener);
    return () => ipcRenderer.off("shortcut:listening", listener);
  },
  onCaptureScreen: (callback: () => void): (() => void) => {
    const listener = (): void => callback();
    ipcRenderer.on("shortcut:screenshot", listener);
    return () => ipcRenderer.off("shortcut:screenshot", listener);
  },
  onContentProtectionChange: (callback: (enabled: boolean) => void): (() => void) => {
    const listener = (_event: unknown, enabled: boolean): void => callback(enabled);
    ipcRenderer.on("overlay:content-protection", listener);
    return () => ipcRenderer.off("overlay:content-protection", listener);
  },
};

contextBridge.exposeInMainWorld("interview", api);

export type InterviewApi = typeof api;

