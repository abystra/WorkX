import type { ReactNode } from 'react';
import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { getLocale, setLocale } from '@/i18n';
import { useUi } from '@/state/ui';
import { Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { SpaceMark } from '@/features/shell/menus';
import { CreateOrganizationDialog, Field, InviteDialog, SpaceButton, readForm } from './SpaceDialogs';
import { AddConnectionDialog, ManageMemberDialog, SharingDialog } from './AdminDialogs';

const RESOURCE_COLLECTIONS = ['projects', 'tasks', 'library', 'agents', 'automations'] as const;
type ResourceCollection = (typeof RESOURCE_COLLECTIONS)[number];

const Section = ({ title, children, extra = '' }: { title?: ReactNode; children: ReactNode; extra?: string }) => (
  <section className={`ws-section ${extra}`}>{title ? <h2>{title}</h2> : null}{children}</section>
);
const Row = ({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) => (
  <div className="ws-setting-row"><div><strong>{label}</strong>{hint ? <p>{hint}</p> : null}</div><div>{value}</div></div>
);
const WsEmpty = ({ text, icon = 'folder' }: { text: string; icon?: string }) => <div className="ws-empty"><Icon name={icon} size={26} /><p>{text}</p></div>;

function useCreateOrg() {
  const { t } = useWs();
  const overlay = useOverlay();
  return () => overlay.modal(t('spaces.create'), <CreateOrganizationDialog />, <CreateOrganizationDialog.Footer />, { className: 'ws-dialog' });
}

function PersonalGeneral() {
  const ctx = useWs();
  const { t, me } = ctx;
  const toast = useToast();
  return (
    <Section title={t('spaces.general')}>
      <Row label={t('spaces.language')} hint={t('spaces.languageHint')} value={
        <select aria-label={t('spaces.language')} data-space-locale="" value={getLocale()} onChange={e => { if (setLocale(e.target.value)) toast(t('language.changed')); }}>
          <option value="zh-CN">中文</option><option value="en">English</option>
        </select>
      } />
      <Row label={t('spaces.notifications')} hint={t('spaces.notificationsHint')} value={
        <button className={`ws-toggle ${me.user.notifications ? 'is-on' : ''}`} role="switch" aria-checked={!!me.user.notifications} aria-label={t('spaces.notifications')} data-action="space-toggle-notifications"
          onClick={() => void ctx.run(() => api.updateMe({ notifications: !me.user.notifications }), 'spaces.saved')}><span /></button>
      } />
    </Section>
  );
}

function OrgGeneral() {
  const ctx = useWs();
  const { t, current } = ctx;
  const createOrg = useCreateOrg();
  const saveName = () => {
    const values = readForm('space-name-form', ctx.tenantId);
    if (!values) return;
    void ctx.run(() => api.updateTenant(ctx.tenantId, { name: String(values.get('name') || '') }), 'spaces.saved');
  };
  return (
    <>
      <Section>
        <div className="ws-org-identity"><SpaceMark space={current} size="is-large" /><div><h2>{ctx.spaceName()}</h2><span>{t('spaces.' + current.type)}</span></div></div>
        <Row label={t('spaces.spaceId')} value={<code>{current.id}</code>} />
        <Row label={t('spaces.spaceType')} value={t('spaces.' + current.type)} />
        <Row label={t('spaces.plan')} value={t('spaces.demoPlan')} />
        {ctx.canManage ? (
          <form id="space-name-form" data-tenant={current.id} onSubmit={e => e.preventDefault()} key={current.name}>
            <Field label={t('spaces.spaceName')}><input name="name" maxLength={80} required defaultValue={ctx.spaceName()} /></Field>
            <div className="ws-form-footer"><SpaceButton action="space-save-name" label={t('team.save')} primary onClick={saveName} /></div>
          </form>
        ) : null}
      </Section>
      <Section title={t('spaces.isolationTitle')}>
        <p className="ws-body-copy">{t('spaces.isolationHint')}</p>
        {current.type === 'personal' ? <div className="ws-callout"><p>{t('spaces.personalOnly')}</p><SpaceButton action="space-create" label={t('spaces.create')} onClick={createOrg} /></div> : null}
      </Section>
    </>
  );
}

function Profile() {
  const ctx = useWs();
  const { t, me } = ctx;
  const save = () => {
    const values = readForm('space-profile-form', ctx.tenantId);
    if (!values) return;
    void ctx.run(() => api.updateMe({ name: String(values.get('name') || '') }), 'spaces.saved');
  };
  return (
    <Section title={t('spaces.profile')}>
      <form id="space-profile-form" onSubmit={e => e.preventDefault()} key={me.user.name}>
        <Field label={t('spaces.displayName')}><input name="name" required maxLength={40} defaultValue={me.user.name} /></Field>
        <Field label={t('spaces.email')}><input type="email" value={me.user.email} readOnly /></Field>
        <p className="ws-body-copy">{t('spaces.accountHint')}</p>
        <div className="ws-form-footer"><SpaceButton action="space-save-profile" label={t('team.save')} primary onClick={save} /></div>
      </form>
    </Section>
  );
}

function MySpaces() {
  const ctx = useWs();
  const { t, tenants } = ctx;
  const createOrg = useCreateOrg();
  return (
    <Section>
      <div className="ws-space-list">
        {tenants.map(space => (
          <div key={space.id}>
            <SpaceMark space={space} />
            <div><strong>{ctx.spaceName(space)}</strong><small>{t('spaces.' + space.type)} · {space.role === 'owner' ? t('spaces.owner') : t('team.role.' + space.role)}</small></div>
            <SpaceButton action="space-switch" label={t('spaces.enter')} data-id={space.id} onClick={() => ctx.switchWorkspace(space.id)} />
          </div>
        ))}
      </div>
      <div className="ws-form-footer"><SpaceButton action="space-create" label={t('spaces.create')} primary onClick={createOrg} /></div>
    </Section>
  );
}

function Members() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const pending = ws.invitations.slice().reverse();
  return (
    <>
      <div className="ws-panel-actions">
        <p>{t('spaces.memberHint')}</p>
        {ctx.canManage ? <SpaceButton action="space-invite" label={t('spaces.invite')} primary onClick={() => overlay.modal(t('spaces.invite'), <InviteDialog />, <InviteDialog.Footer />, { className: 'ws-dialog' })} /> : null}
      </div>
      <Section title={<>{t('spaces.membersCount')} <small>{ws.members.length}</small></>}>
        <div className="ws-member-list">
          {ws.members.map(m => (
            <div className="ws-member" key={m.id}>
              <span className="ws-mark">{m.name.slice(0, 1).toUpperCase()}</span>
              <div><strong>{m.name} {m.id === 'm1' ? <small>{t('team.you')}</small> : null}</strong><span>{m.email || '—'}</span></div>
              <span className="ws-pill">{t('team.role.' + m.role)}</span>
              <span className="ws-member-status">{t(m.status === 'disabled' ? 'spaces.disabled' : 'saas.active')}</span>
              {ctx.canManage ? (
                <button className="icon-btn" data-action="saas-member" data-id={m.id} aria-label={`${t('saas.manageMember')} · ${m.name}`}
                  onClick={() => overlay.modal(t('saas.manageMember'), <ManageMemberDialog memberId={m.id} />, <ManageMemberDialog.Footer memberId={m.id} />)}>
                  <Icon name="edit" size={15} />
                </button>
              ) : null}
            </div>
          ))}
        </div>
      </Section>
      <Section title={t('spaces.pending')}>
        {ws.invitations.length ? (
          <div className="ws-invitations">
            {pending.map(i => (
              <div key={i.id}>
                <div><strong>{i.email}</strong><small>{t('team.role.' + i.role)} · {t('spaces.invitation.' + i.status)}</small></div>
                {i.status === 'pending' && ctx.canManage ? (
                  <div>
                    {ctx.runtime.simulated ? <SpaceButton action="space-accept-invite" label={t('spaces.acceptDemo')} data-id={i.id} onClick={() => void ctx.run(() => api.transitionInvitation(ctx.tenantId, i.id, 'accept'), 'spaces.invitationChanged')} /> : null}
                    <button className="text-btn" data-action="space-cancel-invite" data-id={i.id} onClick={() => void ctx.run(() => api.transitionInvitation(ctx.tenantId, i.id, 'cancel'), 'spaces.invitationChanged')}>{t('spaces.cancelInvite')}</button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : <WsEmpty text={t('spaces.noInvitations')} icon="users" />}
      </Section>
    </>
  );
}

function Roles() {
  const { t } = useWs();
  const rows = [['enterpriseManage', 'allow', 'allow', 'deny'], ['roleManage', 'allow', 'allow', 'deny'], ['transfer', 'allow', 'deny', 'deny'], ['agentManage', 'scoped', 'scoped', 'scoped'], ['ecosystemManage', 'allow', 'allow', 'deny'], ['privateRead', 'scoped', 'scoped', 'scoped'], ['resourceShare', 'scoped', 'scoped', 'scoped'], ['connectionManage', 'scoped', 'scoped', 'scoped'], ['taskUse', 'scoped', 'scoped', 'scoped'], ['audit', 'allow', 'allow', 'deny']];
  return (
    <section className="wx-team-panel">
      <div className="wx-team-panel-heading"><h2>{t('saas.roles')}</h2></div>
      <p className="wx-team-caption">{t('saas.roleNote')}</p>
      <div className="wx-saas-table-scroll">
        <table className="wx-saas-table">
          <thead><tr><th scope="col">{t('saas.permission')}</th>{['owner', 'admin', 'member'].map(r => <th scope="col" key={r}>{t('team.role.' + r)}</th>)}</tr></thead>
          <tbody>{rows.map(([key, ...values]) => <tr key={key}><th scope="row">{t('saas.' + key)}</th>{values.map((v, i) => <td key={i} className={`is-${v}`}>{t('saas.' + v)}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <p className="wx-team-caption">{t('saas.resourceNote')}</p>
    </section>
  );
}

function Resources() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const { resourceTab, set } = useUi();
  const collection: ResourceCollection = (RESOURCE_COLLECTIONS as readonly string[]).includes(resourceTab) ? (resourceTab as ResourceCollection) : 'projects';
  const items = ws[collection] as { id: string; name: string; resourceOwnerId?: string; visibility?: string }[];
  return (
    <>
      <p className="ws-body-copy">{t('spaces.resourceHint')}</p>
      <div className="ws-resource-tabs" role="tablist">
        {RESOURCE_COLLECTIONS.map(c => (
          <button key={c} role="tab" aria-selected={c === collection} className={c === collection ? 'is-active' : ''} data-action="space-resource-tab" data-id={c} onClick={() => set({ resourceTab: c })}>
            {t('spaces.kind.' + c)}<small>{(ws[c] as unknown[]).length}</small>
          </button>
        ))}
      </div>
      <Section>
        {items.length ? (
          <div className="ws-resources">
            {items.map(r => (
              <div key={r.id}>
                <span className="ws-resource-icon"><Icon name={collection === 'agents' ? 'robot' : collection === 'projects' ? 'folder' : 'file'} size={19} /></span>
                <div><strong>{r.name}</strong><small>{t('spaces.ownerLabel', { name: ws.members.find(m => m.id === r.resourceOwnerId)?.name || '—' })} · {ctx.spaceName()}</small></div>
                <span className="ws-pill">{t('spaces.scope.' + r.visibility)}</span>
                {r.resourceOwnerId === 'm1' ? (
                  <button className="text-btn" data-action="space-sharing" data-id={r.id} data-collection={collection}
                    onClick={() => overlay.modal(t('spaces.sharing'), <SharingDialog collection={collection} id={r.id} />, <SharingDialog.Footer collection={collection} id={r.id} />, { className: 'ws-dialog' })}>
                    {t('spaces.sharing')}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        ) : <WsEmpty text={t('spaces.emptyResources')} />}
      </Section>
    </>
  );
}

function Connections() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const providerName = (p: string) => (p === 'feishu' ? t('eco.feishu') : p === 'wecom' ? t('eco.wecom') : p.toUpperCase());
  return (
    <>
      <div className="ws-panel-actions">
        <p>{t('spaces.credentialsHint')}</p>
        <SpaceButton action="space-add-connection" label={t('spaces.addConnection')} primary onClick={() => overlay.modal(t('spaces.addConnection'), <AddConnectionDialog />, <AddConnectionDialog.Footer />, { className: 'ws-dialog' })} />
      </div>
      <Section title={t('spaces.connectionsCount')}>
        {ws.connections.length ? ws.connections.map(c => (
          <article className="ws-connection" key={c.id}>
            <div className="ws-connection-top">
              <span className="ws-mark"><Icon name={c.provider === 'skill' ? 'code' : 'globe'} size={20} /></span>
              <div><strong>{c.name}</strong><small>{providerName(c.provider)} · {t('spaces.auth.' + c.authMode)}</small></div>
              <span className={`ws-pill ${c.enabled ? '' : 'is-muted'}`}>{t(!c.enabled ? 'spaces.disabled' : c.authMode === 'none' ? 'spaces.noAuth' : 'spaces.needsAuth')}</span>
            </div>
            <div className="ws-connection-meta">
              <span>{ctx.spaceName()} · {t(c.ownerScope === 'space' ? 'spaces.sharedConnection' : 'spaces.memberConnection')}</span>
              <SpaceButton action="space-toggle-connection" label={t(c.enabled ? 'spaces.disable' : 'spaces.enable')} data-id={c.id} onClick={() => void ctx.run(() => api.updateConnection(ctx.tenantId, c.id, { enabled: !c.enabled }), 'spaces.saved')} />
            </div>
            {c.agentIds.length ? <div className="ws-bound-agents">{t('spaces.boundAgents')}：{c.agentIds.map(id => ws.agents.find(a => a.id === id)?.name || id).join('、')}</div> : null}
            <p className="ws-mini-note">{t('spaces.bindingHint')}</p>
          </article>
        )) : <WsEmpty text={t('spaces.noConnections')} icon="globe" />}
      </Section>
      <Section title={t('spaces.channelConnections')}>
        <p className="ws-body-copy">{t('spaces.channelHint')}</p>
        {ws.bindings.length ? ws.bindings.map(b => (
          <div className="ws-setting-row" key={b.id}><div><strong>{b.name}</strong><p>{t('spaces.channelScope')} · {ctx.spaceName()}</p></div><span>{b.platform === 'feishu' ? t('eco.feishu') : t('eco.wecom')}</span></div>
        )) : <WsEmpty text={t('spaces.noChannels')} icon="chat" />}
        <div className="ws-form-footer"><SpaceButton action="nav" label={t('spaces.ecosystem')} data-page="ecosystem" onClick={() => ctx.nav('ecosystem')} /></div>
      </Section>
    </>
  );
}

function Usage() {
  const { t, ws } = useWs();
  const items: [string, number][] = [
    ...RESOURCE_COLLECTIONS.map(c => ['spaces.kind.' + c, (ws[c] as unknown[]).length] as [string, number]),
    ['spaces.membersCount', ws.members.filter(m => m.status === 'active').length],
    ['spaces.connectionsCount', ws.connections.length],
  ];
  return (
    <>
      <p className="ws-body-copy">{t('spaces.usageHint')}</p>
      <div className="ws-usage-grid">{items.map(([key, value]) => <div key={key}><span>{t(key)}</span><strong>{value}</strong></div>)}</div>
    </>
  );
}

function Activity() {
  const { t, ws } = useWs();
  return (
    <Section>
      {ws.activity.length ? (
        <ol className="ws-activity">
          {ws.activity.map(a => (
            <li key={a.id}><Icon name="checkcircle" size={17} /><div><strong>{t('spaces.event.' + (a.spaceEvent || 'legacy'))}</strong><time>{new Date(a.at).toLocaleString(getLocale())}</time></div></li>
          ))}
        </ol>
      ) : <WsEmpty text={t('spaces.activityEmpty')} icon="clock" />}
    </Section>
  );
}

/** Personal settings (/settings/:tab) and workspace administration (/t/:id/team/:tab) — prototype renderSettings. */
export function Settings() {
  const ctx = useWs();
  const { t, page, current } = ctx;
  const personal = page === 'settings';
  const tab = ctx.routeId || 'general';
  const createOrg = useCreateOrg();
  const labels: Record<string, string> = { general: personal ? 'spaces.general' : 'spaces.workspaceSettings', profile: 'spaces.profile', spaces: 'spaces.mySpaces', members: 'spaces.members', permissions: 'spaces.permissions', data: 'spaces.data', connections: 'spaces.integrations', usage: 'spaces.usage', activity: 'spaces.activity' };
  let body: ReactNode;
  if (personal) body = tab === 'profile' ? <Profile /> : tab === 'spaces' ? <MySpaces /> : <PersonalGeneral />;
  else if (current.type === 'personal' && ['members', 'permissions', 'activity'].includes(tab)) body = <Section><p>{t('spaces.personalOnly')}</p><SpaceButton action="space-create" label={t('spaces.create')} onClick={createOrg} /></Section>;
  else if (tab === 'members') body = <Members />;
  else if (tab === 'permissions') body = <><p className="ws-body-copy">{t('spaces.departmentsHint')}</p><Section><Roles /></Section></>;
  else if (tab === 'data') body = <Resources />;
  else if (tab === 'connections') body = <Connections />;
  else if (tab === 'usage') body = <Usage />;
  else if (tab === 'activity') body = <Activity />;
  else body = <OrgGeneral />;
  return (
    <div className="ws-settings-content">
      <header>
        <div className="ws-breadcrumb">{t(personal ? 'spaces.account' : 'spaces.' + current.type)}{!personal ? ' / ' + ctx.spaceName() : ''}</div>
        <h1>{t(labels[tab] || labels.general)}</h1>
        <p>{t(personal ? (tab === 'spaces' ? 'spaces.spacesHint' : 'spaces.globalHint') : tab === 'general' ? 'spaces.overviewHint' : 'spaces.contextHint')}</p>
      </header>
      {body}
      <p className="ws-local-note"><Icon name="help" size={14} /><span>{t('spaces.local')}</span></p>
    </div>
  );
}

