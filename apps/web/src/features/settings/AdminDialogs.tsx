import { useState } from 'react';
import { api } from '@/api/client';
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
              {ws.members.filter(m => m.status === 'active' && m.id !== 'm1').map(m => (
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

/** Register a connection (metadata only; no secrets are collected here). */
export function AddConnectionDialog() {
  const ctx = useWs();
  const { t, ws } = ctx;
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

AddConnectionDialog.Footer = function Footer() {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const values = readForm('space-connection-form', ctx.tenantId);
    if (!values) return;
    const body = { name: values.get('name'), provider: values.get('provider'), authMode: values.get('authMode'), ownerScope: values.get('ownerScope'), agentIds: values.getAll('agents') };
    const result = await ctx.run(() => api.createConnection(ctx.tenantId, body), 'spaces.connectionRegistered');
    if (result) overlay.close();
  };
  return <SaveFooter action="space-save-connection" onSave={() => void save()} />;
};
