import type { WorkxEvent } from './contracts';
import { ApiRequestError, type Method, type Transport } from './transport';

const BASE = '/api/v1';
let csrfToken = '';

/**
 * Production transport for the FastAPI control plane (docs/architecture/11-DATA-API-EVENTS.md).
 * Session is an HttpOnly cookie; state-changing requests carry X-WorkX-CSRF.
 * The backend does not exist yet, so every call currently fails with a network or 404 error, which the
 * UI shows through its error states. See apps/web/docs/BACKEND-INTEGRATION.md for the endpoint list.
 */
export class HttpTransport implements Transport {
  runtime = { mode: 'http', simulated: false } as const;

  async request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET' && csrfToken) headers['X-WorkX-CSRF'] = csrfToken;
    if (method === 'POST') headers['Idempotency-Key'] = crypto.randomUUID();
    const response = await fetch(BASE + path, {
      method,
      headers,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 401) {
      window.location.assign('/login');
      throw new ApiRequestError(401, 'UNAUTHENTICATED', 'Sign in again');
    }
    const text = await response.text();
    const json = text ? JSON.parse(text) : null;
    if (!response.ok) throw new ApiRequestError(response.status, json?.code || 'INTERNAL', json?.detail || json?.message || response.statusText);
    if (path === '/me' && json?.csrf_token) csrfToken = json.csrf_token;
    return json as T;
  }

  subscribe(tenantId: string, onEvent: (event: WorkxEvent) => void) {
    const source = new EventSource(`${BASE}/tenants/${encodeURIComponent(tenantId)}/events`, { withCredentials: true });
    source.onmessage = message => {
      try { onEvent(JSON.parse(message.data)); } catch { /* ignore malformed frames */ }
    };
    return () => source.close();
  }
}
