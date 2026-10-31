import { beforeEach, describe, expect, it } from 'vitest';
import { authLoginUrl, safeReturnTo } from '@/api/client';
import { ApiRequestError } from '@/api/transport';
import { DevBackend } from '@/dev-backend/backend';

describe('account screens', () => {
  it('only accepts same-origin relative return paths', () => {
    expect(safeReturnTo('/t/wx-demo/home')).toBe('/t/wx-demo/home');
    expect(safeReturnTo('/invite/abc?x=1')).toBe('/invite/abc?x=1');
    for (const unsafe of ['//evil.example', 'https://evil.example', '/\\evil.example', 'javascript:alert(1)', '', null, undefined]) expect(safeReturnTo(unsafe)).toBe('/');
  });

  it('hands sign-in to the API with an encoded, sanitized return path', () => {
    expect(authLoginUrl('signup', '/t/a b/home')).toBe('/api/v1/auth/login?intent=signup&return_to=%2Ft%2Fa%20b%2Fhome');
    expect(authLoginUrl('login', '//evil.example')).toBe('/api/v1/auth/login?intent=login&return_to=%2F');
  });
});

describe('development adapter: POST /invitations/accept', () => {
  let backend: DevBackend;
  beforeEach(() => { localStorage.clear(); backend = new DevBackend(); });

  const code = async (work: Promise<unknown>) => work.then(() => 'ok', (e: ApiRequestError) => e.code);

  it('accepts a pending invitation once and returns its tenant', async () => {
    const [invitation] = await backend.request<{ id: string }[]>('POST', '/tenants/wx-demo/invitations', { emails: 'new.person@example.com', role: 'member' });
    await expect(backend.request('POST', '/invitations/accept', { token: invitation.id })).resolves.toEqual({ tenant_id: 'wx-demo' });
    expect(await code(backend.request('POST', '/invitations/accept', { token: invitation.id }))).toBe('INVITATION_CLOSED');
  });

  it('rejects unknown tokens', async () => {
    expect(await code(backend.request('POST', '/invitations/accept', { token: 'nope' }))).toBe('INVITATION_NOT_FOUND');
  });
});
