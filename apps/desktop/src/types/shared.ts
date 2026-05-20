// Local type definitions that previously came from the @interview/shared
// workspace package. Defined here so the app builds without the monorepo.

export type OverlayMode = "expanded" | "compact" | "invisible";

export interface TranscriptSegment {
  id: string;
  speaker: "interviewer" | "candidate" | "system";
  text: string;
  isPartial: boolean;
  timestamp?: number;
}

// ---- Outbound (renderer → backend) ------------------------------------------

export interface AudioChunkMessage {
  type: "audio.chunk";
  sessionId: string;
  payloadBase64: string;
  sampleRate: number;
  channels: number;
}

export interface TranscriptManualMessage {
  type: "transcript.manual";
  sessionId: string;
  text: string;
}

export interface AssistantCancelMessage {
  type: "assistant.cancel";
  sessionId: string;
}

export interface ContextScreenMessage {
  type: "context.screen";
  sessionId: string;
  text: string;
}

export type ClientMessage =
  | AudioChunkMessage
  | TranscriptManualMessage
  | AssistantCancelMessage
  | ContextScreenMessage;

// ---- Inbound (backend → renderer) -------------------------------------------

export interface SessionReadyMessage {
  type: "session.ready";
  sessionId: string;
}

export interface TranscriptMessage {
  type: "transcript.final" | "transcript.partial";
  segment: TranscriptSegment;
}

export interface AssistantDeltaMessage {
  type: "assistant.delta";
  delta: { content: string; done: boolean };
}

export interface AssistantErrorMessage {
  type: "assistant.error";
  message: string;
}

export interface Citation {
  source: string;
  page: string;
  snippet: string;
  distance: number;
}

export interface AssistantCitationsMessage {
  type: "assistant.citations";
  sessionId: string;
  citations: Citation[];
}

export type ServerMessage =
  | SessionReadyMessage
  | TranscriptMessage
  | AssistantDeltaMessage
  | AssistantErrorMessage
  | AssistantCitationsMessage;
