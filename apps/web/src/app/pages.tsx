import type { WorkspaceCtx } from './workspace';
import { useWs } from './workspace';
import { NotFound } from './states';
import { Home } from '@/features/home/Home';
import { Settings } from '@/features/settings/Settings';

/** Document title per page (prototype render()). */
export function pageTitle(ctx: WorkspaceCtx): string {
  const { t, page, ws, routeId } = ctx;
  if (page === 'detail') return (ws.agents.find(a => a.id === routeId) || ws.agents[0])?.name || 'WorkX';
  if (page === 'task') return ws.tasks.find(x => x.id === routeId)?.name || t('Home');
  const keys: Record<string, string> = {
    home: 'Home', new: 'New Task', automations: 'Automations', projects: 'Projects', library: 'Library', hub: 'Hub', code: 'Code',
    project: 'Project', ecosystem: 'workspace.ecosystem', scenarios: 'workspace.scenarios',
    team: ctx.current.type === 'organization' ? 'spaces.manage' : 'spaces.workspaceSettings', settings: 'spaces.settings', inbox: 'workspace.inbox',
  };
  return t(keys[page] || 'Home');
}

/** Page switch (prototype render() content selection). Screens are added stage by stage. */
export function PageSwitch() {
  const ctx = useWs();
  switch (ctx.page) {
    case 'home':
      return <Home />;
    case 'team':
    case 'settings':
      return <Settings />;
    default:
      return <NotFound onHome={() => ctx.nav('home')} />;
  }
}
