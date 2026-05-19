export type AssistantMode = "interview" | "coding" | "system-design";
export type OverlayMode = "passive" | "expanded" | "invisible";
export type Provider = "openai" | "gemini" | "ollama" | "openrouter";

export interface TranscriptSegment {
  id: string;
  sessionId: string;
  speaker: string;
  text: string;
  startedAt: number;
  endedAt: number;
  isPartial: boolean;
}

export interface AssistantDelta {
  sessionId: string;
  content: string;
  done: boolean;
}

export type ClientMessage =
  | { type: "audio.chunk"; sessionId: string; payloadBase64: string; sampleRate: number; channels: number }
  | { type: "transcript.manual"; sessionId: string; text: string }
  | { type: "assistant.cancel"; sessionId: string }
  | { type: "context.screen"; sessionId: string; text: string };

export type ServerMessage =
  | { type: "session.ready"; sessionId: string }
  | { type: "transcript.partial"; segment: TranscriptSegment }
  | { type: "transcript.final"; segment: TranscriptSegment }
  | { type: "assistant.delta"; delta: AssistantDelta }
  | { type: "assistant.error"; sessionId: string; message: string }
  | { type: "pong"; at: string };

