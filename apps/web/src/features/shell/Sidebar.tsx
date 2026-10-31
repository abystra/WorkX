import { useWs, pathFor, type Page } from '@/app/workspace';
import { getLocale } from '@/i18n';
import { useUi } from '@/state/ui';
import { Icon, logoHtml } from '@/ui/icons';
import { IconButton, useOverlay } from '@/ui/overlay';
import { LanguageMenu, SidebarSettingsMenu, SpaceMenu, TaskMenu } from './menus';
import { NotificationsDrawer, ProactiveDialog, ProactiveFooter } from './dialogs';
import { SearchDialog } from './SearchDialog';

type NavItem = [Page, string, string];

/** Main sidebar (prototype sidebar()). */
export function Sidebar() {
  const ctx = useWs();
  const { t, ws, page, routeId, me } = ctx;
  const overlay = useOverlay();
  const { collapsed, mobileOpen, set } = useUi();
  const groups: [string, NavItem[]][] = [
    ['workspace.work', [['home', 'home', 'Home'], ['inbox', 'chat', 'workspace.inbox'], ['new', 'edit', 'New Task'], ['projects', 'folder', 'workspace.projects'], ['library', 'library', 'Library']]],
    ['workspace.resources', [['hub', 'hub', 'Hub'], ['scenarios', 'grid', 'workspace.scenarios'], ['automations', 'bolt', 'Automations']]],
    ['workspace.manage', [['team', 'users', ctx.current.type === 'organization' ? 'spaces.manage' : 'spaces.workspaceSettings'], ['ecosystem', 'globe', 'workspace.ecosystem']]],
  ];
  const inert = collapsed || (innerWidth <= 680 && !mobileOpen);
  const tasks = ws.tasks.filter(task => !task.archived).sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned)).slice(0, 16);
  return (
    <aside className="sidebar" {...(inert ? { inert: '' } : {})}>
      <div className="brand">
        <button className="brand-logo" data-action="nav" data-page="home" aria-label={t('WorkX home')} onClick={() => ctx.nav('home')} dangerouslySetInnerHTML={logoHtml} />
        <div className="brand-word">WorkX</div>
        <div className="brand-actions">
          <IconButton action="global-search" icon="search" label={t('Search · ⌘K')} onClick={() => overlay.custom(<SearchDialog />, '#global-search')} />
          <IconButton action="collapse" icon="collapse" label={t('Collapse sidebar')} onClick={() => (innerWidth <= 680 ? set({ mobileOpen: false }) : set({ collapsed: true }))} />
        </div>
      </div>
      <div className="mode-switch" role="tablist" aria-label={t('Workspace mode')}>
        <button role="tab" aria-selected={page !== 'code'} className={page !== 'code' ? 'active' : ''} data-action="nav" data-page="home" onClick={() => ctx.nav('home')}><Icon name="grid" size={12} />{t('Work')}</button>
        <button role="tab" aria-selected={page === 'code'} className={page === 'code' ? 'active' : ''} data-action="nav" data-page="code" onClick={() => ctx.nav('code')}><Icon name="code" size={13} />{t('Code')}</button>
      </div>
      <nav className="main-nav" aria-label={t('Main navigation')}>
        {groups.map(([group, items]) => [
          <div className="nav-group-label" key={group}>{t(group)}</div>,
          ...items.map(([target, ic, label]) => {
            const selected = page === target || (target === 'projects' && page === 'project');
            return (
              <a key={target} href={pathFor(ctx.tenantId, target)} className={`nav-item ${selected ? 'active' : ''}`} data-action="nav" data-page={target} aria-current={selected ? 'page' : undefined}
                onClick={e => { e.preventDefault(); ctx.nav(target); }}>
                <Icon name={ic} size={17} /><span>{t(label)}</span>
                {target === 'scenarios' ? <small className="nav-reserved">{t('workspace.reserved')}</small> : null}
              </a>
            );
          }),
        ])}
      </nav>
      <section className="sidebar-tasks">
        <div className="sidebar-label">
          <button data-action="nav" data-page="home" onClick={() => ctx.nav('home')}>{t('Tasks')}</button>
          <IconButton action="sidebar-settings" icon="settings" label={t('Task list settings')} onClick={e => overlay.popover(e.currentTarget, <SidebarSettingsMenu />)} />
        </div>
        {tasks.map(task => (
          <div key={task.id} className={`sidebar-task ${page === 'task' && routeId === task.id ? 'current' : ''}`}>
            <button className="task-title" title={task.name} data-action="open-task" data-id={task.id} onClick={() => ctx.nav('task', task.id)}>
              {task.pinned ? <><Icon name="star" size={12} />{' '}</> : null}{task.name}
            </button>
            {task.unread ? <span className="dot" /> : null}
            <IconButton action="task-menu" icon="more" label={t('ui.moreTask', { name: task.name })} data-id={task.id} onClick={e => overlay.popover(e.currentTarget, <TaskMenu taskId={task.id} />)} />
          </div>
        ))}
      </section>
      <div className="sidebar-language">
        <button className="language-trigger" data-action="language-menu" aria-label={t('language.choose')} aria-haspopup="menu" aria-expanded={overlay.current?.kind === 'popover' && overlay.current.anchor.dataset.action === 'language-menu'}
          onClick={e => overlay.popover(e.currentTarget, <LanguageMenu />)}>
          <Icon name="globe" size={16} /><span>{getLocale() === 'en' ? 'English' : '中文'}</span><small>{t('language.label')}</small><Icon name="chevron" size={11} />
        </button>
      </div>
      <div className="sidebar-footer">
        <button className="profile-btn" data-action="profile" onClick={e => overlay.popover(e.currentTarget, <SpaceMenu />)}>
          <span className="profile-avatar">{me.user.name.slice(0, 1).toUpperCase()}</span>
          <span className="ws-profile-copy"><strong>{ctx.spaceName()}</strong><small>{t('spaces.' + ctx.current.type)}</small></span>
          <Icon name="chevron" size={11} />
        </button>
        <IconButton action="proactive" icon="moon" label={t('Proactive help')} onClick={() => overlay.modal(t('Proactive help'), <ProactiveDialog />, <ProactiveFooter />)} />
        <button className="icon-btn notice-btn" data-action="notifications" aria-label={t('Notifications')} onClick={() => overlay.custom(<NotificationsDrawer />)}>
          <Icon name="bell" size={18} />
          {!ws.tenant.settings.notificationsRead ? <span className="notice-badge">1</span> : null}
        </button>
      </div>
    </aside>
  );
}

/** Current workspace bar above page content (prototype renderSpaceContext). */
export function SpaceContext() {
  const ctx = useWs();
  const { t } = ctx;
  const overlay = useOverlay();
  return (
    <div className="ws-context">
      <button data-action="profile" aria-label={t('spaces.switch')} onClick={e => overlay.popover(e.currentTarget, <SpaceMenu />)}>
        <span className={`ws-mark ${ctx.current.type === 'organization' ? 'is-org' : ''} is-tiny`}>{ctx.current.type === 'personal' ? <Icon name="users" size={18} /> : ctx.current.name.slice(0, 1).toUpperCase()}</span>
        <strong>{ctx.spaceName()}</strong><span>{t('spaces.' + ctx.current.type)}</span><Icon name="chevron" size={11} />
      </button>
      <button className="ws-context-data" data-action="nav" data-page="team" data-id="data" onClick={() => ctx.nav('team', 'data')}>
        <Icon name="layers" size={13} /><span>{t('spaces.contextHint')}</span>
      </button>
    </div>
  );
}
