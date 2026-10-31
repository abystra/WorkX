import { useEffect } from 'react';
import { api } from '@/api/client';
import type { Project, Task } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { useUi } from '@/state/ui';
import { Avatar, Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { showFile } from '@/features/library/FileDialog';
import { ChannelTaskBadge } from '@/features/channels/ChannelTaskBadge';
import { AssignTaskDialog, EditContextDialog, Person, RosterDialog } from './ProjectDialogs';

const ROLES = ['owner', 'admin', 'member'];

function Tabs({ values, active, onSelect }: { values: [string, string][]; active: string; onSelect: (v: string) => void }) {
  const { t } = useWs();
  return (
    <div className="wx-team-tabs" role="tablist">
      {values.map(([value, label]) => (
        <button key={value} type="button" role="tab" aria-selected={value === active} className={value === active ? 'is-active' : ''} data-action="team-project-tab" data-tab={value} onClick={() => onSelect(value)}>{t(label)}</button>
      ))}
    </div>
  );
}

function TaskCard({ task }: { task: Task }) {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const owner = ws.members.find(m => m.id === task.ownerId);
  const agent = ws.agents.find(a => a.id === task.agent);
  const supporting = ws.agents.filter(a => (task.supportingAgentIds || []).includes(a.id));
  const file = ws.library.find(f => f.id === task.file);
  const accepted = task.reviewState === 'accepted';
  return (
    <article className="wx-project-task">
      <button className="wx-project-task-title" data-action="open-task" data-id={task.id} aria-label={t('project.openTask', { name: task.name })} onClick={() => ctx.nav('task', task.id)}>{task.name}</button>
      <div className="wx-project-task-people">
        <span title={t('project.owner')}>{owner ? <Person member={owner} size="is-small" /> : <Icon name="users" size={14} />}{owner?.name || t('project.unassigned')}</span>
        {agent ? <span title={t('project.primaryAgent')}><Avatar index={agent.avatar} size={18} />{agent.name}</span> : null}
      </div>
      {supporting.length ? <div className="wx-project-supporting"><span>{t('project.supportingAgents')}</span>{supporting.map(a => <span key={a.id} title={a.name}><Avatar index={a.avatar} size={18} />{a.name}</span>)}</div> : null}
      {task.kind === 'channel' ? <ChannelTaskBadge task={task} /> : null}
      <div className="wx-project-task-actions">
        <button className="text-btn" data-action="team-assign-task" data-id={task.id} onClick={() => overlay.modal(t('project.assignTask'), <AssignTaskDialog taskId={task.id} />, <AssignTaskDialog.Footer taskId={task.id} />)}>{t('project.assign')}</button>
        {task.status === 'done' ? (
          <button className={`text-btn ${accepted ? '' : 'is-accent'}`} data-action={accepted ? 'team-reopen-task' : 'team-accept-task'} data-id={task.id}
            onClick={() => void ctx.run(() => api.update(ctx.tenantId, 'tasks', task.id, { reviewState: accepted ? 'review' : 'accepted' }), accepted ? 'project.reopened' : 'project.confirmed')}>
            {t(accepted ? 'project.undoConfirm' : 'project.confirm')}
          </button>
        ) : null}
      </div>
      {file && task.status === 'done' ? (
        <button className="wx-project-task-file" data-action="open-file" data-id={file.id} onClick={() => showFile(ctx, overlay, file.id)}><Icon name="file" size={14} /><span>{t('project.preview')}</span><Icon name="chevron" size={11} /></button>
      ) : null}
    </article>
  );
}

function Board({ project }: { project: Project }) {
  const { t, ws } = useWs();
  const tasks = ws.tasks.filter(task => task.project === project.id && !task.archived);
  const groups: [string, string, string, Task[]][] = [
    ['running', 'project.running', 'project.emptyRunning', tasks.filter(task => !['done', 'failed', 'interrupted', 'cancelled'].includes(task.status))],
    ['review', 'project.review', 'project.emptyReview', tasks.filter(task => task.status === 'done' && task.reviewState !== 'accepted')],
    ['accepted', 'project.accepted', 'project.emptyAccepted', tasks.filter(task => task.status === 'done' && task.reviewState === 'accepted')],
  ];
  const attention = tasks.filter(task => ['failed', 'interrupted', 'cancelled'].includes(task.status));
  if (attention.length) groups.push(['attention', 'project.attention', 'project.emptyAttention', attention]);
  return (
    <>
      <p className="wx-project-board-note">{t('project.boardNote')}</p>
      <div className={`wx-project-board${attention.length ? ' has-attention' : ''}`}>
        {groups.map(([key, label, empty, items]) => (
          <section key={key} className={`wx-project-column is-${key}`}>
            <h2><span className="wx-project-status-dot" />{t(label)}<small>{items.length}</small></h2>
            <div className="wx-project-column-body">{items.length ? items.map(task => <TaskCard key={task.id} task={task} />) : <p className="wx-project-column-empty">{t(empty)}</p>}</div>
          </section>
        ))}
      </div>
    </>
  );
}

function Context({ project }: { project: Project }) {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const fileIds = [...new Set(ws.tasks.filter(task => task.project === project.id && !task.archived && task.status === 'done').map(task => task.file).filter(Boolean))];
  const files = fileIds.map(id => ws.library.find(file => file.id === id)).filter(Boolean) as typeof ws.library;
  return (
    <div className="wx-project-context-layout">
      <section className="wx-team-panel">
        <div className="wx-team-panel-heading">
          <div><h2>{t('project.contextTitle')}</h2><p>{t('project.contextDescription')}</p></div>
          <button className="btn " data-action="team-edit-context" data-id={project.id} onClick={() => overlay.modal(t('project.editContext'), <EditContextDialog projectId={project.id} />, <EditContextDialog.Footer projectId={project.id} />)}>{t('team.edit')}</button>
        </div>
        <div className={`wx-project-context ${project.sharedContext ? '' : 'is-empty'}`}>{project.sharedContext || t('project.emptyContext')}</div>
        <p className="wx-team-caption">{t('project.contextNote')}</p>
      </section>
      <section className="wx-team-panel">
        <div className="wx-team-panel-heading"><div><h2>{t('project.outcomes')} <span>{files.length}</span></h2><p>{t('project.outcomesDescription')}</p></div></div>
        {files.length ? (
          <div className="wx-project-files">
            {files.map(file => <button key={file.id} data-action="open-file" data-id={file.id} onClick={() => showFile(ctx, overlay, file.id)}><Icon name="file" size={21} /><span><strong>{file.name}</strong><small>{t('project.document')}</small></span><Icon name="chevron" size={13} /></button>)}
          </div>
        ) : <p className="wx-project-empty-line"><Icon name="file" size={20} />{t('project.noOutcomes')}</p>}
      </section>
    </div>
  );
}

function Roster({ project }: { project: Project }) {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const members = ws.members.filter(m => project.memberIds.includes(m.id));
  const agents = ws.agents.filter(a => project.agentIds.includes(a.id));
  return (
    <>
      <div className="wx-project-roster-heading">
        <p>{t('project.local')}</p>
        <button className="btn " data-action="team-project-roster" data-id={project.id} onClick={() => overlay.modal(t('project.manageRoster'), <RosterDialog projectId={project.id} />, <RosterDialog.Footer projectId={project.id} />)}>{t('project.manageRoster')}</button>
      </div>
      <div className="wx-project-roster-grid">
        <section className="wx-team-panel">
          <div className="wx-team-panel-heading"><div><h2>{t('team.members')} <span>{members.length}</span></h2><p>{t('project.peopleDescription')}</p></div></div>
          {members.map(m => <div key={m.id} className="wx-project-person-row"><Person member={m} /><strong>{m.name}</strong><span className="wx-team-role">{t('team.role.' + (ROLES.includes(m.role) ? m.role : 'member'))}</span></div>)}
        </section>
        <section className="wx-team-panel">
          <div className="wx-team-panel-heading"><div><h2>{t('project.supportingAgents')} <span>{agents.length}</span></h2><p>{t('project.agentsDescription')}</p></div></div>
          {agents.map(a => <button key={a.id} className="wx-project-person-row is-agent" data-action="agent-detail" data-id={a.id} onClick={() => ctx.nav('detail', a.id)}><Avatar index={a.avatar} size={33} /><strong>{a.name}</strong><span>{t('team.viewAgent')}</span></button>)}
        </section>
      </div>
    </>
  );
}

/** Project workspace (prototype renderProjectWorkspace). */
export function ProjectWorkspace() {
  const ctx = useWs();
  const { t, ws, routeId, tenantId } = ctx;
  const { projectTab, set, setDrafts } = useUi();
  const project = ws.projects.find(p => p.id === routeId);
  useEffect(() => { if (!project) ctx.nav('projects'); }, [project]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!project) return null;
  const active = ['tasks', 'context', 'members'].includes(projectTab) ? projectTab : 'tasks';
  const count = ws.tasks.filter(task => task.project === project.id && !task.archived).length;
  return (
    <div className="secondary-page wx-project-page">
      <div className="wx-project-crumb"><button data-action="nav" data-page="projects" onClick={() => ctx.nav('projects')}>{t('project.back')}</button><Icon name="chevron" size={12} /><span>{t('project.collaboration')}</span></div>
      <header className="wx-project-heading">
        <span className="wx-project-symbol"><Icon name="folder" size={27} /></span>
        <div>
          <h1>{project.name}</h1>
          <p>{project.description || ''}</p>
          <div className="wx-project-meta">
            <span>{t('project.peopleCount', { count: project.memberIds.length })}</span>
            <span>{t('project.agentCount', { count: project.agentIds.length })}</span>
            <span>{t('project.taskCount', { count })}</span>
          </div>
        </div>
        <button className="btn primary" data-action="project-new-task" data-id={project.id} onClick={() => { setDrafts(tenantId, { selectedProject: project.id, draft: '' }); ctx.nav('new'); }}>{t('project.newTask')}</button>
      </header>
      <Tabs values={[['tasks', 'project.tasks'], ['context', 'project.context'], ['members', 'project.members']]} active={active} onSelect={v => set({ projectTab: v })} />
      {active === 'context' ? <Context project={project} /> : active === 'members' ? <Roster project={project} /> : <Board project={project} />}
    </div>
  );
}
