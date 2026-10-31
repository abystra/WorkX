import { beforeEach, describe, expect, it } from 'vitest';
import { DevBackend } from './backend';
import { freshSeed } from './store';
import { canManageSpace, inviteMembers, transitionInvitation, updateResourceSharing } from './rules';
import { ApiRequestError } from '@/api/transport';

describe('development adapter rules (ported from prototype spaces-model.js)', () => {
  let backend: DevBackend;
  beforeEach(() => { localStorage.clear(); backend = new DevBackend(); });

  it('seeds a personal and an organization workspace', async () => {
    const tenants = await backend.request<{ id: string; type: string }[]>('GET', '/me/tenants');
    expect(tenants.map(t => t.type).sort()).toEqual(['organization', 'personal']);
  });

  it('rejects invalid and duplicate invitations, accepts once', () => {
    const data = freshSeed().spaces.find(s => s.type === 'organization')!.data;
    expect(inviteMembers(data, { emails: 'not-an-email', role: 'member' })).toEqual({ error: 'spaces.invalidEmail' });
    const ok = inviteMembers(data, { emails: 'a@example.com', role: 'member' }) as { invitations: { id: string }[] };
    expect(ok.invitations).toHaveLength(1);
    expect(inviteMembers(data, { emails: 'a@example.com', role: 'member' })).toEqual({ error: 'spaces.duplicateInvitation' });
    expect(transitionInvitation(data, ok.invitations[0].id, 'accept')).toHaveProperty('member');
    expect(transitionInvitation(data, ok.invitations[0].id, 'accept')).toEqual({ error: 'spaces.invitationClosed' });
  });

  it('expires invitations after 7 days', () => {
    const data = freshSeed().spaces.find(s => s.type === 'organization')!.data;
    const now = Date.now();
    const { invitations } = inviteMembers(data, { emails: 'b@example.com', role: 'admin' }, now) as { invitations: { id: string }[] };
    expect(transitionInvitation(data, invitations[0].id, 'accept', now + 7 * 86400000 + 1)).toEqual({ error: 'spaces.invitationClosed' });
  });

  it('personal workspaces cannot be managed as organizations and stay private', () => {
    const personal = freshSeed().spaces.find(s => s.type === 'personal')!.data;
    expect(canManageSpace(personal)).toBeFalsy();
    personal.agents[0].resourceOwnerId = 'm1';
    const result = updateResourceSharing(personal, 'agents', personal.agents[0].id, { visibility: 'space' }) as { resource: { visibility: string } };
    expect(result.resource.visibility).toBe('private');
  });

  it('rejects duplicate organization names with the prototype error key', async () => {
    await expect(backend.request('POST', '/tenants', { name: 'workx' })).rejects.toMatchObject({ code: 'spaces.duplicateName' });
    const created = await backend.request<{ id: string; type: string }>('POST', '/tenants', { name: 'Acme' });
    expect(created.type).toBe('organization');
  });

  it('simulated tasks finish and emit task.succeeded', async () => {
    const events: string[] = [];
    backend.subscribe('wx-demo', e => events.push(e.type));
    const task = await backend.request<{ id: string; status: string }>('POST', '/tenants/wx-demo/tasks', { prompt: 'Summarize', agentId: 'a1' });
    expect(task.status).toBe('running');
    await new Promise(r => setTimeout(r, 1700));
    const tasks = await backend.request<{ id: string; status: string; unread: boolean }[]>('GET', '/tenants/wx-demo/tasks');
    expect(tasks.find(t => t.id === task.id)).toMatchObject({ status: 'done', unread: true });
    expect(events).toEqual(['task.running', 'task.succeeded']);
  });

  it('returns 404 errors for unknown routes', async () => {
    await expect(backend.request('GET', '/nope')).rejects.toBeInstanceOf(ApiRequestError);
  });
});
