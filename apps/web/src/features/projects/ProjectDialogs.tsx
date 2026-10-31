import { api } from '@/api/client';
import type { Member } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { Avatar } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';

const footer = (ctx: ReturnType<typeof useWs>, close: () => void, action: string, label: string, onSave: () => void, id?: string) => (
  <>
    <button className="btn " data-action="close" onClick={close}>{ctx.t('team.cancel')}</button>
    <button className="btn primary" data-action={action} data-id={id} onClick={onSave}>{ctx.t(label)}</button>
  </>
);

/** team.js person(): initial in a circle. */
export function Person({ member, size = '' }: { member?: Pick<Member, 'name'>; size?: string }) {
  return <span className={`wx-team-person ${size}`} aria-hidden="true">{(member?.name || '?').slice(0, 1).toUpperCase()}</span>;
}

export function Checks<T extends { id: string; name: string }>({ items, selected, name, image }: { items: T[]; selected: string[]; name: string; image: (item: T) => React.ReactNode }) {
  return (
    <div className="wx-team-choice-list">
      {items.map(item => (
        <label className="wx-team-choice" key={item.id}>
          <input type="checkbox" name={name} value={item.id} defaultChecked={selected.includes(item.id)} />{image(item)}<span>{item.name}</span>
        </label>
      ))}
    </div>
  );
}

export function CreateProjectDialog() {
  const { t } = useWs();
  return (
    <form id="project-form" onSubmit={e => e.preventDefault()}>
      <label className="form-field"><span>{t('Project name')} <span className="muted">*</span></span><input name="name" placeholder={t('What are you working on?')} required maxLength={60} /></label>
      <label className="form-field"><span>{t('Description')}</span><textarea name="description" placeholder={t('A little context goes a long way…')} /></label>
    </form>
  );
}

CreateProjectDialog.Footer = function Footer() {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const form = document.getElementById('project-form') as HTMLFormElement | null;
    if (!form || !form.reportValidity()) return;
    const values = new FormData(form);
    if (!String(values.get('name')).trim()) return;
    const project = await ctx.run(() => api.create(ctx.tenantId, 'projects', { name: values.get('name'), description: values.get('description') }), '项目已创建');
    if (project) ctx.nav('project', project.id);
  };
  return (
    <>
      <button className="btn" data-action="close" onClick={overlay.close}>{ctx.t('Cancel')}</button>
      <button className="btn primary" data-action="save-project" onClick={() => void save()}>{ctx.t('Create project')}</button>
    </>
  );
};

/** Owner and supporting workmates for a task (team.js team-assign-task). */
export function AssignTaskDialog({ taskId }: { taskId: string }) {
  const { t, ws } = useWs();
  const task = ws.tasks.find(x => x.id === taskId);
  if (!task) return null;
  const project = ws.projects.find(p => p.id === task.project);
  const members = ws.members.filter(m => !project || project.memberIds.includes(m.id));
  const agents = ws.agents.filter(a => a.id !== task.agent && (!project || project.agentIds.includes(a.id)));
  const oldOwner = ws.members.find(m => m.id === task.ownerId && !members.some(member => member.id === m.id));
  return (
    <form id="team-assignment-form" onSubmit={e => e.preventDefault()}>
      <p className="wx-team-dialog-title">{task.name}</p>
      <label className="form-field"><span>{t('project.owner')}</span>
        <select name="owner" defaultValue={task.ownerId || ''}>
          <option value="">{t('project.unassigned')}</option>
          {oldOwner ? <option value={oldOwner.id}>{oldOwner.name} · {t('project.memberOutside')}</option> : null}
          {members.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </label>
      <fieldset className="wx-team-fieldset">
        <legend>{t('project.supportingAgents')}</legend>
        {agents.length ? <Checks items={agents} selected={task.supportingAgentIds || []} name="agents" image={a => <Avatar index={a.avatar} size={26} />} /> : <p className="wx-team-caption">{t('project.noSupporting')}</p>}
      </fieldset>
      <p className="prototype-note">{t('project.assignNote')}</p>
    </form>
  );
}

AssignTaskDialog.Footer = function Footer({ taskId }: { taskId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const form = document.getElementById('team-assignment-form') as HTMLFormElement | null;
    if (!form) return;
    const values = new FormData(form);
    overlay.close();
    await ctx.run(() => api.update(ctx.tenantId, 'tasks', taskId, { ownerId: values.get('owner') || '', supportingAgentIds: values.getAll('agents') }), 'project.assignSaved');
  };
  return footer(ctx, overlay.close, 'team-save-assignment', 'team.save', () => void save(), taskId);
};

export function EditContextDialog({ projectId }: { projectId: string }) {
  const { t, ws } = useWs();
  const project = ws.projects.find(p => p.id === projectId);
  if (!project) return null;
  return (
    <form id="team-context-form" onSubmit={e => e.preventDefault()}>
      <label className="form-field"><span>{t('project.contextTitle')}</span><textarea name="context" rows={9} maxLength={6000} placeholder={t('project.contextPlaceholder')} defaultValue={project.sharedContext} /></label>
      <p className="prototype-note">{t('project.contextNote')}</p>
    </form>
  );
}

EditContextDialog.Footer = function Footer({ projectId }: { projectId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const form = document.getElementById('team-context-form') as HTMLFormElement | null;
    if (!form?.reportValidity()) return;
    const context = String(new FormData(form).get('context') || '').trim().slice(0, 6000);
    overlay.close();
    await ctx.run(() => api.update(ctx.tenantId, 'projects', projectId, { sharedContext: context }), 'project.contextSaved');
  };
  return footer(ctx, overlay.close, 'team-save-context', 'team.save', () => void save(), projectId);
};

export function RosterDialog({ projectId }: { projectId: string }) {
  const { t, ws } = useWs();
  const project = ws.projects.find(p => p.id === projectId);
  if (!project) return null;
  return (
    <form id="team-roster-form" onSubmit={e => e.preventDefault()}>
      <fieldset className="wx-team-fieldset"><legend>{t('team.members')}</legend>
        <Checks items={ws.members} selected={project.memberIds} name="members" image={m => <Person member={m} size="is-small" />} />
      </fieldset>
      <fieldset className="wx-team-fieldset"><legend>{t('project.supportingAgents')}</legend>
        <Checks items={ws.agents} selected={project.agentIds} name="agents" image={a => <Avatar index={a.avatar} size={26} />} />
      </fieldset>
      <p className="prototype-note">{t('project.rosterNote')}</p>
    </form>
  );
}

RosterDialog.Footer = function Footer({ projectId }: { projectId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const form = document.getElementById('team-roster-form') as HTMLFormElement | null;
    if (!form) return;
    const values = new FormData(form);
    const result = await ctx.run(() => api.update(ctx.tenantId, 'projects', projectId, { memberIds: values.getAll('members'), agentIds: values.getAll('agents') }), 'project.rosterSaved');
    if (result) overlay.close();
  };
  return footer(ctx, overlay.close, 'team-save-roster', 'team.save', () => void save(), projectId);
};
