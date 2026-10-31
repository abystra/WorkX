import type { RuntimeInfo, WorkxEvent } from './contracts';

export type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

export class ApiRequestError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

/**
 * Everything the app needs from a backend. Two implementations exist:
 * - HttpTransport: FastAPI control plane over `/api/v1` with cookie session and SSE.
 * - DevBackend (src/dev-backend): in-browser development adapter. Never bundled in production builds.
 */
export interface Transport {
  runtime: RuntimeInfo;
  request<T>(method: Method, path: string, body?: unknown): Promise<T>;
  /** Tenant activity stream; returns an unsubscribe function. */
  subscribe(tenantId: string, onEvent: (event: WorkxEvent) => void): () => void;
}
