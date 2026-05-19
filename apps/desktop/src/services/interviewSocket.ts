import type { ClientMessage, ServerMessage } from "../types/shared";

import { BACKEND_TOKEN, WS_URL } from "../config";
import { logger } from "../lib/logger";

type MessageHandler = (message: ServerMessage) => void;

export class InterviewSocket {
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private handlers = new Set<MessageHandler>();
  private pendingMessages: Array<ClientMessage | { type: "ping"; sessionId?: string }> = [];
  private manuallyClosed = false;
  private reconnectAttempt = 0;

  connect(): void {
    if (this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) return;
    this.manuallyClosed = false;
    const url = new URL(WS_URL);
    if (BACKEND_TOKEN) url.searchParams.set("token", BACKEND_TOKEN);
    this.socket = new WebSocket(url.toString());
    this.socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.flushPending();
    };
    this.socket.onmessage = (event) => this.emit(JSON.parse(event.data as string) as ServerMessage);
    this.socket.onclose = () => {
      this.socket = null;
      if (!this.manuallyClosed) this.scheduleReconnect();
    };
    this.socket.onerror = () => {
      logger.warn("websocket error");
    };
  }

  close(): void {
    this.manuallyClosed = true;
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.socket?.close();
  }

  send(message: ClientMessage | { type: "ping"; sessionId?: string }): void {
    if (this.socket?.readyState !== WebSocket.OPEN) {
      this.pendingMessages.push(message);
      this.connect();
      return;
    }
    this.socket.send(JSON.stringify(message));
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  private emit(message: ServerMessage): void {
    for (const handler of this.handlers) handler(message);
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = Math.min(30000, 1200 * 2 ** this.reconnectAttempt);
    this.reconnectAttempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private flushPending(): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    const messages = this.pendingMessages.splice(0);
    for (const message of messages) {
      this.socket.send(JSON.stringify(message));
    }
  }
}

export const interviewSocket = new InterviewSocket();
