import { describe, expect, it } from 'vitest';
import { displayDate, fromCron, mapTask, plan, skillId, toCron, viewStatus } from './http-mapping';

describe('HTTP mapping (view models ↔ control-plane API)', () => {
  it('translates automation schedules both ways', () => {
    expect(toCron('Every weekday', '09:30')).toBe('30 9 * * 1-5');
    expect(fromCron('30 9 * * 1-5')).toBe('Every weekday at 09:30');
    expect(fromCron(toCron('Every Friday', '18:05'))).toBe('Every Friday at 18:05');
    expect(fromCron('*/15 * * * *')).toBe('*/15 * * * *');
  });

  it('maps statuses, skills and dates to the prototype vocabulary', () => {
    expect(viewStatus('succeeded')).toBe('done');
    expect(viewStatus('awaiting_approval')).toBe('running');
    expect(viewStatus('interrupted')).toBe('interrupted');
    expect(skillId('Deep Research')).toBe('deep-research');
    const now = new Date('2026-10-31T10:00:00');
    expect(displayDate('2026-10-31T08:00:00', now)).toBe('Today');
    expect(displayDate('2026-10-30T23:00:00', now)).toBe('Yesterday');
    expect(displayDate('2026-10-02T08:00:00', now)).toBe('Oct 2');
  });

  it('plans task creation and patches with API field names', () => {
    const create = plan('POST', '/tenants/ten_1/tasks', { prompt: 'Hi', agentId: 'agt_1', projectId: '', model: 'Auto', capabilities: ['Deep Research'] });
    expect(create.body).toEqual({ agent_id: 'agt_1', prompt: 'Hi', project_id: null, model_tier: 'auto', capabilities: ['deep-research'] });
    const patch = plan('PATCH', '/tenants/ten_1/tasks/tsk_1', { ownerId: 'mem_2', reviewState: 'accepted', pinned: true });
    expect(patch.body).toEqual({ pinned: true, assignee_id: 'mem_2', review_state: 'accepted' });
    const roster = plan('PATCH', '/tenants/ten_1/projects/prj_1', { memberIds: ['mem_2'], agentIds: [] });
    expect([roster.method, roster.path, roster.body]).toEqual(['PUT', '/tenants/ten_1/projects/prj_1/roster', { member_ids: ['mem_2'], agent_ids: [] }]);
    const tenant = plan('PATCH', '/tenants/ten_1', { hideQuick: true, proactive: false });
    expect(tenant.body).toEqual({ settings: { proactive: false }, preferences: { hideQuick: true } });
  });

  it('serves later-phase endpoints locally instead of calling missing routes', () => {
    expect(plan('POST', '/tenants/ten_1/channel-messages', {}).local).toBeInstanceOf(Error);
    expect(plan('GET', '/tenants/ten_1/artifacts', undefined).path).toBe('/tenants/ten_1/files?include_content=true');
  });

  it('maps connections, their secrets and bound workmates', () => {
    const create = plan('POST', '/tenants/ten_1/connections', { connectorId: 'crm', name: 'CRM', ownerScope: 'space', secret: 'k' });
    expect(create.body).toEqual({ connector_id: 'crm', name: 'CRM', scope: 'tenant', secret: 'k' });
    expect(plan('PATCH', '/tenants/ten_1/connections/con_1', { enabled: false }).body).toEqual({ status: 'suspended' });
    const bind = plan('PUT', '/tenants/ten_1/connections/con_1/usage-policy', { agentIds: ['agt_1'], tools: ['crm_list_accounts'] });
    expect(bind.body).toEqual([{ principal_type: 'agent', principal_ref: 'agt_1', allowed_tools: ['crm_list_accounts'] }]);
    const [view] = plan('GET', '/tenants/ten_1/connections', undefined).out([
      { id: 'con_1', name: 'CRM', connector_id: 'crm', connector_name: 'CRM', auth: 'api_key', scope: 'tenant', owner_id: 'mem_1', status: 'suspended', agent_ids: ['agt_1'] },
    ]) as Record<string, unknown>[];
    expect(view).toMatchObject({ provider: 'api', authMode: 'static', ownerScope: 'space', enabled: false, agentIds: ['agt_1'], connectorName: 'CRM' });
  });

  it('maps channel bindings, their connection setup and runs', () => {
    const create = plan('POST', '/tenants/ten_1/channel-bindings', { platform: 'feishu', method: 'feishu-app-bot', name: 'Bot', assignedAgent: 'agt_1', capabilities: ['message-receive'] });
    expect(create.body).toEqual({ name: 'Bot', agent_id: 'agt_1', capabilities: ['message-receive'], platform: 'feishu', method: 'feishu-bot', config: {} });
    const edit = plan('POST', '/tenants/ten_1/channel-bindings', { id: 'chb_1', name: 'Bot 2', assignedAgent: 'agt_1', capabilities: [] });
    expect([edit.method, edit.path]).toEqual(['PATCH', '/tenants/ten_1/channel-bindings/chb_1']);
    const setup = plan('PUT', '/tenants/ten_1/channel-bindings/chb_1/connection', { platform: 'wecom', draft: { parameters: { corpId: 'ww1', agentId: '1000002', appSecret: 's', token: 't', encodingAESKey: 'k' } } });
    expect(setup.body).toEqual({ config: { corp_id: 'ww1', agent_id: '1000002' }, secrets: { secret: 's', token: 't', encoding_aes_key: 'k' } });
    const [binding] = plan('GET', '/tenants/ten_1/channel-bindings', undefined).out([{ id: 'chb_1', name: 'Bot', platform: 'feishu', method: 'feishu-bot', agent_id: 'agt_1', capabilities: ['message-receive'], enabled: true, revision: 1, config: { app_id: 'cli' }, configured: true }]) as Record<string, any>[];
    expect(binding).toMatchObject({ method: 'feishu-app-bot', assignedAgent: 'agt_1', connection: { verified: true, parameters: { appId: 'cli' } } });
  });

  it('maps a task response into the view model', () => {
    const view = mapTask({
      id: 'tsk_1', name: 'n', created_at: '2026-10-29T19:06:00', agent_id: 'agt_1', status: 'succeeded', project_id: null,
      unread: true, pinned: false, archived: false, kind: 'work', prompt: 'p', model_tier: 'auto', capabilities: [],
      follow_ups: ['more'], assignee_id: 'mem_1', supporting_agent_ids: [], review_state: 'review', answer: '# Done',
      answer_file_id: 'fil_1', visibility: 'private', created_by: 'mem_1', status_reason: null,
    });
    expect(view).toMatchObject({ status: 'done', date: '10/29 19:06', replies: [{ prompt: 'more' }], answer: '# Done', file: 'fil_1', answerKind: 'markdown' });
  });
});
