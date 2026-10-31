import { Fragment } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Task, TaskEventView } from '@/api/contracts';
import { tenantKey } from '@/api/hooks';
import { useWs } from '@/app/workspace';
import { showFile } from '@/features/library/FileDialog';
import { Avatar, Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';

// Conversation against the real runtime (http mode). The prototype only had a simulated answer, so the run
// states below (queued, working with tool steps, approval, failed/interrupted with retry, needs access) are
// new UI built from the prototype's chat classes; see apps/web/docs/NEW-SCREENS.md.

const LIVE = new Set(['queued', 'provisioning', 'running', 'finalizing', 'awaiting_approval', 'waiting_external']);

function toolLabel(name: string) {
  return name.replace(/^mcp__workx__/, '').replace(/_/g, ' ');
}

function Steps({ events }: { events: TaskEventView[] }) {
  const { t } = useWs();
  const finished = new Map(events.filter(e => e.type === 'tool.finished').map(e => [String(e.payload.tool_use_id), e.payload]));
  const started = events.filter(e => e.type === 'tool.started');
  if (!started.length) return null;
  return (
    <ol className="wx-run-steps">
      {started.map(e => {
        const done = finished.get(String(e.payload.tool_use_id));
        const tool = toolLabel(String(e.payload.tool || ''));
        const key = !done ? 'web.task.stepRunning' : done.is_error ? 'web.task.stepFailed' : done.deduplicated ? 'web.task.stepReused' : 'web.task.step';
        return (
          <li key={e.seq} className={done ? (done.is_error ? 'is-failed' : 'is-done') : 'is-running'}>
            <Icon name={done ? (done.is_error ? 'help' : 'checkcircle') : 'clock'} size={14} />{t(key, { tool })}
          </li>
        );
      })}
    </ol>
  );
}

function Approvals({ task }: { task: Task }) {
  const ctx = useWs();
  const { t, tenantId } = ctx;
  const approvals = useQuery({ queryKey: [...tenantKey(tenantId), 'approvals', task.id], queryFn: () => api.approvals(tenantId, task.id) });
  const pending = (approvals.data || []).filter(a => a.status === 'pending');
  if (!pending.length) return null;
  return (
    <>
      {pending.map(a => (
        <div key={a.id} className="wx-approval" role="group" aria-label={t('web.task.approvalTitle')}>
          <strong>{t('web.task.approvalTitle')}</strong>
          <p>{t('web.task.approvalBody')}</p>
          <p className="wx-approval-summary">{a.summary || toolLabel(a.tool)}</p>
          <div className="row">
            <button className="btn primary" data-action="approval-approve" data-id={a.id} onClick={() => void ctx.run(() => api.decide(tenantId, task.id, a.id, 'approve'), 'web.task.approved')}>{t('web.task.approve')}</button>
            <button className="btn" data-action="approval-reject" data-id={a.id} onClick={() => void ctx.run(() => api.decide(tenantId, task.id, a.id, 'reject'), 'web.task.rejected')}>{t('web.task.reject')}</button>
          </div>
        </div>
      ))}
    </>
  );
}

export function RealConversation({ task }: { task: Task }) {
  const ctx = useWs();
  const { t, ws, tenantId } = ctx;
  const overlay = useOverlay();
  const agent = ws.agents.find(a => a.id === task.agent) || ws.agents[0];
  const live = LIVE.has(String(task.apiStatus || task.status));
  const detail = useQuery({
    queryKey: [...tenantKey(tenantId), 'task-detail', task.id],
    queryFn: () => api.taskDetail(tenantId, task.id),
    refetchInterval: live ? 3000 : false,
  });
  const events = useQuery({
    queryKey: [...tenantKey(tenantId), 'task-events', task.id],
    queryFn: () => api.taskEvents(tenantId, task.id),
    refetchInterval: live ? 2000 : false,
  });
  const status = detail.data?.apiStatus || String(task.apiStatus || task.status);
  const reason = detail.data?.statusReason || task.statusReason;
  const messages = detail.data?.messages || [];
  const assistantHeader = <div className="assistant-header">{agent ? <Avatar index={agent.avatar} size={29} /> : null}{agent?.name}</div>;
  const fileCard = (fileId: string) => {
    const file = ws.library.find(f => f.id === fileId);
    return (
      <button className="answer-artifact" data-action="open-file" data-id={fileId} onClick={() => showFile(ctx, overlay, fileId)}>
        <span className="artifact-icon"><Icon name="file" size={22} /></span>
        <span className="grow"><strong>{file?.name || t('Document')}</strong><br /><small>{t('Document · Click to preview')}</small></span>
        <Icon name="chevron" size={16} />
      </button>
    );
  };
  const retry = <button className="btn" data-action="task-retry" onClick={() => void ctx.run(() => api.retry(tenantId, task.id))}>{t('web.task.retry')}</button>;
  return (
    <>
      {messages.length ? messages.map((m, i) => (
        <Fragment key={m.id}>
          {m.role === 'user' ? (
            <div className="chat-user" style={i ? { marginTop: 28 } : undefined}>{m.content}</div>
          ) : (
            <>
              {assistantHeader}
              <div className="assistant-answer">
                <div className="assistant-markdown wx-answer-text">{m.content}</div>
                {m.fileId ? fileCard(m.fileId) : null}
              </div>
            </>
          )}
        </Fragment>
      )) : <div className="chat-user">{task.prompt || task.name}</div>}
      <div className="assistant-answer wx-run-state" aria-live="polite">
        {['queued', 'provisioning'].includes(status) ? <div className="progress-line"><span className="pulse" />{t('web.task.queued')}</div> : null}
        {['running', 'finalizing', 'awaiting_approval', 'waiting_external'].includes(status) ? (
          <div className="progress-line"><span className="pulse" />{t('web.task.working')}
            <button className="text-btn" data-action="task-cancel" onClick={() => void ctx.run(() => api.cancel(tenantId, task.id))}>{t('web.task.cancel')}</button>
          </div>
        ) : null}
        {live ? <Steps events={events.data || []} /> : null}
        {status === 'awaiting_approval' ? <Approvals task={task} /> : null}
        {status === 'succeeded' && !messages.some(m => m.role === 'assistant') ? <div className="progress-line"><Icon name="checkcircle" size={14} />{t('web.task.completed')}</div> : null}
        {['failed', 'interrupted', 'cancelled'].includes(status) ? (
          <div className="wx-run-ended">
            <p>{t(status === 'failed' ? 'web.task.failed' : status === 'interrupted' ? 'web.task.interrupted' : 'web.task.cancelled')}</p>
            {reason && status === 'failed' ? <p className="prototype-note">{t('web.task.reason', { reason })}</p> : null}
            {retry}
          </div>
        ) : null}
        {status === 'needs_auth' ? (
          <div className="wx-run-ended">
            <p>{t('web.task.needsAuth')}</p>
            <p className="prototype-note">{t('web.task.needsAuthResume')}</p>
            <button className="btn" data-action="task-connect" onClick={() => ctx.nav('team', 'connections')}>{t('web.task.connect')}</button>
            {retry}
          </div>
        ) : null}
      </div>
    </>
  );
}
