import { AnimatePresence, motion } from "framer-motion";
import {
  AudioLines,
  Bot,
  EyeOff,
  Keyboard,
  Mic,
  MicOff,
  MousePointer2,
  ScanText,
  Settings,
  Square,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";

import { audioCapture } from "../services/audioCapture";
import { listDocuments, resetDocuments, runOcr, updateSetting, uploadDocument } from "../services/backend";
import { interviewSocket } from "../services/interviewSocket";
import { liveSpeech } from "../services/liveSpeech";
import { useAssistantStore } from "../state/assistantStore";
import type { Citation } from "../types/shared";

const tabs = [
  ["audio", "Audio Input"],
  ["transcript", "Transcript"],
  ["answers", "Answers"],
  ["analysis", "Analysis"],
  ["notes", "Notes"],
  ["settings", "Settings"],
] as const;

export function App(): JSX.Element {
  const store = useAssistantStore();
  const setConnection = useAssistantStore((state) => state.setConnection);
  const setSessionId = useAssistantStore((state) => state.setSessionId);
  const addTranscript = useAssistantStore((state) => state.addTranscript);
  const appendAnswer = useAssistantStore((state) => state.appendAnswer);
  const appendAudioInputText = useAssistantStore((state) => state.appendAudioInputText);
  const setListening = useAssistantStore((state) => state.setListening);
  const setInterimAudioText = useAssistantStore((state) => state.setInterimAudioText);
  const setBackendInterimText = useAssistantStore((state) => state.setBackendInterimText);
  const setCitations = useAssistantStore((state) => state.setCitations);
  const sessionId = useAssistantStore((state) => state.sessionId);
  const listening = useAssistantStore((state) => state.listening);
  const [manualText, setManualText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const generationRef = useRef(0);

  useEffect(() => {
    if (import.meta.env.MODE === "test") return undefined;
    setConnection("connecting");
    const unsubscribe = interviewSocket.onMessage((message) => {
      if (message.type === "session.ready") {
        setSessionId(message.sessionId);
        setConnection("connected");
      }
      if (message.type === "transcript.final") {
        addTranscript(message.segment);
        if (message.segment.text?.trim() && useAssistantStore.getState().listening) {
          appendAudioInputText(message.segment.text);
          setBackendInterimText("");
        }
      }
      if (message.type === "transcript.partial") {
        if (useAssistantStore.getState().listening && message.segment.text?.trim()) {
          setBackendInterimText(message.segment.text);
        }
      }
      if (message.type === "assistant.citations") {
        if (useAssistantStore.getState()._generation === generationRef.current) {
          setCitations(message.citations);
        }
      }
      if (message.type === "assistant.delta") {
        if (useAssistantStore.getState()._generation === generationRef.current) {
          appendAnswer(message.delta.content, message.delta.done);
        }
      }
      if (message.type === "assistant.error") setError(message.message);
      if (message.type === "assistant.question_detected") {
        useAssistantStore.getState().resetAnswer();
        generationRef.current = useAssistantStore.getState()._generation;
        useAssistantStore.getState().setActiveTab("answers");
      }
    });
    interviewSocket.connect();
    return () => unsubscribe();
  }, [addTranscript, appendAudioInputText, appendAnswer, setCitations, setBackendInterimText, setConnection, setSessionId]);

  const startNewRequest = useCallback((sid: string, prompt: string) => {
    interviewSocket.send({ type: "assistant.cancel", sessionId: sid });
    useAssistantStore.getState().resetAnswer();
    generationRef.current = useAssistantStore.getState()._generation;
    useAssistantStore.getState().setActiveTab("answers");
    interviewSocket.send({ type: "transcript.manual", sessionId: sid, text: prompt });
  }, []);

  const toggleListening = useCallback(async () => {
    if (!sessionId) return;
    if (listening) {
      audioCapture.stop();
      liveSpeech.stop();
      const latest = useAssistantStore.getState();
      const capturedText = latest.audioInputText.trim();
      const interimLine = latest.interimAudioText.trim();
      const prompt = [capturedText, interimLine].filter(Boolean).join("\n");

      setListening(false);
      latest.resetAudioInput();
      if (prompt) {
        startNewRequest(sessionId, prompt);
      }
      return;
    }
    setError(null);
    store.setActiveTab("audio");
    if (liveSpeech.isSupported()) {
      liveSpeech.start(setInterimAudioText, appendAudioInputText);
    }
    await audioCapture.start(sessionId, { streamToBackend: true });
    setListening(true);
  }, [listening, sessionId, setInterimAudioText, setListening, appendAudioInputText, startNewRequest]);

  const captureScreen = useCallback(async () => {
    if (!store.sessionId) return;
    const imageBase64 = await window.interview?.captureScreen();
    if (!imageBase64) return;
    const text = await runOcr(imageBase64);
    interviewSocket.send({ type: "context.screen", sessionId: store.sessionId, text });
  }, [store.sessionId]);

  useEffect(() => window.interview?.onToggleListening(() => void toggleListening()), [toggleListening]);
  useEffect(() => window.interview?.onCaptureScreen(() => void captureScreen()), [captureScreen]);

  const status = useMemo(() => {
    if (store.connection === "connected") return "Connected";
    if (store.connection === "connecting") return "Connecting";
    return "Offline";
  }, [store.connection]);

  const submitManual = (): void => {
    if (!store.sessionId || !manualText.trim()) return;
    startNewRequest(store.sessionId, manualText.trim());
    setManualText("");
  };

  const setClickThrough = async (): Promise<void> => {
    const next = !store.clickThrough;
    await window.interview?.setClickThrough(next);
    store.setClickThrough(next);
  };

  const setInvisible = async (): Promise<void> => {
    const next = store.overlayMode !== "invisible";
    await window.interview?.setInvisible(next);
    store.setOverlayMode(next ? "invisible" : "expanded");
  };

  return (
    <main className="h-full w-full bg-transparent p-4 text-slate-100">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex h-full flex-col overflow-hidden rounded-lg border border-white/10 bg-surface/90 shadow-overlay backdrop-blur-xl"
      >
        <header className="drag-region flex items-center justify-between border-b border-white/10 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent/15 text-accent">
              <Bot size={20} />
            </div>
            <div>
              <h1 className="text-sm font-semibold tracking-normal">AI Answer Assistant</h1>
              <div className="flex items-center gap-2 text-xs text-slate-400">
                {store.connection === "connected" ? <Wifi size={13} /> : <WifiOff size={13} />}
                <span>{status}</span>
                <span className="h-1 w-1 rounded-full bg-slate-600" />
                <span>{store.listening ? "Listening" : "Idle"}</span>
              </div>
            </div>
          </div>
          <div className="no-drag flex items-center gap-2">
            <IconButton title={store.listening ? "Stop listening" : "Start listening"} onClick={() => void toggleListening()}>
              {store.listening ? <MicOff size={17} /> : <Mic size={17} />}
            </IconButton>
            <IconButton title="Capture screen context" onClick={() => void captureScreen()}>
              <ScanText size={17} />
            </IconButton>
            <IconButton title="Click-through overlay" active={store.clickThrough} onClick={() => void setClickThrough()}>
              <MousePointer2 size={17} />
            </IconButton>
            <IconButton title="Invisible mode" onClick={() => void setInvisible()}>
              <EyeOff size={17} />
            </IconButton>
          </div>
        </header>

        <nav className="no-drag flex gap-1 border-b border-white/10 px-3 py-2">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              onClick={() => store.setActiveTab(key)}
              className={`rounded-md px-3 py-1.5 text-xs transition ${
                store.activeTab === key ? "bg-white/12 text-white" : "text-slate-400 hover:bg-white/8 hover:text-slate-100"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        {error ? <div className="mx-4 mt-3 rounded-md border border-red-400/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">{error}</div> : null}

        <section className="no-drag min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <AnimatePresence mode="wait">
            {store.activeTab === "audio" && <AudioInputPanel />}
            {store.activeTab === "transcript" && <TranscriptPanel />}
            {store.activeTab === "answers" && <AnswerPanel answer={store.answer} citations={store.citations} />}
            {store.activeTab === "analysis" && <AnalysisPanel />}
            {store.activeTab === "notes" && <NotesPanel />}
            {store.activeTab === "settings" && <SettingsPanel />}
          </AnimatePresence>
        </section>

        <footer className="no-drag border-t border-white/10 p-3">
          <div className="flex gap-2">
            <input
              value={manualText}
              onChange={(event) => setManualText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submitManual();
              }}
              placeholder="Paste or type an interview question..."
              className="min-w-0 flex-1 rounded-md border border-white/10 bg-black/20 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-accent"
            />
            <button
              onClick={submitManual}
              disabled={store.connection !== "connected"}
              title={store.connection !== "connected" ? "Backend offline — waiting for connection" : undefined}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                store.connection === "connected"
                  ? "bg-accent text-slate-950"
                  : "cursor-not-allowed bg-white/10 text-slate-500"
              }`}
            >
              Send
            </button>
          </div>
        </footer>
      </motion.section>
    </main>
  );
}

function AudioInputPanel(): JSX.Element {
  const audioInputText = useAssistantStore((state) => state.audioInputText);
  const setAudioInputText = useAssistantStore((state) => state.setAudioInputText);
  const interimAudioText = useAssistantStore((state) => state.interimAudioText);
  const backendInterimText = useAssistantStore((state) => state.backendInterimText);
  const listening = useAssistantStore((state) => state.listening);

  return (
    <Panel>
      <div className="flex min-h-[360px] flex-col rounded-md border border-white/10 bg-black/20">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <AudioLines size={17} className={listening ? "text-accent" : "text-slate-500"} />
            Audio Input
          </div>
          <div className="flex items-center gap-2">
            {audioInputText ? (
              <button
                onClick={() => setAudioInputText("")}
                title="Clear"
                className="text-slate-500 transition hover:text-slate-300"
              >
                <X size={14} />
              </button>
            ) : null}
            <div className={`rounded-md px-2 py-1 text-xs ${listening ? "bg-accent/15 text-accent" : "bg-white/5 text-slate-400"}`}>
              {listening ? "Listening" : "Idle"}
            </div>
          </div>
        </div>
        <div className="flex-1 p-4">
          {audioInputText || interimAudioText || backendInterimText ? (
            <div className="flex h-full min-h-[300px] flex-col gap-3">
              <textarea
                value={audioInputText}
                onChange={(event) => setAudioInputText(event.target.value)}
                placeholder="Spoken text will appear here. You can edit it before stopping."
                className="min-h-[260px] flex-1 resize-none rounded-md border border-transparent bg-transparent text-base leading-8 text-slate-100 outline-none placeholder:text-slate-600 focus:border-accent/40 focus:bg-black/10"
              />
              {interimAudioText ? (
                <p className="rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm leading-6 text-slate-400">
                  {interimAudioText}
                </p>
              ) : null}
              {backendInterimText && !interimAudioText ? (
                <p className="rounded-md border border-accent/20 bg-accent/5 px-3 py-2 text-sm leading-6 italic text-slate-500">
                  {backendInterimText}
                </p>
              ) : null}
            </div>
          ) : (
            <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 text-slate-500">
              <div className="flex h-11 w-11 items-center justify-center rounded-md border border-white/10 bg-white/5">
                <Mic size={20} />
              </div>
              <p className="text-sm">{listening ? "Listening for speech..." : "Start listening to see spoken text here"}</p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

function IconButton(props: { title: string; active?: boolean; onClick: () => void; children: React.ReactNode }): JSX.Element {
  return (
    <button
      title={props.title}
      onClick={props.onClick}
      className={`flex h-9 w-9 items-center justify-center rounded-md border border-white/10 transition ${
        props.active ? "bg-accent text-slate-950" : "bg-white/5 text-slate-200 hover:bg-white/12"
      }`}
    >
      {props.children}
    </button>
  );
}

function TranscriptPanel(): JSX.Element {
  const transcript = useAssistantStore((state) => state.transcript);
  return (
    <Panel>
      <div className="space-y-3">
        {transcript.length === 0 ? <EmptyState icon={<Mic size={20} />} title="Waiting for transcript" /> : null}
        {transcript.map((segment) => (
          <article key={segment.id} className="rounded-md border border-white/10 bg-white/5 p-3">
            <div className="mb-1 text-xs uppercase text-slate-500">{segment.speaker}</div>
            <p className="text-sm leading-6 text-slate-100">{segment.text}</p>
          </article>
        ))}
      </div>
    </Panel>
  );
}

function AnswerPanel({ answer, citations }: { answer: string; citations: Citation[] }): JSX.Element {
  const [showSources, setShowSources] = useState(false);
  return (
    <Panel>
      {answer ? (
        <div className="flex flex-col gap-3">
          <div className="prose prose-invert prose-sm max-w-none prose-pre:bg-black/40">
            <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{answer}</ReactMarkdown>
          </div>
          {citations.length > 0 && (
            <div className="rounded-md border border-white/10 bg-white/5">
              <button
                onClick={() => setShowSources((s) => !s)}
                className="flex w-full items-center justify-between px-3 py-2 text-xs text-slate-400 hover:text-slate-200"
              >
                <span>📎 Sources ({citations.length})</span>
                <span>{showSources ? "▲" : "▼"}</span>
              </button>
              {showSources && (
                <div className="divide-y divide-white/5 px-3 pb-3">
                  {citations.map((c, i) => (
                    <div key={i} className="py-2 text-xs">
                      <div className="font-semibold text-slate-300">
                        {c.source} — page {c.page}{" "}
                        <span className="font-normal text-slate-500">(dist: {c.distance})</span>
                      </div>
                      <div className="mt-1 text-slate-400 leading-5">{c.snippet}…</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <EmptyState icon={<Bot size={20} />} title="AI answer stream will appear here" />
      )}
    </Panel>
  );
}

function AnalysisPanel(): JSX.Element {
  const transcript = useAssistantStore((state) => state.transcript);
  const latest = transcript.at(-1)?.text;
  return (
    <Panel>
      {latest ? (
        <div className="grid gap-3 text-sm text-slate-200">
          <InfoRow label="Latest prompt" value={latest} />
          <InfoRow label="Response style" value="Concise, interview-ready, STAR when useful" />
          <InfoRow label="Context window" value={`${transcript.length} transcript segment(s)`} />
        </div>
      ) : (
        <EmptyState icon={<Square size={20} />} title="No analysis yet" />
      )}
    </Panel>
  );
}

function NotesPanel(): JSX.Element {
  const notes = useAssistantStore((state) => state.notes);
  const setNotes = useAssistantStore((state) => state.setNotes);
  return (
    <textarea
      value={notes}
      onChange={(event) => setNotes(event.target.value)}
      className="h-full min-h-[360px] w-full resize-none rounded-md border border-white/10 bg-black/20 p-3 text-sm leading-6 outline-none focus:border-accent"
      placeholder="Private notes..."
    />
  );
}

const MODES = ["interview", "coding", "system-design", "senior-fullstack"] as const;
type AssistantMode = (typeof MODES)[number];

function SettingsPanel(): JSX.Element {
  const [currentMode, setCurrentMode] = useState<AssistantMode>("interview");
  const [docInfo, setDocInfo] = useState<{ total_chunks: number; sources: string[] } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [docSuccess, setDocSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshDocs = useCallback(async () => {
    try {
      const info = await listDocuments();
      setDocInfo(info);
    } catch {
      setDocInfo(null);
    }
  }, []);

  useEffect(() => { void refreshDocs(); }, [refreshDocs]);

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setDocError(null);
    setDocSuccess(null);
    try {
      const result = await uploadDocument(file);
      setDocSuccess(`${file.name}: +${result.chunks_added} chunk(s) added, ${result.chunks_skipped} already present.`);
      await refreshDocs();
    } catch (err) {
      setDocError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleReset = async (): Promise<void> => {
    if (!confirm("Delete all indexed documents? This cannot be undone.")) return;
    try {
      await resetDocuments();
      setDocSuccess("Vector store cleared.");
      await refreshDocs();
    } catch (err) {
      setDocError(err instanceof Error ? err.message : "Reset failed");
    }
  };

  const handleModeChange = async (mode: AssistantMode): Promise<void> => {
    await updateSetting("mode", mode);
    setCurrentMode(mode);
    interviewSocket.close();
    interviewSocket.connect();
  };

  return (
    <Panel>
      <div className="space-y-4">
        {/* Mode Selector */}
        <div className="rounded-md border border-white/10 bg-white/5 p-3">
          <div className="mb-2 text-xs font-semibold text-slate-100">Assistant Mode</div>
          <select
            value={currentMode}
            onChange={(e) => void handleModeChange(e.target.value as AssistantMode)}
            className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent"
          >
            {MODES.map((m) => (
              <option key={m} value={m} className="bg-slate-900">
                {m}
              </option>
            ))}
          </select>
          <p className="mt-1.5 text-xs text-slate-500">Takes effect on reconnect.</p>
        </div>
        {/* Document Upload */}
        <div className="rounded-md border border-white/10 bg-white/5 p-3">
          <div className="mb-3 text-xs font-semibold text-slate-100">📚 RAG Documents</div>
          {docInfo ? (
            <div className="mb-3 text-xs text-slate-400">
              <span className="text-slate-200">{docInfo.total_chunks}</span> chunks indexed
              {docInfo.sources.length > 0 && (
                <div className="mt-1 space-y-0.5">
                  {docInfo.sources.map((src) => (
                    <div key={src} className="text-slate-500">• {src}</div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="mb-3 text-xs text-slate-500">RAG not available or no documents yet.</div>
          )}
          {docError && <div className="mb-2 rounded bg-red-500/15 px-2 py-1 text-xs text-red-300">{docError}</div>}
          {docSuccess && <div className="mb-2 rounded bg-green-500/15 px-2 py-1 text-xs text-green-300">{docSuccess}</div>}
          <div className="flex gap-2">
            <label className="flex-1 cursor-pointer rounded-md border border-white/10 bg-black/20 px-3 py-2 text-center text-xs text-slate-300 hover:bg-white/5">
              {uploading ? "Uploading…" : "Upload PDF / DOCX / XLSX"}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.xlsx"
                className="hidden"
                onChange={(e) => void handleFileChange(e)}
                disabled={uploading}
              />
            </label>
            {docInfo && docInfo.total_chunks > 0 && (
              <button
                onClick={() => void handleReset()}
                className="rounded-md border border-red-400/20 bg-red-500/10 px-3 py-2 text-xs text-red-300 hover:bg-red-500/20"
              >
                Reset
              </button>
            )}
          </div>
        </div>

        <InfoRow label="Backend" value={import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8000"} />
        <InfoRow label="WebSocket" value={import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws/interview"} />
        <div className="rounded-md border border-white/10 bg-white/5 p-3 text-xs text-slate-300">
          <div className="mb-2 flex items-center gap-2 font-semibold text-slate-100">
            <Keyboard size={15} />
            Shortcuts
          </div>
          <p>Ctrl/Cmd+Shift+Space toggles overlay visibility.</p>
          <p>Ctrl/Cmd+Shift+L toggles listening.</p>
          <p>Ctrl/Cmd+Shift+S captures screen context.</p>
          <p>Ctrl/Cmd+Shift+X toggles click-through.</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Settings size={14} />
          API keys stay in backend environment variables.
        </div>
      </div>
    </Panel>
  );
}

function Panel({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <motion.div
      key="panel"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="min-h-full"
    >
      {children}
    </motion.div>
  );
}

function EmptyState({ icon, title }: { icon: React.ReactNode; title: string }): JSX.Element {
  return (
    <div className="flex min-h-[300px] flex-col items-center justify-center gap-3 text-slate-500">
      <div className="flex h-11 w-11 items-center justify-center rounded-md border border-white/10 bg-white/5">{icon}</div>
      <p className="text-sm">{title}</p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="rounded-md border border-white/10 bg-white/5 p-3">
      <div className="text-xs uppercase text-slate-500">{label}</div>
      <div className="mt-1 break-words text-slate-100">{value}</div>
    </div>
  );
}
