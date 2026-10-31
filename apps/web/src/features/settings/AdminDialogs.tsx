import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Connector } from '@/api/contracts';
import { tenantKey } from '@/api/hooks';
import { useWs } from '@/app/workspace';
import { SpaceMark } from '@/features/shell/menus';
import { Avatar, Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { Field, SpaceButton, readForm } from './SpaceDialogs';

const SaveFooter = ({ action, onSave, extra = {} }: { action: string; onSave: () => void; extra?: Record<`data-${string}`, string> }) => {
  const { t } = useWs();
  const overlay = useOverlay();
  return (
    <>
      <SpaceButton action="close" label={t('team.cancel')} onClick={overlay.close} />
      <SpaceButton action={action} label={t('team.save')} primary onClick={onSave} {...extra} />
    </>
  );
};

/** Prototype saas-member dialog (name, department attribute, role, status). */
export function ManageMemberDialog({ memberId }: { memberId: string }) {
  const { t, ws } = useWs();
  const member = ws.members.find(m => m.id === memberId);
  if (!member) return null;
  const owner = member.role === 'owner';
  return (
    <form id="saas-member-form" onSubmit={e => e.preventDefault()}>
      <label className="form-field"><span>{t('team.name')}</span><input name="name" maxLength={40} required defaultValue={member.name} /></label>
      <label className="form-field"><span>{t('saas.department')}</span>
        <select name="departmentId" defaultValue={member.departmentId || ''}>
          <option value="">{t('saas.unassigned')}</option>
          {ws.departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </label>
      <label className="form-field"><span>{t('team.role')}</span>
        <select name="role" disabled={owner} defaultValue={member.role}>
          {(owner ? ['owner'] : ['member', 'admin']).map(r => <option key={r} value={r}>{t('team.role.' + r)}</option>)}
        </select>
      </label>
      <label className="form-field"><span>{t('saas.status')}</span>
        <select name="status" disabled={owner} defaultValue={member.status}>
          {['active', 'disabled'].map(s => <option key={s} value={s}>{t('saas.' + s)}</option>)}
        </select>
      </label>
      <p className="prototype-note">{t(owner ? 'saas.ownerProtected' : 'saas.memberNote')}</p>
    </form>
  );
}

ManageMemberDialog.Footer = function Footer({ memberId }: { memberId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const values = readForm('saas-member-form', ctx.tenantId);
    if (!values) return;
    const patch = Object.fromEntries([...values.entries()].map(([k, v]) => [k, String(v)]));
    const result = await ctx.run(() => api.updateMember(ctx.tenantId, memberId, patch), 'saas.saved');
    if (result) overlay.close();
  };
  return <SaveFooter action="saas-save-member" onSave={() => void save()} extra={{ 'data-id': memberId }} />;
};

type Collection = 'projects' | 'tasks' | 'library' | 'agents' | 'automations';

/** Resource sharing dialog (prototype space-sharing). */
export function SharingDialog({ collection, id }: { collection: Collection; id: string }) {
  const ctx = useWs();
  const { t, ws, current } = ctx;
  const resource = (ws[collection] as { id: string; name: string; visibility?: string; project?: string; sharingProjectId?: string; sharedMemberIds?: string[] }[]).find(r => r.id === id);
  const [visibility, setVisibility] = useState(resource?.visibility || 'private');
  if (!resource) return null;
  const scopes = current.type === 'personal' ? ['private'] : ['private', 'selected', 'project', 'space'];
  const selectedProject = resource.project || resource.sharingProjectId || (collection === 'projects' ? resource.id : '');
  return (
    <>
      <p className="ws-body-copy">{t('spaces.sharingHint')}</p>
      <div className="ws-dialog-space"><Icon name="file" size={19} /><strong>{resource.name}</strong><span>{ctx.spaceName()}</span></div>
      <form id="space-sharing-form" data-tenant={ctx.tenantId} onSubmit={e => e.preventDefault()}>
        <Field label={t('spaces.sharingScope')}>
          <select name="visibility" value={visibility} onChange={e => setVisibility(e.target.value)}>
            {scopes.map(s => <option key={s} value={s}>{t('spaces.scope.' + s)}</option>)}
          </select>
        </Field>
        {current.type === 'organization' ? (
          <>
            <div data-sharing-scope="project" hidden={visibility !== 'project'}>
              <Field label={t('spaces.project')}>
                <select name="projectId" defaultValue={selectedProject}>
                  {collection === 'projects' ? null : <option value="">{t('spaces.chooseProject')}</option>}
                  {(collection === 'projects' ? [resource] : ws.projects).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </Field>
            </div>
            <fieldset className="wx-team-fieldset" data-sharing-scope="selected" hidden={visibility !== 'selected'}>
              <legend>{t('spaces.chooseMembers')}</legend>
              {ws.members.filter(m => m.status === 'active' && m.id !== ctx.selfId).map(m => (
                <label className="wx-team-choice" key={m.id}><input type="checkbox" name="members" value={m.id} defaultChecked={resource.sharedMemberIds?.includes(m.id)} />{m.name}</label>
              ))}
            </fieldset>
          </>
        ) : null}
      </form>
    </>
  );
}

SharingDialog.Footer = function Footer({ collection, id }: { collection: Collection; id: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const values = readForm('space-sharing-form', ctx.tenantId);
    if (!values) return;
    const body = { visibility: values.get('visibility'), memberIds: values.getAll('members'), projectId: values.get('projectId') };
    const result = await ctx.run(() => api.setSharing(ctx.tenantId, collection === 'library' ? 'artifacts' : collection, id, body), 'spaces.saved');
    if (result) overlay.close();
  };
  return <SaveFooter action="space-save-sharing" onSave={() => void save()} extra={{ 'data-id': id, 'data-collection': collection }} />;
};

/** Register a connection. Development adapter: metadata only (prototype). Real API: RealConnectionForm. */
export function AddConnectionDialog() {
  const ctx = useWs();
  const { t, ws } = ctx;
  if (!ctx.runtime.simulated) return <RealConnectionForm />;
  return (
    <>
      <p className="ws-body-copy">{t('spaces.connectionFormHint')}</p>
      <div className="ws-dialog-space"><SpaceMark space={ctx.current} /><strong>{ctx.spaceName()}</strong></div>
      <form id="space-connection-form" data-tenant={ctx.tenantId} onSubmit={e => e.preventDefault()}>
        <Field label={t('spaces.connectionName')}><input name="name" required maxLength={80} autoComplete="off" /></Field>
        <div className="ws-form-grid">
          <Field label={t('spaces.provider')}>
            <select name="provider">{['feishu', 'wecom', 'mcp', 'skill', 'api'].map(p => <option key={p} value={p}>{p === 'feishu' ? t('eco.feishu') : p === 'wecom' ? t('eco.wecom') : p.toUpperCase()}</option>)}</select>
          </Field>
          <Field label={t('spaces.authMode')}>
            <select name="authMode">{['oauth', 'static', 'none', 'exchange', 'envfile'].map(a => <option key={a} value={a}>{t('spaces.auth.' + a)}</option>)}</select>
          </Field>
        </div>
        <Field label={t('spaces.connectionOwnership')}>
          <select name="ownerScope"><option value="member">{t('spaces.memberConnection')}</option>{ctx.canManage ? <option value="space">{t('spaces.sharedConnection')}</option> : null}</select>
        </Field>
        <fieldset className="wx-team-fieldset">
          <legend>{t('spaces.boundAgents')}</legend>
          {ws.agents.map(a => <label className="wx-team-choice" key={a.id}><input type="checkbox" name="agents" value={a.id} /><Avatar index={a.avatar} size={22} />{a.name}</label>)}
        </fieldset>
      </form>
    </>
  );
}

/** Usable connectors: installed and enabled, or (for managers) installable on save. Class 0 needs no connection. */
function useConnectors() {
  const ctx = useWs();
  const query = useQuery({ queryKey: [...tenantKey(ctx.tenantId), 'connectors'], queryFn: () => api.connectors(ctx.tenantId) });
  const canInstall = ctx.canManage || ctx.current.type === 'personal';
  return (query.data || []).filter(c => c.auth !== 'none' && ((c.installed && c.enabled) || canInstall));
}

/**
 * Real API (Part 6): the connector comes from the workspace catalog and decides the auth method; an API key is
 * sent once to the credential broker and never shown again. OAuth connectors are created as "Authorization required".
 */
function RealConnectionForm() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const connectors = useConnectors();
  const [connectorId, setConnectorId] = useState('');
  const connector: Connector | undefined = connectors.find(c => c.id === connectorId) || connectors[0];
  return (
    <>
      <p className="ws-body-copy">{t('web.conn.formHint')}</p>
      <div className="ws-dialog-space"><SpaceMark space={ctx.current} /><strong>{ctx.spaceName()}</strong></div>
      <form id="space-connection-form" data-tenant={ctx.tenantId} onSubmit={e => e.preventDefault()}>
        <Field label={t('spaces.connectionName')}><input name="name" required maxLength={80} autoComplete="off" /></Field>
        <div className="ws-form-grid">
          <Field label={t('spaces.provider')}>
            <select name="connectorId" value={connector?.id || ''} onChange={e => setConnectorId(e.target.value)}>
              {connectors.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label={t('spaces.authMode')}>
            <input readOnly value={connector ? t('spaces.auth.' + (connector.auth === 'api_key' ? 'static' : connector.auth)) : ''} />
          </Field>
        </div>
        {connector?.auth === 'api_key'
          ? <Field label={t('web.conn.apiKey')}><input name="secret" type="password" required maxLength={8192} autoComplete="off" spellCheck={false} /></Field>
          : null}
        {connector && !connector.installed ? connector.config_fields.map(f => (
          <Field key={f} label={t('web.conn.config.' + f)}>
            <input name={`config.${f}`} type={f === 'client_secret' ? 'password' : 'text'} maxLength={2000} autoComplete="off" spellCheck={false} required={f === 'base_url'} />
          </Field>
        )) : null}
        {connector?.auth === 'oauth' ? <p className="ws-mini-note">{t('web.conn.oauthNote')}</p> : null}
        <Field label={t('spaces.connectionOwnership')}>
          <select name="ownerScope"><option value="member">{t('spaces.memberConnection')}</option>{ctx.canManage && connector?.identity !== 'user' ? <option value="space">{t('spaces.sharedConnection')}</option> : null}</select>
        </Field>
        <fieldset className="wx-team-fieldset">
          <legend>{t('spaces.boundAgents')}</legend>
          {ws.agents.map(a => <label className="wx-team-choice" key={a.id}><input type="checkbox" name="agents" value={a.id} /><Avatar index={a.avatar} size={22} />{a.name}</label>)}
        </fieldset>
        <p className="ws-mini-note">{t('web.conn.bindingRule')}</p>
      </form>
    </>
  );
}

AddConnectionDialog.Footer = function Footer() {
  const ctx = useWs();
  const overlay = useOverlay();
  const connectors = useConnectors();
  const saveReal = async () => {
    const values = readForm('space-connection-form', ctx.tenantId);
    if (!values) return;
    const connector = connectors.find(c => c.id === values.get('connectorId'));
    if (!connector) return;
    const shared = values.get('ownerScope') === 'space';
    const agentIds = values.getAll('agents').map(String);
    const config: Record<string, string> = {};
    for (const f of connector.config_fields) {
      const value = String(values.get(`config.${f}`) || '').trim();
      if (value && f !== 'client_secret') config[f] = value;
    }
    const clientSecret = String(values.get('config.client_secret') || '');
    const result = await ctx.run(async () => {
      if (!connector.installed || !connector.enabled) await api.installConnector(ctx.tenantId, connector.id, config);
      if (clientSecret) await api.setClientSecret(ctx.tenantId, connector.id, clientSecret);
      const created = await api.createConnection(ctx.tenantId, { connectorId: connector.id, name: values.get('name'), ownerScope: values.get('ownerScope'), secret: values.get('secret') || undefined });
      if (shared && agentIds.length) await api.bindConnection(ctx.tenantId, created.id, agentIds, connector.tools);
      // OAuth: continue at the provider; it sends the browser back to this page.
      if (connector.auth === 'oauth') {
        const { authorize_url } = await api.authorizeConnection(ctx.tenantId, created.id, window.location.pathname);
        window.location.assign(authorize_url);
      }
      return created;
    }, connector.auth === 'oauth' ? undefined : 'spaces.connectionRegistered');
    if (result) overlay.close();
  };
  const save = async () => {
    if (!ctx.runtime.simulated) return saveReal();
    const values = readForm('space-connection-form', ctx.tenantId);
    if (!values) return;
    const body = { name: values.get('name'), provider: values.get('provider'), authMode: values.get('authMode'), ownerScope: values.get('ownerScope'), agentIds: values.getAll('agents') };
    const result = await ctx.run(() => api.createConnection(ctx.tenantId, body), 'spaces.connectionRegistered');
    if (result) overlay.close();
  };
  return <SaveFooter action="space-save-connection" onSave={() => void save()} />;
};
