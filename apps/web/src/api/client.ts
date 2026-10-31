import type {
  ModelOption, ActivityEvent, Agent, Artifact, Automation, ChannelRun, CollectionName, Connection, EcosystemBinding, Invitation, Me,
  KnowledgeSource, Member, Project, ScenarioDraft, Task, TenantDetail, TenantSummary,
} from './contracts';
import type { Transport } from './transport';

let transport: Transport | null = null;

/**
 * Selects the backend at startup. `VITE_API_MODE=http` (production) uses the FastAPI control plane.
 * Any other mode loads the development adapter through a dynamic import, so production bundles never
 * contain it. Test seeding is registered only when VITE_ENABLE_TEST_SEED is 'true'.
 */
export async function initTransport(): Promise<Transport> {
  if (import.meta.env.VITE_API_MODE === 'http') {
    const { HttpTransport } = await import('./http-transport');
    transport = new HttpTransport();
  } else {
    const { DevBackend } = await import('@/dev-backend/backend');
    const backend = new DevBackend();
    if (import.meta.env.VITE_ENABLE_TEST_SEED === 'true') {
      const { registerTestRoutes } = await import('@/dev-backend/test-seed');
      registerTestRoutes(backend);
    }
    transport = backend;
  }
  return transport;
}

export function getTransport(): Transport {
  if (!transport) throw new Error('Transport not initialised');
  return transport;
}

const req = <T>(method: Parameters<Transport['request']>[0], path: string, body?: unknown) => getTransport().request<T>(method, path, body);
const t = (tenantId: string) => `/tenants/${encodeURIComponent(tenantId)}`;

type CollectionTypes = { agents: Agent; tasks: Task; projects: Project; artifacts: Artifact; automations: Automation; scenarios: ScenarioDraft };

export const api = {
  me: () => req<Me>('GET', '/me'),
  models: () => req<ModelOption[]>('GET', '/models'),
  updateMe: (patch: { name?: string; notifications?: boolean }) => req<Me>('PATCH', '/me', patch),
  setLastTenant: (lastTenantId: string) => req<null>('PUT', '/me/preferences', { lastTenantId }),
  tenants: () => req<TenantSummary[]>('GET', '/me/tenants'),
  createTenant: (name: string) => req<TenantSummary>('POST', '/tenants', { name }),
  tenant: (tenantId: string) => req<TenantDetail>('GET', t(tenantId)),
  updateTenant: (tenantId: string, patch: Partial<{ name: string; hideQuick: boolean; proactive: boolean; notificationsRead: boolean }>) => req<null>('PATCH', t(tenantId), patch),

  list: <C extends CollectionName>(tenantId: string, collection: C) => req<CollectionTypes[C][]>('GET', `${t(tenantId)}/${collection}`),
  create: <C extends CollectionName>(tenantId: string, collection: C, body: Record<string, unknown>) => req<CollectionTypes[C]>('POST', `${t(tenantId)}/${collection}`, body),
  update: <C extends CollectionName>(tenantId: string, collection: C, id: string, patch: Record<string, unknown>) => req<CollectionTypes[C]>('PATCH', `${t(tenantId)}/${collection}/${encodeURIComponent(id)}`, patch),

  sendMessage: (tenantId: string, taskId: string, prompt: string) => req<Task>('POST', `${t(tenantId)}/tasks/${encodeURIComponent(taskId)}/messages`, { prompt }),

  members: (tenantId: string) => req<Member[]>('GET', `${t(tenantId)}/members`),
  updateMember: (tenantId: string, id: string, patch: Record<string, unknown>) => req<Member>('PATCH', `${t(tenantId)}/members/${encodeURIComponent(id)}`, patch),
  sharedAgentIds: (tenantId: string) => req<string[]>('GET', `${t(tenantId)}/shared-agents`),
  invitations: (tenantId: string) => req<Invitation[]>('GET', `${t(tenantId)}/invitations`),
  invite: (tenantId: string, emails: string, role: string) => req<Invitation[]>('POST', `${t(tenantId)}/invitations`, { emails, role }),
  /** Global (not tenant-scoped): accepts an emailed invitation for the signed-in user (J2). */
  acceptInvitation: (token: string) => req<{ tenant_id: string }>('POST', '/invitations/accept', { token }),
  transitionInvitation: (tenantId: string, id: string, action: 'accept' | 'cancel') => req<null>('POST', `${t(tenantId)}/invitations/${encodeURIComponent(id)}/${action}`),
  connections: (tenantId: string) => req<Connection[]>('GET', `${t(tenantId)}/connections`),
  createConnection: (tenantId: string, body: Record<string, unknown>) => req<Connection>('POST', `${t(tenantId)}/connections`, body),
  updateConnection: (tenantId: string, id: string, patch: Record<string, unknown>) => req<Connection>('PATCH', `${t(tenantId)}/connections/${encodeURIComponent(id)}`, patch),
  setSharing: (tenantId: string, collection: string, id: string, body: Record<string, unknown>) => req<unknown>('PUT', `${t(tenantId)}/resources/${collection}/${encodeURIComponent(id)}/sharing`, body),
  activity: (tenantId: string) => req<ActivityEvent[]>('GET', `${t(tenantId)}/activity`),
  departments: (tenantId: string) => req<{ id: string; name: string; parentId?: string }[]>('GET', `${t(tenantId)}/departments`),
  channelRuns: (tenantId: string) => req<ChannelRun[]>('GET', `${t(tenantId)}/channel-runs`),
  knowledgeSources: (tenantId: string) => req<KnowledgeSource[]>('GET', `${t(tenantId)}/knowledge-sources`),
  /** Makes a Library file a knowledge source (idempotent per file) and starts ingestion. */
  createKnowledgeSource: (tenantId: string, fileId: string) => req<KnowledgeSource>('POST', `${t(tenantId)}/knowledge-sources`, { fileId }),
  /** Replaces the knowledge sources attached to a workmate. */
  setAgentKnowledge: (tenantId: string, agentId: string, sourceIds: string[]) => req<Agent>('PUT', `${t(tenantId)}/agents/${encodeURIComponent(agentId)}/knowledge`, { sourceIds }),
  channelBindings: (tenantId: string) => req<EcosystemBinding[]>('GET', `${t(tenantId)}/channel-bindings`),

  /** Generic call for adapter-specific actions (channels, ecosystem); typed at the call site. */
  call: <T>(method: Parameters<Transport['request']>[0], path: string, body?: unknown) => req<T>(method, path, body),
};

/** Only same-origin relative paths may be used as a post-login destination (no open redirects). */
export function safeReturnTo(value: string | null | undefined): string {
  return value && value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/\\') ? value : '/';
}

/** Server-side OIDC entry point (Part 9 §3): the API redirects to Keycloak and sets the session cookie. */
export function authLoginUrl(intent: 'login' | 'signup', returnTo: string): string {
  return `/api/v1/auth/login?intent=${intent}&return_to=${encodeURIComponent(safeReturnTo(returnTo))}`;
}
