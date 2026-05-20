import { BACKEND_TOKEN, BACKEND_URL } from "../config";

export interface ModelInfo {
  provider: string;
  id: string;
  local: boolean;
}

export interface DocumentListResponse {
  total_chunks: number;
  sources: string[];
}

export async function fetchModels(): Promise<ModelInfo[]> {
  const response = await fetch(`${BACKEND_URL}/api/models`, { headers: authHeaders() });
  if (!response.ok) throw new Error(`Failed to load models: ${response.status}`);
  return response.json() as Promise<ModelInfo[]>;
}

export async function runOcr(imageBase64: string): Promise<string> {
  const response = await fetch(`${BACKEND_URL}/api/ocr`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ image_base64: imageBase64 }),
  });
  if (!response.ok) throw new Error(`OCR failed: ${response.status}`);
  const payload = (await response.json()) as { text: string };
  return payload.text;
}

export async function uploadDocument(file: File): Promise<{ chunks_added: number; chunks_skipped: number; total_chunks: number }> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${BACKEND_URL}/api/documents/upload`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (!response.ok) {
    const err = (await response.json().catch(() => ({ detail: response.statusText }))) as { detail: string };
    throw new Error(err.detail ?? `Upload failed: ${response.status}`);
  }
  return response.json() as Promise<{ chunks_added: number; chunks_skipped: number; total_chunks: number }>;
}

export async function listDocuments(): Promise<DocumentListResponse> {
  const response = await fetch(`${BACKEND_URL}/api/documents`, { headers: authHeaders() });
  if (!response.ok) throw new Error(`Failed to list documents: ${response.status}`);
  return response.json() as Promise<DocumentListResponse>;
}

export async function resetDocuments(): Promise<void> {
  const response = await fetch(`${BACKEND_URL}/api/documents/reset`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error(`Reset failed: ${response.status}`);
}

function authHeaders(): Record<string, string> {
  return BACKEND_TOKEN ? { "X-Interview-Token": BACKEND_TOKEN } : {};
}
