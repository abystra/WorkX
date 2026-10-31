import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Agent, Artifact, KnowledgeSource } from '@/api/contracts';
import { ApiRequestError } from '@/api/transport';
import { DevBackend } from '@/dev-backend/backend';

describe('development adapter: knowledge sources (Q-15)', () => {
  let backend: DevBackend;
  beforeEach(() => { vi.useFakeTimers(); localStorage.clear(); backend = new DevBackend(); });
  afterEach(() => vi.useRealTimers());

  const firstFile = async () => (await backend.request<Artifact[]>('GET', '/tenants/wx-demo/artifacts'))[0];

  it('creates one source per file and marks it ready after simulated processing', async () => {
    const file = await firstFile();
    const events: string[] = [];
    backend.subscribe('wx-demo', e => events.push(e.type));
    const source = await backend.request<KnowledgeSource>('POST', '/tenants/wx-demo/knowledge-sources', { fileId: file.id });
    expect(source).toMatchObject({ fileId: file.id, status: 'processing' });
    const again = await backend.request<KnowledgeSource>('POST', '/tenants/wx-demo/knowledge-sources', { fileId: file.id });
    expect(again.id).toBe(source.id);
    await vi.advanceTimersByTimeAsync(1300);
    const [stored] = await backend.request<KnowledgeSource[]>('GET', '/tenants/wx-demo/knowledge-sources');
    expect(stored.status).toBe('ready');
    expect(events).toContain('knowledge.source.updated');
  });

  it('attaches sources to a workmate and rejects unknown ids', async () => {
    const file = await firstFile();
    const source = await backend.request<KnowledgeSource>('POST', '/tenants/wx-demo/knowledge-sources', { fileId: file.id });
    const agent = await backend.request<Agent>('PUT', '/tenants/wx-demo/agents/a1/knowledge', { sourceIds: [source.id, source.id] });
    expect(agent.knowledgeSourceIds).toEqual([source.id]);
    await expect(backend.request('PUT', '/tenants/wx-demo/agents/a1/knowledge', { sourceIds: ['missing'] })).rejects.toBeInstanceOf(ApiRequestError);
    await expect(backend.request('POST', '/tenants/wx-demo/knowledge-sources', { fileId: 'missing' })).rejects.toMatchObject({ code: 'NOT_FOUND' });
  });
});
