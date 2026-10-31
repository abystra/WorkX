import { TENANT_EVENT_TYPES, type WorkxEvent } from './contracts';
import { ApiRequestError, type Method, type Transport } from './transport';

const BASE = '/api/v1';
let csrfToken = '';
let hadSession = false;

/** Public routes handle their own 401s; everywhere else a 401 leaves the app for a sign-in screen. */
const PUBLIC_PATHS = ['/login', '/signup', '/invite/', '/session-expired'];

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
    const text = await response.text();
    const json = text ? JSON.parse(text) : null;
    if (response.status === 401) {
      const code = json?.code || 'UNAUTHENTICATED';
      const here = window.location.pathname + window.location.search;
      if (!PUBLIC_PATHS.some(p => window.location.pathname.startsWith(p))) {
        // A session that worked earlier (or was revoked) gets the session-expired screen; a first visit goes to sign-in.
        const screen = hadSession || code === 'SESSION_REVOKED' ? '/session-expired' : '/login';
        window.location.assign(`${screen}?return_to=${encodeURIComponent(here)}`);
      }
      throw new ApiRequestError(401, code, json?.detail || 'Sign in again');
    }
    if (!response.ok) throw new ApiRequestError(response.status, json?.code || 'INTERNAL', json?.detail || json?.message || response.statusText);
    if (path === '/me') hadSession = true;
    if (path === '/me' && json?.csrf_token) csrfToken = json.csrf_token;
    return json as T;
  }

  /**
   * Tenant event stream. The architecture names SSE frames (`event: task.succeeded`), and EventSource only
   * calls onmessage for unnamed frames, so each type the UI reacts to gets its own listener.
   * The tenant-level stream itself is a proposed contract addition (docs/BACKEND-INTEGRATION.md §3).
   */
  subscribe(tenantId: string, onEvent: (event: WorkxEvent) => void) {
    const source = new EventSource(`${BASE}/tenants/${encodeURIComponent(tenantId)}/events`, { withCredentials: true });
    const handle = (message: MessageEvent) => {
      try { onEvent(JSON.parse(message.data)); } catch { /* ignore malformed frames */ }
    };
    source.onmessage = handle;
    for (const type of TENANT_EVENT_TYPES) source.addEventListener(type, handle as EventListener);
    return () => source.close();
  }

}
