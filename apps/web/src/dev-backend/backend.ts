// Development adapter: an in-browser stand-in for the WorkX control plane.
// It answers the same paths as HttpTransport, persists to localStorage, and simulates task execution
// with the prototype's timing. It is loaded only in development/demo/fidelity modes and is never part of
// a production build (enforced by vite.config.ts and scripts/check-production-bundle.mjs).
import type { WorkxEvent } from '@/api/contracts';
import { ApiRequestError, type Method, type Transport } from '@/api/transport';
import { tStatic } from '@/i18n';
import { freshSeed, loadRoot, saveRoot, type Root, type Space, type SpaceData } from './store';
import { recoverChannelRuns, registerChannelRoutes } from './channels';
import {
  canManageSpace, createOrganization, expireInvitations, inviteMembers, normalizeSpace, recordSpaceEvent, recordTeamEvent,
  resourceCollections, saveConnectionMetadata, transitionInvitation, uid, updateResourceSharing,
} from './rules';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Handler = (ctx: { root: Root; params: Record<string, string>; body: any; backend: DevBackend }) => unknown;
interface Route { method: Method; pattern: RegExp; keys: string[]; handler: Handler }

const COLLECTION_FIELDS: Record<string, string> = {
  agents: 'agents', tasks: 'tasks', projects: 'projects', artifacts: 'library', automations: 'automations',
  scenarios: 'scenarioDrafts', members: 'teamMembers', invitations: 'invitations', connections: 'connections',
  activity: 'teamActivity', 'channel-runs': 'channelRuns', 'channel-bindings': 'ecosystemBindings', departments: 'departments',
};

const fail = (code: string, status = 400): never => { throw new ApiRequestError(status, code, code); };

export class DevBackend implements Transport {
  runtime = { mode: 'development', simulated: true } as const;
  root: Root;
  private routes: Route[] = [];
  private listeners = new Map<string, Set<(event: WorkxEvent) => void>>();
  private timers = new Map<string, ReturnType<typeof setTimeout>>();

  constructor() {
    this.root = loadRoot();
    for (const space of this.root.spaces) {
      normalizeSpace(space);
      // Prototype behavior: ordinary tasks that were running when the page closed finish on reload.
      for (const task of space.data.tasks) if (task.status === 'running' && task.kind !== 'channel') task.status = 'done';
      // Channel runs in flight when the page closed become interrupted and wait for an explicit retry.
      recoverChannelRuns(space.data);
    }
    registerCoreRoutes(this);
    registerChannelRoutes(this);
  }

  route(method: Method, path: string, handler: Handler) {
    const keys: string[] = [];
    const pattern = new RegExp('^' + path.replace(/:(\w+)/g, (_m, key) => { keys.push(key); return '([^/]+)'; }) + '$');
    this.routes.push({ method, pattern, keys, handler });
  }

  reset(root: Root = freshSeed()) {
    for (const timer of this.timers.values()) clearTimeout(timer);
    this.timers.clear();
    this.root = root;
    for (const space of this.root.spaces) normalizeSpace(space);
    this.save();
  }

  save() {
    for (const space of this.root.spaces) { space.name = space.data.enterprise.name; normalizeSpace(space); }
    saveRoot(this.root);
  }

  space(tenantId: string): Space {
    return this.root.spaces.find(s => s.id === tenantId) ?? fail('NOT_FOUND', 404);
  }

  emit(tenantId: string, type: string, payload: Record<string, unknown> = {}) {
    const event: WorkxEvent = { event_id: uid('evt_'), type, tenant_id: tenantId, occurred_at: new Date().toISOString(), payload };
    for (const listener of this.listeners.get(tenantId) || []) listener(event);
  }

  schedule(key: string, delay: number, fn: () => void) {
    clearTimeout(this.timers.get(key));
    this.timers.set(key, setTimeout(() => { this.timers.delete(key); fn(); }, delay));
  }

  async request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    await Promise.resolve();
    const clean = path.split('?')[0];
    for (const route of this.routes) {
      if (route.method !== method) continue;
      const match = route.pattern.exec(clean);
      if (!match) continue;
      const params = Object.fromEntries(route.keys.map((key, i) => [key, decodeURIComponent(match[i + 1])]));
      const result = route.handler({ root: this.root, params, body: structuredClone(body ?? {}), backend: this });
      return structuredClone(result ?? null) as T;
    }
    return fail('NOT_FOUND', 404);
  }

  subscribe(tenantId: string, onEvent: (event: WorkxEvent) => void) {
    if (!this.listeners.has(tenantId)) this.listeners.set(tenantId, new Set());
    this.listeners.get(tenantId)!.add(onEvent);
    return () => { this.listeners.get(tenantId)?.delete(onEvent); };
  }
}

const me = (data: SpaceData) => data.teamMembers.find((m: any) => m.id === 'm1');
const summary = (space: Space) => ({ id: space.id, slug: space.id, type: space.type, name: space.data.enterprise.name, role: me(space.data)?.role || 'member' });
const requireManager = (data: SpaceData) => { if (!canManageSpace(data)) fail('spaces.noPermission', 403); };
const findIn = (data: SpaceData, field: string, id: string) => data[field].find((r: any) => r.id === id) ?? fail('NOT_FOUND', 404);

function taskDate() {
  return new Date().toLocaleString('en-US', { timeZone: 'America/Los_Angeles', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).replace(',', '');
}

function registerCoreRoutes(b: DevBackend) {
  // Model tiers offered in the composer. The control plane owns this list (no model IDs in the frontend).
  b.route('GET', '/models', () => [
    { id: 'Auto', label: 'Auto' }, { id: 'claude-opus', label: 'Claude Opus' }, { id: 'claude-sonnet', label: 'Claude Sonnet' }, { id: 'claude-haiku', label: 'Claude Haiku' },
  ]);
  b.route('GET', '/me', ({ root }) => ({ user: root.user, lastTenantId: root.activeSpaceId }));
  b.route('PATCH', '/me', ({ root, body, backend }) => {
    if (body.name !== undefined) {
      const name = String(body.name || '').trim();
      if (!name || name.length > 40) fail('spaces.profileInvalid');
      root.user.name = name;
      for (const space of root.spaces) { const m = me(space.data); if (m) m.name = name; }
    }
    if (body.notifications !== undefined) root.user.notifications = !!body.notifications;
    backend.save();
    return { user: root.user, lastTenantId: root.activeSpaceId };
  });
  b.route('PUT', '/me/preferences', ({ root, body, backend }) => {
    if (root.spaces.some(s => s.id === body.lastTenantId)) root.activeSpaceId = body.lastTenantId;
    backend.save();
    return null;
  });
  b.route('GET', '/me/tenants', ({ root }) => root.spaces.map(summary));
  b.route('POST', '/tenants', ({ root, body, backend }) => {
    const result: any = createOrganization(root, body.name, freshSeed().spaces.find(s => s.type === 'organization')!.data.agents);
    if (result.error) fail(result.error);
    backend.save();
    return summary(result.space);
  });
  b.route('GET', '/tenants/:t', ({ params, backend }) => {
    const space = backend.space(params.t);
    return { ...summary(space), settings: { hideQuick: !!space.data.hideQuick, proactive: !!space.data.proactive, notificationsRead: !!space.data.notificationsRead } };
  });
  b.route('PATCH', '/tenants/:t', ({ params, body, backend, root }) => {
    const space = backend.space(params.t), data = space.data;
    if (body.name !== undefined) {
      requireManager(data);
      const value = String(body.name || '').trim();
      if (!value || value.length > 80) fail('spaces.invalidName');
      if (root.spaces.some(s => s.id !== space.id && s.type === 'organization' && s.name.toLowerCase() === value.toLowerCase())) fail('spaces.duplicateName');
      space.name = value; data.enterprise.name = value;
      recordSpaceEvent(data, 'settings');
    }
    for (const key of ['hideQuick', 'proactive', 'notificationsRead']) if (body[key] !== undefined) data[key] = !!body[key];
    backend.save();
    return null;
  });

  // Collections (read). Specific paths first: routes match in registration order.
  b.route('GET', '/tenants/:t/shared-agents', ({ params, backend }) => backend.space(params.t).data.teamAgentIds);
  b.route('GET', '/tenants/:t/:collection', ({ params, backend }) => {
    const field = COLLECTION_FIELDS[params.collection] ?? fail('NOT_FOUND', 404);
    const data = backend.space(params.t).data;
    if (field === 'invitations') expireInvitations(data);
    return data[field];
  });

  // Workmates
  b.route('POST', '/tenants/:t/agents', ({ params, body, backend }) => {
    const data = backend.space(params.t).data;
    const name = String(body.name || '').trim();
    if (!name) fail('请输入伙伴名称');
    const agent = { id: 'a' + Date.now(), name, description: body.description || 'No description yet', tag: body.tag, avatar: body.avatar, tasks: 0, skills: 0 };
    data.agents.push(agent);
    backend.save();
    return agent;
  });
  b.route('PATCH', '/tenants/:t/agents/:id', ({ params, body, backend }) => {
    const agent = findIn(backend.space(params.t).data, 'agents', params.id);
    for (const key of ['name', 'description', 'tag', 'avatar', 'instructions', 'context']) if (body[key] !== undefined) agent[key] = body[key];
    if (body.addSkill) { agent.extraSkills = [...(agent.extraSkills || []), body.addSkill]; agent.skills++; }
    backend.save();
    return agent;
  });

  // Tasks
  b.route('POST', '/tenants/:t/tasks', ({ params, body, backend }) => {
    const tenantId = params.t, data = backend.space(tenantId).data;
    const text = String(body.prompt || '').trim();
    if (!text) fail('VALIDATION_FAILED');
    const kind = body.kind === 'code' ? 'code' : 'work';
    const agent = data.agents.find((a: any) => a.id === (kind === 'code' ? 'a3' : body.agentId)) || data.agents[0];
    const id = 't' + Date.now() + Math.random().toString(36).slice(2, 6), fileId = 'f' + id;
    const task = { id, tenantId, ownerId: 'm1', name: text.length > 30 ? text.slice(0, 30) + '…' : text, prompt: text, date: taskDate(), agent: agent.id, status: 'running', project: body.projectId || '', file: fileId, kind, attachment: body.attachment || '', model: body.model || 'Auto', capabilities: [...(body.capabilities || [])], answerKind: 'simulated' };
    data.tasks.unshift(task);
    agent.tasks++;
    data.library.unshift({ id: fileId, tenantId, ownerId: 'm1', project: body.projectId || '', name: text.slice(0, 24) + ' · ' + tStatic('actions.deliverable'), type: 'doc', updated: 'Just now', content: tStatic('actions.generatedDocument', { prompt: text }) });
    const project = data.projects.find((p: any) => p.id === body.projectId);
    if (project && !project.agentIds.includes(agent.id)) project.agentIds.push(agent.id);
    backend.save();
    backend.emit(tenantId, 'task.running', { task_id: id });
    backend.schedule(tenantId + ':' + id, 1600, () => {
      const current = backend.space(tenantId).data.tasks.find((t: any) => t.id === id);
      if (!current) return;
      current.status = 'done';
      current.unread = true;
      backend.save();
      backend.emit(tenantId, 'task.succeeded', { task_id: id, artifact_id: fileId });
    });
    return task;
  });
  b.route('PATCH', '/tenants/:t/tasks/:id', ({ params, body, backend }) => {
    const data = backend.space(params.t).data, task = findIn(data, 'tasks', params.id);
    if (body.name !== undefined) { const name = String(body.name).trim(); if (!name) fail('VALIDATION_FAILED'); task.name = name; }
    for (const key of ['pinned', 'archived', 'unread']) if (body[key] !== undefined) task[key] = !!body[key];
    // Assignment and review (prototype team.js team-save-assignment / team-accept-task).
    const project = data.projects.find((p: any) => p.id === task.project);
    if (body.ownerId !== undefined) {
      task.ownerId = data.teamMembers.some((m: any) => m.id === body.ownerId && (!project || project.memberIds.includes(m.id) || m.id === task.ownerId)) ? body.ownerId : '';
      task.supportingAgentIds = data.agents.filter((a: any) => a.id !== task.agent && (!project || project.agentIds.includes(a.id)) && (body.supportingAgentIds || []).includes(a.id)).map((a: any) => a.id);
      recordTeamEvent(data, 'assigned', { task: task.name, projectId: task.project || '' });
    }
    if (body.reviewState !== undefined) {
      if (task.status !== 'done') fail('project.runningReview');
      task.reviewState = body.reviewState === 'accepted' ? 'accepted' : 'review';
      recordTeamEvent(data, task.reviewState === 'accepted' ? 'accepted' : 'reopened', { task: task.name, projectId: task.project || '' });
    }
    backend.save();
    return task;
  });
  b.route('POST', '/tenants/:t/tasks/:id/messages', ({ params, body, backend }) => {
    const task = findIn(backend.space(params.t).data, 'tasks', params.id);
    task.replies = [...(task.replies || []), { prompt: String(body.prompt || '').trim() }];
    backend.save();
    return task;
  });

  // Projects, automations
  b.route('POST', '/tenants/:t/projects', ({ params, body, backend }) => {
    const data = backend.space(params.t).data, name = String(body.name || '').trim();
    if (!name) fail('VALIDATION_FAILED');
    const project = { id: 'p' + Date.now(), name, description: String(body.description || '').trim(), tasks: 0, updated: 'Just now' };
    data.projects.unshift(project);
    backend.save();
    return findIn(data, 'projects', project.id);
  });
  b.route('PATCH', '/tenants/:t/projects/:id', ({ params, body, backend }) => {
    const data = backend.space(params.t).data, project = findIn(data, 'projects', params.id);
    if (body.sharedContext !== undefined) {
      project.sharedContext = String(body.sharedContext).trim().slice(0, 6000);
      recordTeamEvent(data, 'contextChanged', { project: project.name, projectId: project.id });
    }
    if (body.memberIds !== undefined || body.agentIds !== undefined) {
      const members = data.teamMembers.filter((m: any) => (body.memberIds || []).includes(m.id)).map((m: any) => m.id);
      const agents = data.agents.filter((a: any) => (body.agentIds || []).includes(a.id)).map((a: any) => a.id);
      if (!members.length || !agents.length) fail('project.rosterRequired');
      project.memberIds = members;
      project.agentIds = agents;
      recordTeamEvent(data, 'rosterChanged', { project: project.name, projectId: project.id });
    }
    backend.save();
    return project;
  });
  b.route('POST', '/tenants/:t/automations', ({ params, body, backend }) => {
    const data = backend.space(params.t).data;
    if (!String(body.name || '').trim() || !String(body.description || '').trim()) fail('VALIDATION_FAILED');
    const automation = { id: 'au' + Date.now(), name: body.name.trim(), description: body.description.trim(), schedule: `${body.frequency} at ${body.time}`, enabled: true };
    data.automations.unshift(automation);
    backend.save();
    return automation;
  });
  b.route('PATCH', '/tenants/:t/automations/:id', ({ params, body, backend }) => {
    const automation = findIn(backend.space(params.t).data, 'automations', params.id);
    if (body.enabled !== undefined) automation.enabled = !!body.enabled;
    backend.save();
    return automation;
  });

  // Members, invitations
  b.route('PATCH', '/tenants/:t/members/:id', ({ params, body, backend }) => {
    const data = backend.space(params.t).data;
    requireManager(data);
    const member = findIn(data, 'teamMembers', params.id);
    const name = String(body.name ?? member.name).trim(), departmentId = String(body.departmentId ?? member.departmentId ?? '');
    if (!name || name.length > 40 || (departmentId && !data.departments.some((d: any) => d.id === departmentId))) fail('saas.invalid');
    if (member.role !== 'owner' && ((body.role && !['admin', 'member'].includes(body.role)) || (body.status && !['active', 'disabled'].includes(body.status)))) fail('saas.invalid');
    Object.assign(member, { name, departmentId }, member.role === 'owner' ? { status: 'active' } : { role: body.role ?? member.role, status: body.status ?? member.status });
    recordTeamEvent(data, 'enterpriseChanged');
    backend.save();
    return member;
  });
  b.route('POST', '/tenants/:t/invitations', ({ params, body, backend }) => {
    const data = backend.space(params.t).data;
    const result: any = inviteMembers(data, body);
    if (result.error) fail(result.error);
    recordSpaceEvent(data, 'invited');
    backend.save();
    return result.invitations;
  });
  b.route('POST', '/tenants/:t/invitations/:id/:action', ({ params, backend }) => {
    if (!['accept', 'cancel'].includes(params.action)) fail('NOT_FOUND', 404);
    const data = backend.space(params.t).data;
    const result: any = transitionInvitation(data, params.id, params.action as 'accept' | 'cancel');
    if (result.error) fail(result.error);
    recordSpaceEvent(data, 'invitation');
    backend.save();
    return null;
  });

  // Connections (metadata only; secrets never accepted here)
  b.route('POST', '/tenants/:t/connections', ({ params, body, backend }) => {
    const data = backend.space(params.t).data;
    const result: any = saveConnectionMetadata(data, body);
    if (result.error) fail(result.error);
    recordSpaceEvent(data, 'connection');
    backend.save();
    return result.connection;
  });
  b.route('PATCH', '/tenants/:t/connections/:id', ({ params, body, backend }) => {
    const data = backend.space(params.t).data, connection = findIn(data, 'connections', params.id);
    if (connection.ownerScope === 'space' ? !canManageSpace(data) : connection.ownerId !== 'm1') fail('spaces.noPermission', 403);
    if (body.enabled !== undefined) connection.enabled = !!body.enabled;
    recordSpaceEvent(data, 'connection');
    backend.save();
    return connection;
  });

  // Sharing
  b.route('PUT', '/tenants/:t/resources/:collection/:id/sharing', ({ params, body, backend }) => {
    const data = backend.space(params.t).data;
    const collection = params.collection === 'artifacts' ? 'library' : params.collection;
    if (!(resourceCollections as readonly string[]).includes(collection)) fail('NOT_FOUND', 404);
    const result: any = updateResourceSharing(data, collection, params.id, body);
    if (result.error) fail(result.error);
    recordSpaceEvent(data, 'sharing');
    backend.save();
    return result.resource;
  });
}
