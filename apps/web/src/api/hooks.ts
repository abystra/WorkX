import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  ActivityEvent, Agent, Artifact, Automation, ChannelRun, Connection, EcosystemBinding, Invitation, Member, Project,
  ScenarioDraft, Task, TenantDetail,
} from './contracts';

export const tenantKey = (tenantId: string) => ['t', tenantId] as const;

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: api.me });
}

export function useTenants() {
  return useQuery({ queryKey: ['tenants'], queryFn: api.tenants });
}

/** Everything a workspace screen renders, loaded per tenant. `ws` is undefined until all parts arrive. */
export interface Workspace {
  tenantId: string;
  tenant: TenantDetail;
  agents: Agent[];
  tasks: Task[];
  projects: Project[];
  library: Artifact[];
  automations: Automation[];
  members: Member[];
  sharedAgentIds: string[];
  invitations: Invitation[];
  connections: Connection[];
  activity: ActivityEvent[];
  departments: { id: string; name: string; parentId?: string }[];
  channelRuns: ChannelRun[];
  bindings: EcosystemBinding[];
  scenarios: ScenarioDraft[];
}

const parts = {
  tenant: api.tenant,
  agents: (t: string) => api.list(t, 'agents'),
  tasks: (t: string) => api.list(t, 'tasks'),
  projects: (t: string) => api.list(t, 'projects'),
  library: (t: string) => api.list(t, 'artifacts'),
  automations: (t: string) => api.list(t, 'automations'),
  scenarios: (t: string) => api.list(t, 'scenarios'),
  members: api.members,
  sharedAgentIds: api.sharedAgentIds,
  invitations: api.invitations,
  connections: api.connections,
  activity: api.activity,
  departments: api.departments,
  channelRuns: api.channelRuns,
  bindings: api.channelBindings,
} as const;
const names = Object.keys(parts) as (keyof typeof parts)[];

export function useWorkspace(tenantId: string | undefined): { ws?: Workspace; error?: unknown; loading: boolean } {
  const results = useQueries({
    queries: names.map(name => ({
      queryKey: [...tenantKey(tenantId || ''), name],
      queryFn: () => (parts[name] as (t: string) => Promise<unknown>)(tenantId!),
      enabled: !!tenantId,
    })),
  });
  const error = results.find(r => r.error)?.error;
  if (!tenantId || results.some(r => r.data === undefined)) return { error, loading: !error };
  const ws = Object.fromEntries(names.map((name, i) => [name, results[i].data])) as unknown as Workspace;
  ws.tenantId = tenantId;
  // Same derivation the prototype performs on every render.
  ws.projects = ws.projects.map(p => ({ ...p, tasks: ws.tasks.filter(task => task.project === p.id && !task.archived).length }));
  return { ws, loading: false };
}

/** Refetch everything for a tenant (and the tenant list) after a mutation or a server event. */
export function useRefresh() {
  const client = useQueryClient();
  return (tenantId?: string) => Promise.all([
    tenantId ? client.invalidateQueries({ queryKey: tenantKey(tenantId) }) : client.invalidateQueries({ queryKey: ['t'] }),
    client.invalidateQueries({ queryKey: ['tenants'] }),
    client.invalidateQueries({ queryKey: ['me'] }),
  ]);
}
