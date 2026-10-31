import { api } from '@/api/client';
import type { ChannelRun } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { platformBy } from '@/domain/ecosystem-model.js';
import { channelKey, eligibleBindings, runIsActive, runNeedsAttention } from '@/domain/channel-rules';
import { useUi } from '@/state/ui';
import { Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { openCompose } from './ComposeDialog';

/** Cancel / retry controls for a channel run (prototype runActions). */
export function RunActions({ run }: { run: ChannelRun }) {
  const ctx = useWs();
  const { t } = ctx;
  const call = (action: string) => () => void ctx.run(() => api.call('POST', `/tenants/${ctx.tenantId}/channel-runs/${run.id}/${action}`));
  return (
    <>
      {runIsActive(run) ? <button type="button" className="btn" data-action="channel-cancel-run" data-id={run.id} onClick={call('cancel')}>{t('channel.cancelRun')}</button> : null}
      {['failed', 'cancelled', 'interrupted'].includes(run.executionStatus) ? <button type="button" className="btn primary" data-action="channel-retry-execution" data-id={run.id} onClick={call('retry-execution')}>{t('channel.retryExecution')}</button> : null}
      {run.executionStatus === 'done' && ['failed', 'cancelled', 'interrupted'].includes(run.deliveryStatus) ? <button type="button" className="btn primary" data-action="channel-retry-delivery" data-id={run.id} onClick={call('retry-delivery')}>{t('channel.retryDelivery')}</button> : null}
    </>
  );
}

export const RunStatus = ({ run }: { run: ChannelRun }) => {
  const { t } = useWs();
  return <span className={`wx-channel-status is-${run.stage}`}>{t(channelKey('stage', run.stage))}</span>;
};

/** Channel workbench (prototype renderInbox). */
export function Inbox() {
  const ctx = useWs();
  const { t, ws, runtime } = ctx;
  const overlay = useOverlay();
  const { channelFilter: filter, set } = useUi();
  const runs = ws.channelRuns.filter(run => filter === 'all' || (filter === 'active' && runIsActive(run)) || (filter === 'attention' && runNeedsAttention(run)) || (filter === 'delivered' && run.stage === 'delivered'));
  const ready = eligibleBindings(ws).length;
  const counts: [string, number][] = [['active', ws.channelRuns.filter(runIsActive).length], ['attention', ws.channelRuns.filter(runNeedsAttention).length], ['delivered', ws.channelRuns.filter(r => r.stage === 'delivered').length]];
  const compose = runtime.simulated ? <button type="button" className="btn primary" data-action="channel-compose" onClick={() => openCompose(ctx, overlay)}>{t('channel.simulate')}</button> : null;
  const manage = <button type="button" className="btn" data-action="nav" data-page="ecosystem" onClick={() => ctx.nav('ecosystem')}>{t('channel.manageBindings')}</button>;
  return (
    <section className="wx-channel-page">
      <header className="wx-channel-heading"><div><h1>{t('channel.title')}</h1><p>{t('channel.subtitle')}</p></div>{compose}</header>
      <div className="wx-channel-notice"><Icon name="help" size={17} /><p>{t('channel.notice')}</p></div>
      <div className="wx-channel-stats">
        {counts.map(([key, count]) => <div key={key}><span>{t('channel.count.' + key)}</span><strong>{count}</strong></div>)}
        <div><span>{t('channel.readyBindings')}</span><strong>{ready}</strong></div>
      </div>
      <div className="wx-channel-toolbar">
        <div className="tabs" role="tablist" aria-label={t('channel.filterLabel')}>
          {['all', 'active', 'attention', 'delivered'].map(key => (
            <button key={key} type="button" role="tab" aria-selected={filter === key} className={`tab-btn ${filter === key ? 'active' : ''}`} data-action="channel-filter" data-filter={key} onClick={() => set({ channelFilter: key })}>{t('channel.filter.' + key)}</button>
          ))}
        </div>
        <a href={`/t/${ctx.tenantId}/ecosystem`} data-action="nav" data-page="ecosystem" onClick={e => { e.preventDefault(); ctx.nav('ecosystem'); }}>{t('channel.manageBindings')}<Icon name="arrow" size={13} /></a>
      </div>
      {runs.length ? (
        <div className="wx-channel-list">
          {runs.map(run => (
            <article key={run.id} className="wx-channel-row">
              <div className="wx-channel-row-top">
                <span className={`wx-channel-platform is-${run.platform}`}><Icon name={platformBy(run.platform)?.icon || 'chat'} size={20} /></span>
                <div>
                  <button type="button" className="wx-channel-task-link" data-action="channel-open-task" data-id={run.id} onClick={() => ctx.nav('task', run.taskId)}>{run.source.message}</button>
                  <p>{t(platformBy(run.platform)?.name || 'eco.platformPending')} · {run.source.conversation} · {run.source.sender}</p>
                </div>
                <RunStatus run={run} />
              </div>
              <div className="wx-channel-row-bottom">
                <span>{t('channel.assigned', { name: run.agentName })}</span>
                <span>{t('channel.executionLabel')} {t(channelKey('execution', run.executionStatus))}</span>
                <span>{t('channel.deliveryLabel')} {t(channelKey('delivery', run.deliveryStatus))}</span>
                <div><RunActions run={run} /><button type="button" className="btn" data-action="channel-open-task" data-id={run.id} onClick={() => ctx.nav('task', run.taskId)}>{t('channel.viewTask')}</button></div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="wx-channel-empty">
          <Icon name="chat" size={30} />
          <h2>{t(ws.channelRuns.length ? 'channel.noMatches' : 'channel.emptyTitle')}</h2>
          <p>{t(ready ? 'channel.emptyReady' : 'channel.emptySetup')}</p>
          {ready && compose ? compose : manage}
        </div>
      )}
    </section>
  );
}
