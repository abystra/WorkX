import { TENANT_EVENT_TYPES, type WorkxEvent } from './contracts';
import { plan } from './http-mapping';
import { ApiRequestError, type Method, type Transport } from './transport';

const BASE = '/api/v1';
let csrfToken = '';
let hadSession = false;

/** Public routes handle their own 401s; everywhere else a 401 leaves the app for a sign-in screen. */
const PUBLIC_PATHS = ['/login', '/signup', '/invite/', '/session-expired'];

/**
 * Production transport for the control plane (docs/architecture/11-DATA-API-EVENTS.md).
 * Session is an HttpOnly cookie; state-changing requests carry X-WorkX-CSRF; every POST carries a fresh
 * Idempotency-Key (one per user action: the client never retries automatically).
 * View-model calls are translated to API routes and shapes in http-mapping.ts.
 */
export class HttpTransport implements Transport {
  runtime = { mode: 'http', simulated: false } as const;

  async request<T>(uiMethod: Method, uiPath: string, uiBody?: unknown): Promise<T> {
    const call = plan(uiMethod, uiPath, uiBody);
    if (call.local instanceof Error) throw new ApiRequestError(501, call.local.message, 'Not available yet');
    if (call.local !== undefined) return call.local as T;
    const { method, path, body } = call;
    // Public pages (e.g. /invite/:token) can POST before anything loaded /me, which carries the CSRF token.
    if (method !== 'GET' && !csrfToken) await this.loadCsrfToken();
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
    if (response.status === 403 && json?.code === 'TENANT_REAUTH_REQUIRED') {
      // Organization SSO policy: sign in again through the organization's identity provider, then come back.
      const url = String(json?.data?.login_url || '');
      if (url.startsWith('/api/v1/auth/login?')) window.location.assign(url);
      throw new ApiRequestError(403, 'TENANT_REAUTH_REQUIRED', json?.detail || 'Sign in again');
    }
    if (response.status === 403 && call.forbiddenAs !== undefined) return call.forbiddenAs as T;
    if (!response.ok) throw new ApiRequestError(response.status, json?.code || 'INTERNAL', json?.detail || json?.message || response.statusText);
    if (path === '/me') hadSession = true;
    if (path === '/me' && json?.csrf_token) csrfToken = json.csrf_token;
    return call.out(json) as T;
  }

  private async loadCsrfToken() {
    const response = await fetch(`${BASE}/me`, { credentials: 'include', headers: { Accept: 'application/json' } });
    if (response.ok) {
      hadSession = true;
      csrfToken = (await response.json()).csrf_token || '';
    }
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
