import { api } from '@/api/client';
import type { Task } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { platformBy } from '@/domain/ecosystem-model.js';
import { channelBindingReady } from '@/domain/channel-rules';
import { getLocale } from '@/i18n';
import { Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { showFile } from '@/features/library/FileDialog';
import { RunActions, RunStatus } from './Inbox';
import { openCompose } from './ComposeDialog';

const clock = (value?: number) => (Number.isFinite(value) ? new Date(value!).toLocaleTimeString(getLocale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '');

/** Source, pipeline, result and delivery record of a channel task (prototype renderChannelTask). */
export function ChannelTaskDetail({ task }: { task: Task }) {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const toast = useToast();
  const run = ws.channelRuns.find(item => item.id === task.channelRunId);
  const openWorkbench = <button type="button" className="btn" data-action="nav" data-page="inbox" onClick={() => ctx.nav('inbox')}>{t('channel.openWorkbench')}</button>;
  if (!run) return <div className="wx-channel-detail"><p>{t('channel.missingRun')}</p>{openWorkbench}</div>;
  const phase = run.stage === 'received' ? 0 : run.executionStatus !== 'done' ? 1 : run.stage === 'result' ? 2 : 3;
  const platform = t(platformBy(run.platform)?.name || 'eco.platformPending');
  const source = run.source;
  const replay = async () => {
    const result = await ctx.run(() => api.call<{ message: string }>('POST', `/tenants/${ctx.tenantId}/channel-runs/${run.id}/replay`));
    if (result) toast(t(result.message));
  };
  return (
    <section className="wx-channel-detail">
      <div className="wx-channel-detail-top">
        <span className="wx-channel-local">{t('channel.demo')}</span>
        <RunStatus run={run} />
        <button type="button" className="text-btn" data-action="nav" data-page="inbox" onClick={() => ctx.nav('inbox')}>{t('channel.openWorkbench')}<Icon name="arrow" size={13} /></button>
      </div>
      <h2>{t('channel.detailTitle')}</h2>
      <p className="wx-channel-detail-intro">{t('channel.detailHint')}</p>
      <ol className="wx-channel-pipeline">
        {['received', 'running', 'result', 'delivered'].map((key, index) => (
          <li key={key} className={index < phase || run.stage === 'delivered' ? 'is-done' : index === phase ? 'is-current' : ''}><span>{index + 1}</span><strong>{t('channel.phase.' + key)}</strong></li>
        ))}
      </ol>
      <div className="wx-channel-source">
        <div><span>{t('channel.source')}</span><strong>{platform} · {run.bindingName}</strong></div>
        <div><span>{t('channel.conversation')}</span><strong>{source.conversation} · {t('channel.kind.' + source.kind)}</strong></div>
        <div><span>{t('channel.sender')}</span><strong>{source.sender}</strong></div>
        <div><span>{t('channel.partner')}</span><strong>{run.agentName}</strong></div>
      </div>
      <div className="wx-channel-message"><span>{t('channel.incoming')}</span><p>{source.message}</p></div>
      <div className="wx-channel-run-summary">
        <span>{t('channel.executionLabel')}<strong>{t('channel.execution.' + run.executionStatus)}</strong></span>
        <span>{t('channel.deliveryLabel')}<strong>{t('channel.delivery.' + run.deliveryStatus)}</strong></span>
        <span>{t('channel.attempts', { execution: run.executionAttempts, delivery: run.deliveryAttempts })}</span>
      </div>
      {run.errorKey ? <div className="wx-channel-error" role="status">{t(run.errorKey)}</div> : null}
      <div className="wx-channel-detail-actions">
        <RunActions run={run} />
        {run.errorKey === 'channel.blocked' ? (
          <>
            <button type="button" className="btn" data-action="nav" data-page="ecosystem" onClick={() => ctx.nav('ecosystem')}>{t('channel.checkBinding')}</button>
            {channelBindingReady(ws.bindings.find(b => b.id === run.bindingId), ws) && ctx.runtime.simulated ? <button type="button" className="btn" data-action="channel-compose" data-binding={run.bindingId} onClick={() => openCompose(ctx, overlay, run.bindingId)}>{t('channel.newMessage')}</button> : null}
          </>
        ) : null}
        {ctx.runtime.simulated ? <button type="button" className="btn" data-action="channel-replay" data-id={run.id} onClick={() => void replay()}>{t('channel.replay')}</button> : null}
      </div>
      {run.resultText ? (
        <section className="wx-channel-result">
          <div><h3>{t('channel.resultTitle')}</h3><button type="button" className="btn" data-action="open-file" data-id={run.fileId} onClick={() => showFile(ctx, overlay, run.fileId!)}>{t('channel.openResult')}</button></div>
          <p>{run.resultText}</p>
        </section>
      ) : null}
      <section className="wx-channel-return">
        <div><h3>{t('channel.returnTitle')}</h3><span>{platform} · {source.conversation}</span></div>
        {run.reply ? (
          <div className="wx-channel-reply"><span>{t('channel.replyFrom', { name: run.agentName })}</span><p>{run.reply.text}</p><small>{t('channel.replyDelivered', { time: clock(run.reply.at) })}</small></div>
        ) : <p className="wx-channel-return-pending">{t(run.executionStatus !== 'done' ? 'channel.awaitResult' : 'channel.awaitDelivery')}</p>}
        <p className="wx-channel-return-note">{t('channel.returnHint')}</p>
      </section>
      <details className="wx-channel-history" open>
        <summary>{t('channel.history')}<small>{t('channel.replayCount', { count: run.replayCount || 0 })}</small></summary>
        <ol>{run.history.map((item, i) => <li key={i}><time>{clock(item.at)}</time><span>{t(item.key)}</span></li>)}</ol>
        <code>{t('channel.eventId')} {run.eventId}</code>
      </details>
    </section>
  );
}
