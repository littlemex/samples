export interface SSEMessage {
  count?: number;
  timestamp?: string;
  message?: string;
}

export const CONFIG = {
  PORT: 3001,
  HOST: 'localhost',
  ENDPOINT: '/sse',
  INTERVAL_MS: 1000
};
