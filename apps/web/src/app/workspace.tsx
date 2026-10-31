import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { api, getTransport } from '@/api/client';
import type { Me, RuntimeInfo, TenantSummary } from '@/api/contracts';
import { useMe, useRefresh, useTenants, useWorkspace, type Workspace } from '@/api/hooks';
import { getLocale, useT, type TFn } from '@/i18n';
import { useUi } from '@/state/ui';
import { useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { LoadError } from './states';

export type Page =
  | 'home' | 'new' | 'detail' | 'task' | 'automations' | 'projects' | 'project' | 'library' | 'hub' | 'code'
  | 'ecosystem' | 'scenarios' | 'team' | 'settings' | 'inbox';

export const PAGES: Page[] = ['home', 'new', 'detail', 'task', 'automations', 'projects', 'project', 'library', 'hub', 'code', 'ecosystem', 'scenarios', 'team', 'settings', 'inbox'];

export interface WorkspaceCtx {
  tenantId: string;
  ws: Workspace;
  me: Me;
  tenants: TenantSummary[];
  current: TenantSummary;
  runtime: RuntimeInfo;
  page: Page;
  routeId?: string;
  t: TFn;
  /** Name shown for a workspace ("Personal workspace" for the personal tenant). */
  spaceName: (space?: TenantSummary) => string;
  canManage: boolean;
  nav: (page: Page, id?: string) => void;
  switchWorkspace: (id: string, options?: { page?: Page; tab?: string; notice?: string; space?: TenantSummary }) => void;
  refresh: () => Promise<unknown>;
  /** Runs a mutation, refreshes the workspace, and shows the error key as a toast on failure. */
  run: <T>(work: () => Promise<T>, success?: string) => Promise<T | undefined>;
}

const Ctx = createContext<WorkspaceCtx | null>(null);
export const useWs = () => useContext(Ctx)!;

export function pathFor(tenantId: string, page: Page, id?: string): string {
  if (page === 'settings') return `/settings/${id || 'general'}`;
  if (page === 'team') return `/t/${tenantId}/team/${id || 'general'}`;
  if (['detail', 'task', 'project', 'new'].includes(page) && id) return `/t/${tenantId}/${page}/${id}`;
  return `/t/${tenantId}/${page}`;
}

/** Loads workspace data for `tenantId` and provides navigation with the prototype's semantics. */
export function WorkspaceProvider({ tenantId, page, routeId, children }: { tenantId?: string; page: Page; routeId?: string; children: ReactNode }) {
  const t = useT();
  const me = useMe();
  const tenants = useTenants();
  const resolvedId = tenantId || me.data?.lastTenantId;
  const { ws, error } = useWorkspace(resolvedId);
  const refresh = useRefresh();
  const navigate = useNavigate();
  const overlay = useOverlay();
  const toast = useToast();
  const ui = useUi();

  // Tenant event stream: refresh lists, mark read when viewing, notify on completion (prototype startTask timer).
  useEffect(() => {
    if (!resolvedId) return;
    return getTransport().subscribe(resolvedId, event => {
      void (async () => {
        if (event.type === 'task.succeeded') {
          const taskId = String(event.payload.task_id);
          const viewing = window.location.pathname === `/t/${resolvedId}/task/${taskId}`;
          if (viewing) await api.update(resolvedId, 'tasks', taskId, { unread: false });
          await refresh(resolvedId);
          if (me.data?.user.notifications && !viewing) toast(t('智能伙伴已完成演示任务'));
        } else {
          await refresh(resolvedId);
        }
      })();
    });
  }, [resolvedId, me.data?.user.notifications]); // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo<WorkspaceCtx | null>(() => {
    if (!ws || !me.data || !tenants.data || !resolvedId) return null;
    const current = tenants.data.find(x => x.id === resolvedId)!;
    const spaceName = (space = current) => (space.type === 'personal' ? t('spaces.personal') : space.name);
    const canManage = current.type === 'organization' && ws.members.some(m => m.id === 'm1' && m.status === 'active' && ['owner', 'admin'].includes(m.role));
    const nav: WorkspaceCtx['nav'] = (target, id) => {
      overlay.close();
      ui.set({
        query: '', filter: 'all', listTab: 'tasks', mobileOpen: false,
        ...(target === 'detail' ? { detailTab: 'Instructions' } : {}),
        ...(target === 'project' ? { projectTab: 'tasks' } : {}),
      });
      if (target === 'new' && id) ui.setDrafts(resolvedId, { agent: id });
      if (target === 'task' && id && ws.tasks.find(x => x.id === id)?.unread) {
        void api.update(resolvedId, 'tasks', id, { unread: false }).then(() => refresh(resolvedId));
      }
      void navigate({ to: pathFor(resolvedId, target, id) });
      window.scrollTo(0, 0);
    };
    const switchWorkspace: WorkspaceCtx['switchWorkspace'] = (id, options = {}) => {
      const next = options.space || tenants.data!.find(x => x.id === id);
      if (!next) return;
      overlay.close();
      ui.set({ query: '', secondaryQuery: '', filter: 'all', listTab: 'tasks', libraryFilter: 'all', hubFilter: 'all', detailTab: 'Instructions', resourceTab: 'projects', projectTab: 'tasks', channelFilter: 'all', mobileOpen: false });
      void api.setLastTenant(id).then(() => refresh());
      const target = options.page || 'home';
      void navigate({ to: pathFor(id, target, target === 'team' ? options.tab || 'general' : undefined) });
      window.scrollTo(0, 0);
      toast(options.notice ? t(options.notice) : t('spaces.switched', { name: spaceName(next) }));
    };
    const run: WorkspaceCtx['run'] = async (work, success) => {
      try {
        const result = await work();
        await refresh(resolvedId);
        if (success) toast(t(success));
        return result;
      } catch (e) {
        await refresh(resolvedId);
        const code = (e as { code?: string }).code;
        toast(code && code !== 'INTERNAL' && code !== 'VALIDATION_FAILED' ? t(code) : t('web.requestFailed'));
        return undefined;
      }
    };
    return {
      tenantId: resolvedId, ws, me: me.data, tenants: tenants.data, current, runtime: getTransport().runtime, page, routeId, t,
      spaceName, canManage, nav, switchWorkspace, refresh: () => refresh(resolvedId), run,
    };
  }, [ws, me.data, tenants.data, resolvedId, page, routeId, t, getLocale()]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error || me.error || tenants.error) return <LoadError onRetry={() => void refresh(resolvedId)} />;
  if (!value) return null;
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
