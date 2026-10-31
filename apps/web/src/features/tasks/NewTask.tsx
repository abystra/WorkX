import { useEffect } from 'react';
import { useWs } from '@/app/workspace';
import { useDrafts, useUi } from '@/state/ui';
import { Avatar, Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { AgentMenu } from '@/features/shell/menus';
import { Composer } from './Composer';
import { TaskSection } from './TaskSection';
import { SUGGESTIONS } from './suggestions';

function ProjectHint() {
  const ctx = useWs();
  const { t, ws, tenantId } = ctx;
  const drafts = useDrafts(tenantId);
  const project = ws.projects.find(p => p.id === drafts.selectedProject);
  if (!project) return null;
  return (
    <div className="workspace-project-hint">
      <Icon name="users" size={18} />
      <div className="grow"><strong>{project.name}</strong><p>{t('workspace.projectContext')}</p></div>
      <button className="text-btn" data-action="open-project" data-id={project.id} onClick={() => ctx.nav('project', project.id)}>{t('workspace.projectLink')}<Icon name="chevron" size={12} /></button>
    </div>
  );
}

/** New Task page (prototype newTask()). */
export function NewTask() {
  const ctx = useWs();
  const { t, ws, tenantId, routeId } = ctx;
  const overlay = useOverlay();
  const drafts = useDrafts(tenantId);
  const setDrafts = useUi(s => s.setDrafts);
  // Route '#new/<agent>' selects the workmate (prototype readRoute; default a1).
  useEffect(() => { if (routeId && routeId !== drafts.agent) setDrafts(tenantId, { agent: routeId }); }, [routeId]); // eslint-disable-line react-hooks/exhaustive-deps
  const agent = ws.agents.find(a => a.id === (drafts.agent || routeId)) || ws.agents[0];
  return (
    <div className="new-page">
      <div className="new-hero">
        <div className="agent-greeting">
          <Avatar index={agent.avatar} size={56} />
          <button className="greeting-name" data-action="select-agent" onClick={e => overlay.popover(e.currentTarget, <AgentMenu />)}>
            {agent.name}<span style={{ transform: 'rotate(90deg)', display: 'inline-flex' }}><Icon name="chevron" size={13} /></span>
          </button>
          <button className="text-btn details-link" data-action="agent-detail" data-id={agent.id} onClick={() => ctx.nav('detail', agent.id)}>{t('Workmate Details')} <Icon name="chevron" size={12} /></button>
        </div>
        <Composer />
        <ProjectHint />
      </div>
      <section className="for-you">
        <div className="for-you-title"><h2>{t('For You')}</h2><p>{t('Here are a few recommended tasks based on your recent activity:')}</p></div>
        <div className="suggestion-grid">
          {[3, 4, 0].map(index => {
            const s = SUGGESTIONS[index];
            return (
              <button key={index} className="suggestion-card" data-action="fill-suggestion" data-index={String(index)}
                onClick={() => {
                  setDrafts(tenantId, { draft: t('suggestion.' + index), capabilities: s.label === 'Slides' || s.label === 'Deep Research' ? [s.label] : [] });
                  setTimeout(() => (document.getElementById('task-prompt') as HTMLTextAreaElement | null)?.focus(), 0);
                }}>
                <span className="suggestion-label"><Icon name={s.icon} size={13} />{t(s.label)}</span>
                <p>{t('suggestion.' + index)}</p>
              </button>
            );
          })}
        </div>
      </section>
      <TaskSection />
    </div>
  );
}
