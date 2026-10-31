// Development adapter: ecosystem bindings, connection setup records, simulated channel messages and
// their execution/delivery runs (ported from the prototype's ecosystem.js, connection.js and
// channel-model.js). In production these are the channel-worker, Broker and control-plane flows of
// docs/architecture/06 and 08 (J6); nothing here talks to Feishu or WeCom.
/* eslint-disable @typescript-eslint/no-explicit-any */
import { tStatic } from '@/i18n';
import { bindingIsReady, methodBy, normalizeCapabilities, platformBy } from '@/domain/ecosystem-model.js';
import { reconcileConnection, sanitizeConnection } from '@/domain/connection-model.js';
import { channelBindingIdentity, channelBindingReady } from '@/domain/channel-rules';
import { ApiRequestError } from '@/api/transport';
import type { DevBackend } from './backend';
import type { SpaceData } from './store';
import { uid } from './rules';

const fail = (code: string, status = 400): never => { throw new ApiRequestError(status, code, code); };
const ACTIVE = ['received', 'running', 'result', 'sending'];

export function recoverChannelRuns(data: SpaceData) {
  for (const run of data.channelRuns || []) {
    if (!ACTIVE.includes(run.stage)) continue;
    run.stage = 'interrupted'; run.errorKey = 'channel.interruptedHint'; run.history = Array.isArray(run.history) ? run.history : [];
    if (run.executionStatus !== 'done') { run.executionStatus = 'interrupted'; const task = data.tasks.find((x: any) => x.id === run.taskId); if (task) task.status = 'failed'; }
    else run.deliveryStatus = 'interrupted';
    run.history.push({ key: 'channel.event.interrupted', at: Date.now() });
  }
  for (const task of data.tasks) if (task.kind === 'channel' && task.status === 'running' && !data.channelRuns.some((r: any) => r.taskId === task.id)) task.status = 'failed';
}

export function registerChannelRoutes(b: DevBackend) {
  const data = (t: string) => b.space(t).data;
  const record = (run: any, key: string) => run.history.push({ key, at: Date.now() });
  const update = (tenantId: string, run: any) => { b.save(); b.emit(tenantId, 'channel.run.updated', { run_id: run.id, task_id: run.taskId }); };
  const getTask = (d: SpaceData, run: any) => d.tasks.find((x: any) => x.id === run.taskId);
  const binding = (d: SpaceData, id: string) => d.ecosystemBindings.find((x: any) => x.id === id);
  const canContinue = (d: SpaceData, run: any) => {
    const current = binding(d, run.bindingId);
    return channelBindingReady(current, d) && channelBindingIdentity(current) === run.bindingSignature && d.agents.some((a: any) => a.id === run.agentId) && !!getTask(d, run);
  };
  const stop = (tenantId: string, run: any) => b.schedule(`${tenantId}:run:${run.id}`, 0, () => {});
  const blocked = (tenantId: string, run: any, delivery = false) => {
    const d = data(tenantId);
    run.errorKey = 'channel.blocked'; run.stage = delivery ? 'delivery_failed' : 'execution_failed';
    if (delivery) run.deliveryStatus = 'failed';
    else { run.executionStatus = 'failed'; const task = getTask(d, run); if (task) task.status = 'failed'; }
    record(run, 'channel.event.blocked'); update(tenantId, run);
  };
  const beginDelivery = (tenantId: string, run: any, failDelivery = false) => {
    const d = data(tenantId);
    if (!canContinue(d, run)) { blocked(tenantId, run, true); return; }
    run.stage = 'sending'; run.deliveryStatus = 'sending'; run.deliveryAttempts++; run.errorKey = '';
    record(run, 'channel.event.sending'); update(tenantId, run);
    b.schedule(`${tenantId}:run:${run.id}`, 800, () => {
      if (!canContinue(data(tenantId), run)) { blocked(tenantId, run, true); return; }
      run.stage = failDelivery ? 'delivery_failed' : 'delivered'; run.deliveryStatus = failDelivery ? 'failed' : 'delivered'; run.errorKey = failDelivery ? 'channel.deliveryError' : '';
      if (!failDelivery) run.reply = { text: run.resultText, conversation: run.source.conversation, kind: run.source.kind, platform: run.platform, sender: run.source.sender, at: Date.now(), simulated: true };
      record(run, failDelivery ? 'channel.event.deliveryFailed' : 'channel.event.delivered'); update(tenantId, run);
    });
  };
  const beginExecution = (tenantId: string, run: any, failExecution = false, failDelivery = false) => {
    const d = data(tenantId);
    if (!canContinue(d, run)) { blocked(tenantId, run); return; }
    run.stage = 'running'; run.executionStatus = 'running'; run.errorKey = ''; run.executionAttempts++;
    const task = getTask(d, run); task.status = 'running';
    record(run, 'channel.event.running'); update(tenantId, run);
    b.schedule(`${tenantId}:run:${run.id}`, 1400, () => {
      const d2 = data(tenantId);
      if (!canContinue(d2, run)) { blocked(tenantId, run); return; }
      const t2 = getTask(d2, run);
      if (failExecution) { run.stage = 'execution_failed'; run.executionStatus = 'failed'; run.errorKey = 'channel.executionError'; t2.status = 'failed'; record(run, 'channel.event.executionFailed'); update(tenantId, run); return; }
      run.executionStatus = 'done'; run.stage = 'result'; t2.status = 'done'; t2.reviewState = 'review'; t2.unread = true;
      run.resultText = tStatic('channel.generatedResult', { agent: run.agentName, message: run.source.message });
      if (!run.fileId) { run.fileId = uid('channel-file'); d2.library.unshift({ id: run.fileId, name: t2.name + ' · ' + tStatic('channel.deliverable'), type: 'doc', updated: 'Just now', content: run.resultText }); }
      t2.file = run.fileId; record(run, 'channel.event.result'); update(tenantId, run);
      b.schedule(`${tenantId}:run:${run.id}`, 500, () => beginDelivery(tenantId, run, failDelivery));
    });
  };
  const receive = (tenantId: string, input: any) => {
    const d = data(tenantId);
    const bound = binding(d, input.bindingId);
    if (!channelBindingReady(bound, d)) return { error: 'channel.bindingUnavailable' };
    if (!['direct', 'group'].includes(input.kind)) return { error: 'channel.invalidKind' };
    const source = { sender: String(input.sender || '').trim(), conversation: String(input.conversation || '').trim(), message: String(input.message || '').trim(), kind: input.kind === 'group' ? 'group' : 'direct', mentioned: input.mentioned === true };
    if (!source.sender || source.sender.length > 60 || !source.conversation || source.conversation.length > 100 || !source.message || source.message.length > 2000) return { error: 'channel.requiredMessage' };
    if (source.kind === 'group' && (bound.method === 'wecom-app' || !source.mentioned)) return { error: bound.method === 'wecom-app' ? 'channel.directOnly' : 'channel.mentionRequired' };
    if (input.projectId && !d.projects.some((p: any) => p.id === input.projectId)) return { error: 'channel.invalidProject' };
    const eventId = String(input.eventId || uid('event'));
    const existing = d.channelRuns.find((r: any) => r.bindingId === bound.id && r.eventId === eventId);
    if (existing) { existing.replayCount = (existing.replayCount || 0) + 1; record(existing, 'channel.event.duplicate'); update(tenantId, existing); return { run: existing, duplicate: true }; }
    const agent = d.agents.find((a: any) => a.id === bound.assignedAgent), id = uid('channel'), taskId = uid('channel-task');
    const run = { id, eventId, bindingId: bound.id, bindingName: bound.name, bindingSignature: channelBindingIdentity(bound), platform: bound.platform, method: bound.method, agentId: agent.id, agentName: agent.name, source, taskId, projectId: input.projectId || '', scenario: ['execution_error', 'delivery_error'].includes(input.scenario) ? input.scenario : 'success', stage: 'received', executionStatus: 'queued', deliveryStatus: 'pending', executionAttempts: 0, deliveryAttempts: 0, history: [], createdAt: Date.now(), resultText: '', errorKey: '', fileId: null };
    const task = { id: taskId, name: source.message.length > 40 ? source.message.slice(0, 40) + '…' : source.message, prompt: source.message, date: new Date().toLocaleString('en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }), agent: agent.id, status: 'running', project: run.projectId, kind: 'channel', channelRunId: id, unread: true };
    d.channelRuns.unshift(run); d.tasks.unshift(task); agent.tasks = (Number(agent.tasks) || 0) + 1;
    const project = d.projects.find((p: any) => p.id === run.projectId);
    if (project && !project.agentIds.includes(agent.id)) project.agentIds.push(agent.id);
    record(run, 'channel.event.received'); update(tenantId, run);
    b.schedule(`${tenantId}:run:${run.id}`, 500, () => beginExecution(tenantId, run, run.scenario === 'execution_error', run.scenario === 'delivery_error'));
    return { run, duplicate: false };
  };

  // Bindings (wizard save, enable/disable, delete) and their non-secret connection setup record.
  b.route('POST', '/tenants/:t/channel-bindings', ({ params, body }) => {
    const d = data(params.t);
    const existing = body.id ? binding(d, body.id) : undefined;
    if (body.id && !existing) fail('eco.bindingMissing');
    const saved: any = { id: existing?.id || 'eco-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8), platform: body.platform, method: body.method, name: String(body.name || '').trim(), assignedAgent: body.assignedAgent, capabilities: normalizeCapabilities(body.method, body.capabilities), configured: true, enabled: existing ? existing.enabled !== false : true, ...(body.method === 'wecom-ai-bot' ? { transport: body.transport } : {}) };
    if (!platformBy(saved.platform) || !methodBy(saved.method) || !bindingIsReady(saved, d)) fail('eco.requiredCapability');
    reconcileConnection(existing, saved);
    if (existing) d.ecosystemBindings.splice(d.ecosystemBindings.indexOf(existing), 1, saved);
    else d.ecosystemBindings.unshift(saved);
    b.save();
    return saved;
  });
  b.route('PATCH', '/tenants/:t/channel-bindings/:id', ({ params, body }) => {
    const d = data(params.t), current = binding(d, params.id) ?? fail('NOT_FOUND', 404);
    if (body.enabled !== undefined) {
      if (body.enabled && !bindingIsReady(current, d)) fail('eco.reviewBeforeResume');
      current.enabled = !!body.enabled;
    }
    b.save();
    return current;
  });
  b.route('DELETE', '/tenants/:t/channel-bindings/:id', ({ params }) => {
    const d = data(params.t);
    d.ecosystemBindings = d.ecosystemBindings.filter((x: any) => x.id !== params.id);
    b.save();
    return null;
  });
  b.route('PUT', '/tenants/:t/channel-bindings/:id/connection', ({ params, body }) => {
    const current = binding(data(params.t), params.id) ?? fail('NOT_FOUND', 404);
    // Server-side allow-list: secrets in body.draft are discarded by sanitizeConnection.
    current.connection = sanitizeConnection(current, body.draft || {}, body.test);
    b.save();
    return current;
  });

  // Simulated inbound messages and run controls (development adapter only).
  b.route('POST', '/tenants/:t/channel-messages', ({ params, body }) => {
    const result: any = receive(params.t, body);
    if (result.error) fail(result.error);
    return { run: result.run, duplicate: result.duplicate };
  });
  b.route('POST', '/tenants/:t/channel-runs/:id/:action', ({ params }) => {
    const d = data(params.t), run = d.channelRuns.find((r: any) => r.id === params.id) ?? fail('NOT_FOUND', 404);
    if (params.action === 'replay') {
      const result: any = receive(params.t, { ...run.source, bindingId: run.bindingId, eventId: run.eventId, projectId: run.projectId, scenario: run.scenario });
      return { message: result.error || 'channel.duplicate' };
    }
    if (params.action === 'cancel') {
      if (!ACTIVE.includes(run.stage)) return null;
      stop(params.t, run);
      run.stage = 'cancelled'; run.errorKey = 'channel.cancelledHint';
      if (run.executionStatus !== 'done') { run.executionStatus = 'cancelled'; const task = getTask(d, run); if (task) task.status = 'failed'; }
      run.deliveryStatus = 'cancelled'; record(run, 'channel.event.cancelled'); update(params.t, run);
      return null;
    }
    if (params.action === 'retry-execution') {
      if (!['failed', 'cancelled', 'interrupted'].includes(run.executionStatus)) return null;
      if (!canContinue(d, run)) { blocked(params.t, run); return null; }
      record(run, 'channel.event.executionRetry'); run.deliveryStatus = 'pending'; beginExecution(params.t, run);
      return null;
    }
    if (params.action === 'retry-delivery') {
      if (run.executionStatus !== 'done' || !['failed', 'cancelled', 'interrupted'].includes(run.deliveryStatus) || !run.fileId) return null;
      if (!canContinue(d, run)) { blocked(params.t, run, true); return null; }
      record(run, 'channel.event.deliveryRetry'); beginDelivery(params.t, run);
      return null;
    }
    return fail('NOT_FOUND', 404);
  });

  // Business scenario drafts.
  b.route('POST', '/tenants/:t/scenarios', ({ params, body }) => {
    const d = data(params.t), draft = { id: 'sc-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7), ...scenarioFields(body) };
    d.scenarioDrafts.unshift(draft);
    b.save();
    return draft;
  });
  b.route('PATCH', '/tenants/:t/scenarios/:id', ({ params, body }) => {
    const draft = data(params.t).scenarioDrafts.find((x: any) => x.id === params.id) ?? fail('NOT_FOUND', 404);
    Object.assign(draft, scenarioFields(body));
    b.save();
    return draft;
  });
  b.route('DELETE', '/tenants/:t/scenarios/:id', ({ params }) => {
    const d = data(params.t);
    d.scenarioDrafts = d.scenarioDrafts.filter((x: any) => x.id !== params.id);
    b.save();
    return null;
  });
}

function scenarioFields(body: any) {
  const text = (v: unknown) => String(v || '').trim();
  if (!text(body.name)) fail('scene.requiredName');
  if (!text(body.problem)) fail('scene.requiredProblem');
  return { name: text(body.name), problem: text(body.problem), role: text(body.role), input: text(body.input), output: text(body.output), ecosystems: (body.ecosystems || []).filter((v: string) => platformBy(v)), status: 'draft' };
}
