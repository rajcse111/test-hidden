import type { OverlayMode, TranscriptSegment } from "../types/shared";
import { create } from "zustand";

type ConnectionState = "disconnected" | "connecting" | "connected";

interface AssistantState {
  sessionId: string | null;
  connection: ConnectionState;
  listening: boolean;
  overlayMode: OverlayMode;
  clickThrough: boolean;
  activeTab: "audio" | "transcript" | "analysis" | "answers" | "notes" | "settings";
  transcript: TranscriptSegment[];
  audioInputText: string;
  interimAudioText: string;
  answer: string;
  notes: string;
  _generation: number;
  setSessionId: (sessionId: string) => void;
  setConnection: (connection: ConnectionState) => void;
  setListening: (listening: boolean) => void;
  setOverlayMode: (overlayMode: OverlayMode) => void;
  setClickThrough: (clickThrough: boolean) => void;
  setActiveTab: (activeTab: AssistantState["activeTab"]) => void;
  addTranscript: (segment: TranscriptSegment) => void;
  appendAudioInputText: (text: string) => void;
  setAudioInputText: (text: string) => void;
  setInterimAudioText: (text: string) => void;
  clearInterimAudioText: () => void;
  resetAudioInput: () => void;
  appendAnswer: (content: string, done: boolean) => void;
  setNotes: (notes: string) => void;
  resetAnswer: () => void;
}

export const useAssistantStore = create<AssistantState>((set) => ({
  sessionId: null,
  connection: "disconnected",
  listening: false,
  overlayMode: "expanded",
  clickThrough: false,
  activeTab: "audio",
  transcript: [],
  audioInputText: "",
  interimAudioText: "",
  answer: "",
  notes: "",
  _generation: 0,
  setSessionId: (sessionId) => set({ sessionId }),
  setConnection: (connection) => set({ connection }),
  setListening: (listening) => set({ listening }),
  setOverlayMode: (overlayMode) => set({ overlayMode }),
  setClickThrough: (clickThrough) => set({ clickThrough }),
  setActiveTab: (activeTab) => set({ activeTab }),
  addTranscript: (segment) =>
    set((state) => ({
      transcript: [...state.transcript.filter((item) => item.id !== segment.id), segment].slice(-100),
      interimAudioText: segment.isPartial ? state.interimAudioText : "",
    })),
  appendAudioInputText: (text) =>
    set((state) => ({
      audioInputText: [state.audioInputText.trim(), text.trim()].filter(Boolean).join("\n"),
    })),
  setAudioInputText: (text) => set({ audioInputText: text }),
  setInterimAudioText: (text) => set({ interimAudioText: text }),
  clearInterimAudioText: () => set({ interimAudioText: "" }),
  resetAudioInput: () => set({ audioInputText: "", interimAudioText: "", transcript: [] }),
  appendAnswer: (content, done) =>
    set((state) => ({
      answer: done ? state.answer : `${state.answer}${content}`,
    })),
  setNotes: (notes) => set({ notes }),
  resetAnswer: () => set((state) => ({ answer: "", _generation: state._generation + 1 })),
}));
