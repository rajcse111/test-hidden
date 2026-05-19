export const logger = {
  info: (message: string, meta?: unknown): void => console.info(message, meta ?? ""),
  warn: (message: string, meta?: unknown): void => console.warn(message, meta ?? ""),
  error: (message: string, meta?: unknown): void => console.error(message, meta ?? ""),
};
