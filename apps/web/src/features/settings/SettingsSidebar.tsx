import { useWs, pathFor, type Page } from '@/app/workspace';
import { SpaceMark, SpaceMenu } from '@/features/shell/menus';
import { Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';

/** Sidebar for personal settings and workspace administration (prototype renderSettingsSidebar). */
export function SettingsSidebar() {
  const ctx = useWs();
  const { t, page, routeId, current, me } = ctx;
  const overlay = useOverlay();
  const personal = page === 'settings';
  const isOrg = current.type === 'organization';
  const tab = routeId || 'general';
  const groups: [string, [string, string, string][]][] = personal
    ? [['spaces.account', [['general', 'settings', 'spaces.general'], ['profile', 'users', 'spaces.profile'], ['spaces', 'layers', 'spaces.mySpaces']]]]
    : [
        ['spaces.general', [['general', 'settings', 'spaces.workspaceSettings']]],
        ['spaces.identity', isOrg ? [['members', 'users', 'spaces.members'], ['permissions', 'layers', 'spaces.permissions']] : []],
        ['spaces.governance', [['data', 'folder', 'spaces.data'], ['connections', 'globe', 'spaces.integrations'], ['usage', 'grid', 'spaces.usage'], ...(isOrg ? [['activity', 'clock', 'spaces.activity'] as [string, string, string]] : [])]],
      ];
  const target: Page = personal ? 'settings' : 'team';
  return (
    <aside className="sidebar ws-settings-sidebar">
      <button className="ws-back" data-action="nav" data-page="home" onClick={() => ctx.nav('home')}><Icon name="arrow" size={16} />{t('spaces.back')}</button>
      <h2>{t(personal ? 'spaces.settings' : isOrg ? 'spaces.manage' : 'spaces.workspaceSettings')}</h2>
      {!personal ? (
        <button className="ws-settings-selector" data-action="profile" aria-label={t('spaces.switch')} onClick={e => overlay.popover(e.currentTarget, <SpaceMenu />)}>
          <SpaceMark space={current} /><span>{ctx.spaceName()}</span><Icon name="chevron" size={12} />
        </button>
      ) : (
        <div className="ws-settings-account"><span className="profile-avatar">{me.user.name.slice(0, 1).toUpperCase()}</span><span>{me.user.name}</span></div>
      )}
      <nav aria-label={t(personal ? 'spaces.settings' : 'spaces.workspaceSettings')}>
        {groups.filter(([, items]) => items.length).map(([label, items]) => [
          <div className="ws-nav-label" key={label}>{t(label)}</div>,
          ...items.map(([id, ic, itemLabel]) => (
            <a key={id} className={`ws-nav-item ${tab === id ? 'is-active' : ''}`} href={pathFor(ctx.tenantId, target, id)} data-action="nav" data-page={target} data-id={id}
              aria-current={tab === id ? 'page' : undefined} onClick={e => { e.preventDefault(); ctx.nav(target, id); }}>
              <Icon name={ic} size={17} />{t(itemLabel)}
            </a>
          )),
        ])}
      </nav>
      <div className="ws-settings-bottom">
        <button data-action="profile" onClick={e => overlay.popover(e.currentTarget, <SpaceMenu />)}><SpaceMark space={current} size="is-tiny" /><span>{ctx.spaceName()}</span><Icon name="more" size={16} /></button>
        <button className="text-btn" data-action="nav" data-page={personal ? 'team' : 'settings'} data-id="general" onClick={() => ctx.nav(personal ? 'team' : 'settings', 'general')}>
          {t(personal ? (isOrg ? 'spaces.manage' : 'spaces.workspaceSettings') : 'spaces.settings')}
        </button>
      </div>
    </aside>
  );
}
