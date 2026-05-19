import { BACKEND_TOKEN, BACKEND_URL } from "../config";

export interface ModelInfo {
  provider: string;
  id: string;
  local: boolean;
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

function authHeaders(): Record<string, string> {
  return BACKEND_TOKEN ? { "X-Interview-Token": BACKEND_TOKEN } : {};
}
