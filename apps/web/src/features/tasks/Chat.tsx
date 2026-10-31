import { Fragment, useEffect } from 'react';
import type { Task } from '@/api/contracts';
import { useModels } from '@/api/hooks';
import { useWs } from '@/app/workspace';
import { displayText } from '@/i18n';
import { useUi } from '@/state/ui';
import { Avatar, Icon } from '@/ui/icons';
import { IconButton, useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { TaskMenu } from '@/features/shell/menus';
import { showFile } from '@/features/library/FileDialog';
import { AssignTaskDialog } from '@/features/projects/ProjectDialogs';
import { ChannelTaskBadge } from '@/features/channels/ChannelTaskBadge';
import { ChannelTaskDetail } from '@/features/channels/ChannelTaskDetail';
import { RealConversation } from './RealConversation';
import { Composer } from './Composer';
import { modelLabel } from './ComposerMenus';

/** Project, owner and review state above a conversation (prototype taskCollaboration). */
export function TaskCollaboration({ task }: { task: Task }) {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const project = ws.projects.find(p => p.id === task.project);
  if (!project) return null;
  const owner = ws.members.find(m => m.id === task.ownerId);
  const agentCount = new Set([task.agent, ...(task.supportingAgentIds || [])]).size;
  const review = task.status === 'running' ? 'workspace.running' : task.reviewState === 'accepted' ? 'workspace.accepted' : 'workspace.review';
  return (
    <div className="workspace-task-team" aria-label={t('workspace.taskTeam')}>
      <button className="team-project" data-action="open-project" data-id={project.id} onClick={() => ctx.nav('project', project.id)}>
        <Icon name="folder" size={15} /><span className="ellipsis">{project.name}</span><Icon name="chevron" size={11} />
      </button>
      <span className="task-owner">{owner ? t('workspace.owner', { name: owner.name }) : t('workspace.unassigned')}</span>
      <span className="muted">{t('workspace.agents', { count: agentCount })}</span>
      <button className="text-btn" data-action="team-assign-task" data-id={task.id} onClick={() => overlay.modal(t('project.assignTask'), <AssignTaskDialog taskId={task.id} />, <AssignTaskDialog.Footer taskId={task.id} />)}>{t('workspace.assign')}</button>
      {task.kind === 'channel' ? <ChannelTaskBadge task={task} /> : <span className={`task-review ${task.reviewState === 'accepted' ? 'is-accepted' : ''}`}>{t(review)}</span>}
    </div>
  );
}

/** Simulated answer from the development adapter (prototype answerMarkup); real answers render as text. */
function Answer({ task }: { task: Task }) {
  const ctx = useWs();
  const { t } = ctx;
  const overlay = useOverlay();
  const toast = useToast();
  const setDrafts = useUi(s => s.setDrafts);
  if (task.status === 'running') {
    return <><div className="progress-line"><span className="pulse" />{t('chat.running')}</div><p>{t('chat.runningDescription')}</p></>;
  }
  if (task.answerKind === 'markdown') return <div className="assistant-markdown">{task.answer}</div>;
  const isCode = task.kind === 'code', isResearch = /调研|研究|Research/.test(task.name);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`${task.name}\n\n${t('明确目标与范围，整理信息与优先级，形成可执行方案。')}\n\n${t('演示结果：此内容来自本地交互原型。')}`);
      toast(t('已复制到剪贴板'));
    } catch {
      overlay.modal(t('Copy answer'), <label className="form-field"><span>{t('选择并复制以下内容')}</span><textarea readOnly defaultValue={`${task.name}\n\n${t('明确目标与范围，整理信息与优先级，形成可执行方案。')}`} /></label>);
    }
  };
  return (
    <>
      <div className="progress-line"><Icon name="checkcircle" size={14} />{t('chat.completed')} <span className="demo-badge">{t('chat.demo')}</span></div>
      <p>{t('chat.received', { prompt: task.prompt || task.name })}</p>
      <p>{t('chat.intro')}</p>
      <h3>{t(isCode ? 'chat.planCode' : isResearch ? 'chat.planResearch' : 'chat.plan')}</h3>
      <ol>
        <li><strong>{t('chat.scope')}</strong> — {t('chat.scopeBody')}</li>
        <li><strong>{t(isCode ? 'chat.organizeCode' : 'chat.organize')}</strong> — {t(isCode ? 'chat.organizeCodeBody' : 'chat.organizeBody')}</li>
        <li><strong>{t('chat.execute')}</strong> — {t('chat.executeBody')}</li>
      </ol>
      <h3>{t('chat.next')}</h3>
      <p>{t('chat.nextBody')}</p>
      <button className="answer-artifact" data-action="open-file" data-id={task.file || 'f1'} onClick={() => showFile(ctx, overlay, task.file || 'f1')}>
        <span className="artifact-icon"><Icon name="file" size={22} /></span>
        <span className="grow"><strong>{t('chat.deliverable', { name: task.name })}</strong><br /><small>{t('Document · Click to preview')}</small></span>
        <Icon name="chevron" size={16} />
      </button>
      <div className="row">
        <IconButton action="copy-answer" icon="copy" label={t('Copy answer')} data-id={task.id} onClick={() => void copy()} />
        <button className="soft-chip" data-action="followup-suggestion" onClick={() => {
          setDrafts(ctx.tenantId, { draft: t('请将以上内容整理为行动清单，并补充优先级和验收标准。') });
          setTimeout(() => (document.getElementById('task-prompt') as HTMLTextAreaElement | null)?.focus(), 0);
        }}>{t('整理为行动清单')}</button>
      </div>
    </>
  );
}

/** Conversation page (prototype chat()). */
export function Chat() {
  const ctx = useWs();
  const { t, ws, routeId, runtime } = ctx;
  const overlay = useOverlay();
  const models = useModels();
  const task = ws.tasks.find(x => x.id === routeId);
  useEffect(() => {
    if (task?.kind === 'channel') return;
    const scroll = document.querySelector('.chat-scroll');
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
  }, [task?.id, task?.status, task?.replies?.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!task) ctx.nav('home'); }, [task]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!task) return null;
  const agent = ws.agents.find(a => a.id === task.agent) || ws.agents[0];
  const menu = <IconButton action="task-menu" icon="more" label={t('Task actions')} data-id={task.id} onClick={e => overlay.popover(e.currentTarget, <TaskMenu taskId={task.id} />)} />;
  if (task.kind === 'channel') {
    return (
      <div className="chat-page">
        <header className="chat-header">
          {ws.agents.some(a => a.id === task.agent) ? <Avatar index={agent.avatar} size={29} /> : <Icon name="robot" size={29} />}
          <h1 title={task.name}>{task.name}</h1>
          {menu}
          <button className="btn" data-action="nav" data-page="inbox" onClick={() => ctx.nav('inbox')}><Icon name="chat" size={16} />{t('workspace.inbox')}</button>
        </header>
        <TaskCollaboration task={task} />
        <div className="chat-scroll" data-channel-task={task.id}><ChannelTaskDetail task={task} /></div>
      </div>
    );
  }
  return (
    <div className="chat-page">
      <header className="chat-header">
        <Avatar index={agent.avatar} size={29} />
        <h1 title={task.name}>{task.name}</h1>
        {menu}
        <IconButton action="agent-detail" icon="settings" label={t('Workmate details')} data-id={agent.id} onClick={() => ctx.nav('detail', agent.id)} />
      </header>
      <TaskCollaboration task={task} />
      <div className="chat-scroll">
        {runtime.simulated ? <div className="chat-user">
          {task.prompt || task.name}
          {task.attachment ? <div className="attachment-pill" style={{ margin: '10px 0 0', background: 'white' }}><Icon name="file" size={14} />{task.attachment}</div> : null}
          {task.capabilities?.length ? <div className="prototype-note" style={{ marginTop: 8 }}>{task.capabilities.map(c => displayText(t, c)).join(' · ')} · {displayText(t, modelLabel(t, task.model || 'Auto', models.data))}</div> : null}
        </div> : null}
        {!runtime.simulated ? <RealConversation task={task} /> : (<>
        <div className="assistant-header"><Avatar index={agent.avatar} size={29} />{agent.name}{runtime.simulated ? <span className="demo-badge">{t('Prototype')}</span> : null}</div>
        <div className="assistant-answer"><Answer task={task} /></div>
        {(task.replies || []).map((r, i) => (
          <Fragment key={i}>
            <div className="chat-user" style={{ marginTop: 28 }}>{r.prompt}</div>
            <div className="assistant-header"><Avatar index={agent.avatar} size={29} />{agent.name}</div>
            <div className="assistant-answer">
              <p>{t('chat.followup', { prompt: r.prompt })}</p>
              <ol><li>{t('chat.prepare')}</li><li>{t('chat.work')}</li><li>{t('chat.deliver')}</li></ol>
              {runtime.simulated ? <p className="prototype-note">{t('chat.preset')}</p> : null}
            </div>
          </Fragment>
        ))}
        </>)}
      </div>
      <div className="chat-composer">
        <Composer followup />
        <div className="chat-footnote">{t(runtime.simulated ? 'chat.footnote' : 'web.chatFootnote')}</div>
      </div>
    </div>
  );
}
