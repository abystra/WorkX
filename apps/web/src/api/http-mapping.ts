/* eslint-disable @typescript-eslint/no-explicit-any */
// Maps the UI's view-model calls (api/client.ts, shaped after the prototype) onto the control-plane API
// (docs/architecture/11-DATA-API-EVENTS.md: snake_case, prefixed ids, separate routes for roster/sharing).
// Screens never see API shapes; everything is translated here, in one place.

import type { Method } from './transport';

export interface Planned {
  method: Method;
  path: string;
  body?: unknown;
  /** Converts the API response into the view model the screen expects. */
  out: (json: any) => unknown;
  /** Value to return without calling the API (features whose backend arrives in a later phase). */
  local?: unknown;
  /** Manager-only lists the UI loads for everyone: a 403 means "nothing to show you", not a page error. */
  forbiddenAs?: unknown;
}

const identity = (json: any) => json;

/** Prototype display dates: "Today", "Yesterday", "Oct 28" (formatRelative localizes them). */
export function displayDate(iso?: string | null, now = new Date()): string {
  if (!iso) return '';
  const date = new Date(iso);
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((day(now) - day(date)) / 86_400_000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** Task list timestamp in the prototype's "10/29 19:06" form. */
export function taskDate(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const FREQUENCIES: Record<string, string> = {
  'Every weekday': '1-5',
  'Every day': '*',
  'Every Monday': '1',
  'Every Friday': '5',
};

/** "Every weekday" + "09:00" → "0 9 * * 1-5". */
export function toCron(frequency: string, time: string): string {
  const [hour, minute] = String(time || '09:00').split(':').map(Number);
  return `${minute || 0} ${hour || 0} * * ${FREQUENCIES[frequency] ?? '*'}`;
}

/** "0 9 * * 1-5" → "Every weekday at 09:00"; other cron expressions are shown as written. */
export function fromCron(cron: string): string {
  const parts = String(cron).split(/\s+/);
  if (parts.length !== 5 || parts[2] !== '*' || parts[3] !== '*') return cron;
  const frequency = Object.entries(FREQUENCIES).find(([, dow]) => dow === parts[4])?.[0];
  const minute = Number(parts[0]);
  const hour = Number(parts[1]);
  if (!frequency || !Number.isInteger(minute) || !Number.isInteger(hour)) return cron;
  return `${frequency} at ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

/** The composer's capability labels ("Deep Research") → catalog ids ("deep-research"). */
export const skillId = (label: string) => String(label).trim().toLowerCase().replace(/\s+/g, '-');

/** API task statuses (Part 4 state machine) → the UI's coarser view. */
export function viewStatus(status: string): string {
  if (status === 'succeeded') return 'done';
  if (['failed', 'cancelled', 'interrupted', 'queued'].includes(status)) return status;
  return 'running';
}

const ACTIVITY: [RegExp, string][] = [
  [/^tenant\.created$/, 'created'],
  [/^invitation\.created$/, 'invited'],
  [/^invitation\./, 'invitation'],
  [/^resource\.sharing_changed$/, 'sharing'],
  [/^connection\./, 'connection'],
  [/^(tenant\.(renamed|settings_changed)|department\.)/, 'settings'],
  [/^membership\./, 'member'],
];

export const mapMe = (m: any) => ({
  user: { id: m.id, name: m.name, email: m.email, notifications: m.notifications },
  lastTenantId: m.last_tenant_id || '',
  csrfToken: m.csrf_token,
});

export const mapTenant = (t: any) => ({
  id: t.id, membershipId: t.membership_id, slug: t.slug, type: t.type, name: t.name, role: t.role,
  ...(t.settings
    ? {
        settings: {
          proactive: Boolean(t.settings?.proactive),
          hideQuick: Boolean(t.preferences?.hideQuick),
          notificationsRead: Boolean(t.preferences?.notificationsRead),
        },
      }
    : {}),
});

const visibility = (v: string) => (v === 'organization' ? 'space' : v);

export const mapAgent = (a: any) => ({
  id: a.id, name: a.name, description: a.description, tag: a.tag, avatar: a.avatar,
  tasks: a.task_count, skills: a.skills.length, extraSkills: [], instructions: a.instructions, context: a.context,
  knowledgeSourceIds: a.knowledge_source_ids, visibility: visibility(a.visibility), resourceOwnerId: a.resource_owner_id,
  modelTier: a.model_tier, skillIds: a.skills, version: a.version,
});

export const mapTask = (t: any) => ({
  id: t.id, name: t.name, date: taskDate(t.created_at), agent: t.agent_id, status: viewStatus(t.status),
  apiStatus: t.status, statusReason: t.status_reason, project: t.project_id || undefined, unread: t.unread,
  pinned: t.pinned, archived: t.archived, kind: t.kind, prompt: t.prompt, model: t.model_tier,
  capabilities: t.capabilities, replies: (t.follow_ups || []).map((prompt: string) => ({ prompt })),
  ownerId: t.assignee_id || undefined, supportingAgentIds: t.supporting_agent_ids, reviewState: t.review_state,
  answer: t.answer || undefined, answerKind: t.answer ? 'markdown' : undefined, file: t.answer_file_id || undefined,
  visibility: visibility(t.visibility), resourceOwnerId: t.created_by,
});

export const mapTaskDetail = (t: any) => ({
  ...mapTask(t),
  messages: (t.messages || []).map((m: any) => ({
    id: m.id, role: m.role, content: m.content, fileId: m.file_id || undefined, createdAt: m.created_at,
    citations: (m.citations || []).map((c: any) => ({ n: c.n, source: c.source, section: c.section, locator: c.locator || {}, snippet: c.snippet })),
  })),
});

export const mapKnowledgeSource = (k: any) => ({
  id: k.id, fileId: k.file_id, name: k.name, status: k.status,
  errorKey: k.error_code ? `web.knowledge.error.${k.error_code}` : undefined,
  updatedAt: Date.parse(k.updated_at) || Date.now(),
});

/** Catalog connector → the prototype's provider and auth-mode vocabulary (the card's icon and subtitle). */
const PROVIDER: Record<string, string> = { 'feishu-docs': 'feishu', notes: 'mcp' };
const AUTH_MODE: Record<string, string> = { api_key: 'static', oauth: 'oauth', none: 'none' };

export const mapConnection = (c: any) => ({
  id: c.id, name: c.name, connectorId: c.connector_id, connectorName: c.connector_name,
  provider: PROVIDER[c.connector_id] || 'api', authMode: AUTH_MODE[c.auth] || 'static',
  ownerScope: c.scope === 'tenant' ? 'space' : 'member', ownerId: c.owner_id, agentIds: c.agent_ids || [],
  status: c.status === 'active' ? 'active' : 'needs_auth', enabled: c.status !== 'suspended', usageClass: 'tool',
});

/** Channel binding methods: UI (prototype) ids ↔ API ids. Other UI methods have no backend yet. */
const METHOD_OUT: Record<string, string> = { 'feishu-bot': 'feishu-app-bot', 'wecom-app': 'wecom-app' };
const METHOD_IN: Record<string, string> = { 'feishu-app-bot': 'feishu-bot', 'wecom-app': 'wecom-app' };
const PARAM_OUT: Record<string, string> = { app_id: 'appId', corp_id: 'corpId', agent_id: 'agentId' };

export const mapBinding = (b: any) => {
  const view: any = {
    id: b.id, name: b.name, platform: b.platform, method: METHOD_OUT[b.method] || b.method, assignedAgent: b.agent_id,
    capabilities: b.capabilities || [], enabled: b.enabled, configured: true, revision: b.revision,
    webhookUrl: b.webhook_url || undefined, credentialsSet: b.configured,
  };
  if (b.configured) {
    // Real credentials stored by the broker stand in for the prototype's simulated connection test.
    view.connection = {
      signature: JSON.stringify([view.platform, view.method, '', view.assignedAgent, [...view.capabilities].sort()]),
      parameters: Object.fromEntries(Object.entries(b.config || {}).map(([k, v]) => [PARAM_OUT[k] || k, v])),
      verified: true,
    };
  }
  return view;
};

/** Connection dialog parameters → non-secret config and broker secrets. */
export function connectionBody(platform: string, params: Record<string, string>) {
  const config: Record<string, string> = {}, secrets: Record<string, string> = {};
  const put = (target: Record<string, string>, key: string, value?: string) => { if (value) target[key] = String(value).trim(); };
  put(config, platform === 'feishu' ? 'app_id' : 'corp_id', platform === 'feishu' ? params.appId : params.corpId);
  if (platform === 'wecom') put(config, 'agent_id', params.agentId);
  put(secrets, platform === 'feishu' ? 'app_secret' : 'secret', params.appSecret);
  put(secrets, 'verification_token', params.verificationToken);
  put(secrets, 'encrypt_key', params.encryptKey);
  put(secrets, 'token', params.token);
  put(secrets, 'encoding_aes_key', params.encodingAESKey);
  return { config, secrets };
}

export const mapChannelRun = (r: any) => ({
  id: r.id, taskId: r.task_id || '', bindingId: r.binding_id, bindingName: r.binding_name, platform: r.platform,
  agentId: r.agent_id, agentName: r.agent_name, source: r.source, stage: r.stage, executionStatus: r.execution_status,
  deliveryStatus: r.delivery_status, executionAttempts: r.task_id ? 1 : 0, deliveryAttempts: r.delivery_attempts,
  errorKey: r.error_code ? `web.channel.error.${r.error_code}` : undefined,
  reply: r.reply ? { text: r.reply.text, at: Date.parse(r.reply.at) } : undefined,
  history: [], eventId: r.event_id, replayCount: r.replay_count,
});

export const mapApproval = (a: any) => ({ id: a.id, tool: a.tool, summary: a.summary, status: a.status, expiresAt: a.expires_at });

export const mapProject = (p: any) => ({
  id: p.id, name: p.name, description: p.description, tasks: p.task_count, updated: displayDate(p.updated_at),
  color: p.color || undefined, memberIds: p.member_ids, agentIds: p.agent_ids, sharedContext: p.shared_context,
  visibility: visibility(p.visibility), resourceOwnerId: p.resource_owner_id,
});

const FILE_TYPES = new Set(['doc', 'slides', 'sheet']);
export const mapFile = (f: any) => ({
  id: f.id, name: f.name, type: FILE_TYPES.has(f.kind) ? f.kind : 'doc', updated: displayDate(f.updated_at),
  content: f.content ?? undefined, project: f.project_id || undefined, visibility: visibility(f.visibility),
  resourceOwnerId: f.resource_owner_id,
});

export const mapAutomation = (a: any) => ({
  id: a.id, name: a.name, description: a.description || a.prompt, schedule: fromCron(a.schedule), enabled: a.enabled,
  resourceOwnerId: a.resource_owner_id,
});

export const mapScenario = (s: any) => ({
  id: s.id, name: s.name, problem: s.problem, role: s.role, input: s.input, output: s.output, ecosystems: s.ecosystems,
});

export const mapMember = (m: any) => ({
  id: m.id, name: m.name, email: m.email, role: m.role, status: m.status === 'deactivated' ? 'disabled' : m.status,
  departmentId: m.department_id || undefined,
});

export const mapInvitation = (i: any) => ({
  id: i.id, email: i.email, role: i.role, status: i.status, createdAt: Date.parse(i.created_at), expiresAt: Date.parse(i.expires_at),
});

export const mapDepartment = (d: any) => ({ id: d.id, name: d.name, parentId: d.parent_id || undefined });

export const mapActivity = (page: any) =>
  (page?.items || []).map((e: any) => ({
    id: e.id, at: e.created_at, type: e.action,
    spaceEvent: ACTIVITY.find(([pattern]) => pattern.test(e.action))?.[1] || 'legacy',
  }));

function taskBody(b: any) {
  return {
    agent_id: b.agentId,
    prompt: b.prompt,
    project_id: b.projectId || null,
    model_tier: !b.model || b.model === 'Auto' ? 'auto' : String(b.model).toLowerCase(),
    capabilities: (b.capabilities || []).map(skillId),
  };
}

function taskPatch(b: any) {
  const out: Record<string, unknown> = {};
  for (const key of ['name', 'pinned', 'archived', 'unread']) if (key in b) out[key] = b[key];
  if ('ownerId' in b) out.assignee_id = b.ownerId || null;
  if ('supportingAgentIds' in b) out.supporting_agent_ids = b.supportingAgentIds;
  if ('reviewState' in b) out.review_state = b.reviewState;
  return out;
}

function agentBody(b: any) {
  const out: Record<string, unknown> = {};
  for (const key of ['name', 'description', 'tag', 'avatar', 'instructions', 'context']) if (key in b) out[key] = b[key];
  if (b.addSkill) out.add_skill = b.addSkill;
  return out;
}

const COLLECTIONS: Record<string, string> = { artifacts: 'files', library: 'files' };
// Simulated inbound messages exist only in the development adapter.
const LATER = /^\/tenants\/[^/]+\/(channel-messages)(\/|$)/;

/** Plans one UI call. Unknown paths pass through unchanged (snake_case bodies are the caller's responsibility). */
export function plan(method: Method, path: string, body: any): Planned {
  const m = (pattern: RegExp) => pattern.exec(path);
  let match: RegExpExecArray | null;

  if (LATER.test(path)) {
    // The compose-a-test-message control belongs to the development adapter only.
    return method === 'GET' ? { method, path, out: identity, local: [] } : { method, path, out: identity, local: new Error('NOT_AVAILABLE') };
  }
  if (path === '/me') {
    return method === 'GET' ? { method, path, out: mapMe } : { method, path, body, out: mapMe };
  }
  if (path === '/me/preferences') return { method: 'PUT', path, body: { last_tenant_id: body.lastTenantId }, out: identity };
  if (path === '/me/tenants') return { method, path, out: (rows: any[]) => rows.map(mapTenant) };
  if (path === '/tenants' && method === 'POST') return { method, path, body, out: mapTenant };
  if ((match = m(/^\/tenants\/([^/]+)$/))) {
    if (method === 'GET') return { method, path, out: mapTenant };
    const { name, proactive, hideQuick, notificationsRead } = body || {};
    const patch: Record<string, unknown> = {};
    if (name !== undefined) patch.name = name;
    if (proactive !== undefined) patch.settings = { proactive };
    const preferences: Record<string, unknown> = {};
    if (hideQuick !== undefined) preferences.hideQuick = hideQuick;
    if (notificationsRead !== undefined) preferences.notificationsRead = notificationsRead;
    if (Object.keys(preferences).length) patch.preferences = preferences;
    return { method: 'PATCH', path, body: patch, out: () => null };
  }

  const t = (rest: string) => m(new RegExp(`^/tenants/([^/]+)/${rest}$`));

  if ((match = t('agents'))) return method === 'GET'
    ? { method, path, out: (rows: any[]) => rows.map(mapAgent) }
    : { method, path, body: agentBody(body), out: mapAgent };
  if ((match = t('agents/([^/]+)'))) return { method, path, body: method === 'PATCH' ? agentBody(body) : body, out: method === 'DELETE' ? identity : mapAgent };
  if ((match = t('shared-agents'))) return { method, path, out: identity };

  if ((match = t('tasks'))) return method === 'GET'
    ? { method, path, out: (rows: any[]) => rows.map(mapTask) }
    : { method, path, body: taskBody(body), out: mapTask };
  if ((match = t('tasks/([^/]+)'))) return { method, path, body: method === 'PATCH' ? taskPatch(body) : body, out: method === 'DELETE' ? identity : method === 'GET' ? mapTaskDetail : mapTask };
  if ((match = t('tasks/([^/]+)/events'))) return { method, path, out: (rows: any[]) => rows.map(e => ({ seq: e.seq, type: e.type, payload: e.payload, createdAt: e.created_at })) };
  if ((match = t('tasks/([^/]+)/approvals'))) return { method, path, out: (rows: any[]) => rows.map(mapApproval) };
  if ((match = t('tasks/([^/]+)/approvals/([^/]+)/decision'))) return { method, path, body, out: mapApproval };
  if ((match = t('tasks/([^/]+)/retry'))) return { method, path, out: identity };
  if ((match = t('tasks/([^/]+)/(messages|cancel)'))) return { method, path, body, out: mapTask };

  if ((match = t('projects'))) return method === 'GET'
    ? { method, path, out: (rows: any[]) => rows.map(mapProject) }
    : { method, path, body: { name: body.name, description: body.description || '', color: body.color }, out: mapProject };
  if ((match = t('projects/([^/]+)'))) {
    if (method === 'PATCH' && body && ('memberIds' in body || 'agentIds' in body)) {
      return { method: 'PUT', path: `${path}/roster`, body: { member_ids: body.memberIds || [], agent_ids: body.agentIds || [] }, out: mapProject };
    }
    const patch: Record<string, unknown> = {};
    if (body) for (const [key, value] of Object.entries(body)) patch[key === 'sharedContext' ? 'shared_context' : key] = value;
    return { method, path, body: method === 'PATCH' ? patch : body, out: method === 'DELETE' ? identity : mapProject };
  }

  if ((match = t('(artifacts|files)'))) return method === 'GET'
    ? { method, path: `/tenants/${match[1]}/files?include_content=true`, out: (rows: any[]) => rows.map(mapFile) }
    : { method, path: `/tenants/${match[1]}/files`, body, out: mapFile };
  if ((match = t('(artifacts|files)/([^/]+)'))) return { method, path: `/tenants/${match[1]}/files/${match[3]}`, body, out: method === 'DELETE' ? identity : mapFile };

  if ((match = t('automations'))) {
    if (method === 'GET') return { method, path, out: (rows: any[]) => rows.map(mapAutomation) };
    return {
      method, path, out: mapAutomation,
      body: {
        name: body.name, description: body.description, prompt: body.description,
        schedule: toCron(body.frequency, body.time), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
      },
    };
  }
  if ((match = t('automations/([^/]+)'))) return { method, path, body, out: method === 'DELETE' ? identity : mapAutomation };

  if ((match = t('scenarios'))) return method === 'GET'
    ? { method, path, out: (rows: any[]) => rows.map(mapScenario) }
    : { method, path, body, out: mapScenario };
  if ((match = t('scenarios/([^/]+)'))) return { method, path, body, out: method === 'DELETE' ? identity : mapScenario };

  if ((match = t('knowledge-sources'))) return method === 'GET'
    ? { method, path, out: (rows: any[]) => rows.map(mapKnowledgeSource) }
    : { method, path, body: { file_id: body.fileId }, out: mapKnowledgeSource };
  if ((match = t('agents/([^/]+)/knowledge'))) return { method, path, body: { source_ids: body.sourceIds || [] }, out: identity };

  if ((match = t('channel-bindings'))) {
    if (method === 'GET') return { method, path, out: (rows: any[]) => rows.map(mapBinding) };
    const fields = { name: body.name, agent_id: body.assignedAgent, capabilities: body.capabilities || [] };
    return body.id
      ? { method: 'PATCH', path: `${path}/${body.id}`, body: fields, out: mapBinding }
      : { method, path, body: { ...fields, platform: body.platform, method: METHOD_IN[body.method] || body.method, config: {} }, out: mapBinding };
  }
  if ((match = t('channel-bindings/([^/]+)/connection'))) {
    const params = body?.draft?.parameters || {};
    return { method, path, body: connectionBody(String(body?.platform || (params.corpId ? 'wecom' : 'feishu')), params), out: mapBinding };
  }
  if ((match = t('channel-bindings/([^/]+)/link-code'))) return { method, path, out: identity };
  if ((match = t('channel-bindings/([^/]+)'))) return { method, path, body, out: method === 'DELETE' ? identity : mapBinding };
  if ((match = t('channel-runs'))) return { method, path, out: (rows: any[]) => rows.map(mapChannelRun), forbiddenAs: [] };
  if ((match = t('channel-runs/([^/]+)/([a-z-]+)'))) return { method, path, out: identity };

  if ((match = t('connectors'))) return { method, path, out: identity };
  if ((match = t('connectors/([^/]+)/installation'))) return { method, path, body, out: identity };
  if ((match = t('connections'))) return method === 'GET'
    ? { method, path, out: (rows: any[]) => rows.map(mapConnection) }
    : {
      method, path, out: mapConnection,
      body: { connector_id: body.connectorId, name: body.name, scope: body.ownerScope === 'space' ? 'tenant' : 'member', secret: body.secret || null },
    };
  if ((match = t('connectors/([^/]+)/client-secret'))) return { method, path, body, out: () => null };
  if ((match = t('connections/([^/]+)/authorize'))) return { method, path, body, out: identity };
  if ((match = t('connections/([^/]+)/usage-policy'))) return {
    method, path, out: identity,
    // Bound workmates may use every tool of the connector; no workmates bound means nobody uses it (Part 6 §2 rule 3).
    body: (body.agentIds || []).map((id: string) => ({ principal_type: 'agent', principal_ref: id, allowed_tools: body.tools })),
  };
  if ((match = t('connections/([^/]+)'))) {
    const patch: Record<string, unknown> = {};
    if (body && 'name' in body) patch.name = body.name;
    if (body && 'enabled' in body) patch.status = body.enabled ? 'active' : 'suspended';
    return { method, path, body: method === 'PATCH' ? patch : undefined, out: method === 'DELETE' ? identity : mapConnection };
  }

  if ((match = t('members'))) return { method, path, out: (rows: any[]) => rows.map(mapMember) };
  if ((match = t('members/([^/]+)'))) {
    const patch: Record<string, unknown> = {};
    if (body?.role) patch.role = body.role;
    if (body?.status) patch.status = body.status === 'disabled' ? 'deactivated' : body.status;
    if (body?.name) patch.name = body.name;
    if (body && 'departmentId' in body) patch.department_id = body.departmentId || null;
    return { method, path, body: patch, out: mapMember };
  }
  if ((match = t('departments'))) return { method, path, body, out: (rows: any) => (Array.isArray(rows) ? rows.map(mapDepartment) : mapDepartment(rows)) };
  if ((match = t('invitations'))) return method === 'GET'
    ? { method, path, out: (rows: any[]) => rows.map(mapInvitation), forbiddenAs: [] }
    : { method, path, body: { emails: body.emails, role: body.role }, out: (rows: any[]) => rows.map(mapInvitation) };
  if ((match = t('invitations/([^/]+)/(accept|cancel)'))) {
    // Accepting happens through the emailed link (/invitations/accept); only cancel is a tenant action.
    return match[3] === 'cancel' ? { method, path, out: () => null } : { method, path, out: identity, local: new Error('NOT_AVAILABLE') };
  }
  if ((match = t('activity'))) return { method, path: `/tenants/${match[1]}/audit-events?limit=100`, out: mapActivity, forbiddenAs: [] };
  if ((match = t('resources/([^/]+)/([^/]+)/sharing'))) {
    const collection = COLLECTIONS[match[2]] || match[2];
    return {
      method, path: `/tenants/${match[1]}/resources/${collection}/${match[3]}/sharing`, out: identity,
      body: {
        visibility: body.visibility === 'space' ? 'organization' : body.visibility,
        member_ids: body.memberIds || [], project_id: body.projectId || null,
      },
    };
  }
  return { method, path, body, out: identity };
}
