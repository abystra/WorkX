import { api } from '@/api/client';
import type { TenantSummary } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { getLocale, setLocale } from '@/i18n';
import { Avatar, Icon } from '@/ui/icons';
import { MenuItem, useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { useUi } from '@/state/ui';
import { AboutDialog, HelpDialog, ShortcutsDialog } from './dialogs';
import { CreateAgentDialog } from '@/features/agents/AgentDialogs';
import { RenameTaskDialog } from '@/features/tasks/TaskDialogs';
import { CreateOrganizationDialog, InviteDialog } from '@/features/settings/SpaceDialogs';
import { SearchDialog } from './SearchDialog';

/** ws-mark: personal shows the users icon, organizations their initial. */
export function SpaceMark({ space, size = '' }: { space: TenantSummary; size?: string }) {
  return (
    <span className={`ws-mark ${space.type === 'organization' ? 'is-org' : ''} ${size}`}>
      {space.type === 'personal' ? <Icon name="users" size={18} /> : space.name.slice(0, 1).toUpperCase()}
    </span>
  );
}

/** Account menu (prototype renderSpaceMenu). */
export function SpaceMenu() {
  const ctx = useWs();
  const { t, me, tenants, current, ws } = ctx;
  const overlay = useOverlay();
  const run = (fn: () => void) => () => { overlay.close(); fn(); };
  const extra: [string, string, string, () => void][] = [
    ['help', 'help', 'Getting started', () => overlay.modal(t('Your work, with a little help.'), <HelpDialog />, <HelpFooter />)],
    ...(ws.tenant.settings.hideQuick ? [['restore-quick', 'grid', 'Show Quick start', () => void restoreQuick(ctx)] as [string, string, string, () => void]] : []),
    ['shortcuts', 'keyboard', 'Keyboard shortcuts', () => overlay.modal(t('Keyboard shortcuts'), <ShortcutsDialog />)],
    ['about', 'book', 'About this prototype', () => overlay.modal(t('About WorkX'), <AboutDialog />)],
  ];
  return (
    <div className="ws-menu">
      <div className="ws-menu-account"><strong>{me.user.name}</strong><small>{me.user.email}</small></div>
      <div className="menu-caption">{t('spaces.switch')}</div>
      {tenants.map(space => (
        <button key={space.id} className="menu-item ws-switch-item" role="menuitemradio" aria-checked={current.id === space.id} data-action="space-switch" data-id={space.id} onClick={() => ctx.switchWorkspace(space.id)}>
          <SpaceMark space={space} />
          <span><strong>{ctx.spaceName(space)}</strong><small>{t(space.type === 'personal' ? 'spaces.scope.private' : 'spaces.organization')}</small></span>
          {space.id === current.id ? <Icon name="check" size={16} /> : null}
        </button>
      ))}
      <button className="menu-item" data-action="space-create" onClick={() => overlay.modal(t('spaces.create'), <CreateOrganizationDialog />, <CreateOrganizationDialog.Footer />, { className: 'ws-dialog' })}>
        <Icon name="plus" size={17} /><span>{t('spaces.create')}</span>
      </button>
      <div className="menu-separator" />
      {current.type === 'organization' && ctx.canManage ? (
        <>
          <button className="menu-item" data-action="space-invite" onClick={() => overlay.modal(t('spaces.invite'), <InviteDialog />, <InviteDialog.Footer />, { className: 'ws-dialog' })}>
            <Icon name="users" size={17} /><span>{t('spaces.invite')}</span>
          </button>
          <button className="menu-item" data-action="nav" data-page="team" data-id="general" onClick={run(() => ctx.nav('team', 'general'))}>
            <Icon name="settings" size={17} /><span>{t('spaces.manage')}</span>
          </button>
        </>
      ) : (
        <button className="menu-item" data-action="nav" data-page="team" data-id="data" onClick={run(() => ctx.nav('team', 'data'))}>
          <Icon name="folder" size={17} /><span>{t('spaces.data')}</span>
        </button>
      )}
      <button className="menu-item" data-action="nav" data-page="settings" data-id="general" onClick={run(() => ctx.nav('settings', 'general'))}>
        <Icon name="settings" size={17} /><span>{t('spaces.settings')}</span>
      </button>
      <div className="menu-separator" />
      {extra.map(([action, ic, label, fn]) => (
        <button key={action} className="menu-item" data-action={action} onClick={() => { overlay.close(); fn(); }}>
          <Icon name={ic} size={17} /><span>{t(label)}</span>
        </button>
      ))}
    </div>
  );
}

function HelpFooter() {
  const { t, nav } = useWs();
  return <button className="btn primary" data-action="nav" data-page="new" onClick={() => nav('new')}><Icon name="arrow" size={16} />{t('Start a task')}</button>;
}

export async function restoreQuick(ctx: ReturnType<typeof useWs>) {
  await ctx.run(() => api.updateTenant(ctx.tenantId, { hideQuick: false }), '已恢复 Quick start');
  ctx.nav('home');
}

export function LanguageMenu() {
  const { t } = useWs();
  const overlay = useOverlay();
  const toast = useToast();
  return (
    <>
      <div className="menu-caption">{t('language.choose')}</div>
      {[['zh-CN', '中文'], ['en', 'English']].map(([locale, label]) => (
        <button key={locale} className="menu-item" role="menuitemradio" aria-checked={getLocale() === locale} data-action="set-language" data-locale={locale}
          onClick={() => {
            const y = window.scrollY;
            if (!setLocale(locale)) return;
            overlay.close();
            window.scrollTo(0, y);
            (document.querySelector('[data-action="language-menu"]') as HTMLElement | null)?.focus({ preventScroll: true });
            toast(t('language.changed'));
          }}>
          <span lang={locale}>{label}</span>
          {getLocale() === locale ? <span className="menu-check"><Icon name="check" size={14} /></span> : null}
        </button>
      ))}
    </>
  );
}

export function CreateMenu() {
  const { t } = useWs();
  const overlay = useOverlay();
  const open = (squad: boolean) => overlay.modal(t(squad ? 'Create a squad' : 'Create a Workmate'), <CreateAgentDialog squad={squad} />, <CreateAgentDialog.Footer />, { focus: '#agent-form input' });
  return (
    <>
      <MenuItem action="create-agent" label={t('Create a Workmate')} icon="users" onClick={() => open(false)} />
      <MenuItem action="create-squad" label={t('Create a squad')} icon="layers" onClick={() => open(true)} />
    </>
  );
}

export function TaskMenu({ taskId }: { taskId: string }) {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const task = ws.tasks.find(x => x.id === taskId);
  if (!task) return null;
  const toggle = async (field: 'pinned' | 'archived') => {
    overlay.close();
    const next = !task[field];
    await ctx.run(() => api.update(ctx.tenantId, 'tasks', task.id, { [field]: next }),
      field === 'pinned' ? (next ? '任务已置顶' : '已取消置顶') : (next ? '任务已归档，可在筛选中恢复' : '任务已恢复'));
  };
  return (
    <>
      <MenuItem action="pin-task" data-id={task.id} label={task.pinned ? t('Unpin task') : t('Pin task')} icon="star" onClick={() => void toggle('pinned')} />
      <MenuItem action="rename-task" data-id={task.id} label={t('Rename')} icon="edit" onClick={() => overlay.modal(t('Rename task'), <RenameTaskDialog task={task} />, <RenameTaskDialog.Footer taskId={task.id} />)} />
      <MenuItem action="archive-task" data-id={task.id} label={task.archived ? t('Restore task') : t('Archive task')} icon="folder" onClick={() => void toggle('archived')} />
    </>
  );
}

export function FilterMenu() {
  const { t } = useWs();
  const overlay = useOverlay();
  const { filter, set } = useUi();
  return (
    <>
      <div className="menu-caption">{t('Show tasks')}</div>
      {[['all', 'All tasks'], ['unread', 'Unread'], ['pinned', 'Pinned'], ['done', 'Completed'], ['archived', 'Archived']].map(([value, label]) => (
        <MenuItem key={value} action="set-filter" data-value={value} label={t(label)} checked={filter === value} onClick={() => { set({ filter: value }); overlay.close(); }} />
      ))}
    </>
  );
}

export function SidebarSettingsMenu() {
  const ctx = useWs();
  const { t } = ctx;
  const overlay = useOverlay();
  const { set } = useUi();
  const show = (filter: string) => {
    ctx.nav('home');
    set({ filter });
    setTimeout(() => document.querySelector('.task-section')?.scrollIntoView({ behavior: 'smooth' }), 0);
  };
  return (
    <>
      <MenuItem action="show-unread" label={t('Unread tasks')} icon="bell" onClick={() => show('unread')} />
      <MenuItem action="show-archived" label={t('Archived tasks')} icon="folder" onClick={() => show('archived')} />
      <MenuItem action="global-search" label={t('Search tasks')} icon="search" onClick={() => overlay.custom(<SearchDialog />, '#global-search')} />
      <MenuItem action="restore-quick" label={t('Show Quick start')} icon="grid" onClick={() => { overlay.close(); void restoreQuick(ctx); }} />
    </>
  );
}

/** Workmate picker (prototype select-agent). */
export function AgentMenu() {
  const { t, ws, tenantId } = useWs();
  const overlay = useOverlay();
  const drafts = useUi(s => s.drafts[tenantId]);
  const setDrafts = useUi(s => s.setDrafts);
  const currentAgent = drafts?.agent || ws.agents[0]?.id;
  return (
    <>
      <div className="menu-caption">{t('Choose a workmate')}</div>
      {ws.agents.map(agent => (
        <button key={agent.id} className="menu-item" data-action="choose-agent" data-id={agent.id} onClick={() => { setDrafts(tenantId, { agent: agent.id }); overlay.close(); }}>
          <Avatar index={agent.avatar} size={26} />
          <span>{agent.name}</span>
          {agent.id === currentAgent ? <span className="menu-check"><Icon name="check" size={14} /></span> : null}
        </button>
      ))}
    </>
  );
}
