/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from '@/api/client';
import type { WorkspaceCtx } from '@/app/workspace';
import { useWs } from '@/app/workspace';
import { platformBy } from '@/domain/ecosystem-model.js';
import { eligibleBindings } from '@/domain/channel-rules';
import { getLocale, setLocale } from '@/i18n';
import { useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { useChannelUi, type ChannelDraft } from './store';

/** Simulated inbound message (development adapter only; prototype channel-compose). */
export function openCompose(ctx: WorkspaceCtx, overlay: ReturnType<typeof useOverlay>, bindingId?: string) {
  const bindings = eligibleBindings(ctx.ws);
  const binding = bindingId ? bindings.find(b => b.id === bindingId) : bindings[0];
  useChannelUi.getState().set({ compose: { bindingId: binding?.id || '', sender: '', conversation: '', message: '', kind: 'direct', mentioned: true, projectId: '', scenario: 'success', error: bindingId && !binding ? 'channel.bindingUnavailable' : '' } });
  overlay.modal(ctx.t('channel.simulate'), <ComposeDialog />, <ComposeDialog.Footer />, { className: 'wx-channel-modal' });
}

function capture(draft: ChannelDraft): ChannelDraft {
  const form = document.getElementById('channel-message-form') as HTMLFormElement | null;
  if (!form) return draft;
  const values = new FormData(form), next = { ...draft };
  for (const key of ['bindingId', 'sender', 'conversation', 'message', 'kind', 'projectId', 'scenario'] as const) next[key] = String(values.get(key) || '');
  next.mentioned = values.get('mentioned') !== null;
  return next;
}

export function ComposeDialog() {
  const { t, ws } = useWs();
  const draft = useChannelUi(s => s.compose);
  const set = useChannelUi(s => s.set);
  if (!draft) return null;
  const bindings = eligibleBindings(ws), binding: any = bindings.find(b => b.id === draft.bindingId), groupAllowed = binding?.method !== 'wecom-app';
  const recapture = (changedName?: string) => {
    const next = capture(draft);
    if (changedName === 'bindingId' || changedName === 'kind') {
      if (bindings.find(b => b.id === next.bindingId)?.method === 'wecom-app') next.kind = 'direct';
      set({ compose: next });
    } else useChannelUi.setState({ compose: next }); // language switch: keep typed values
  };
  const input = (id: 'sender' | 'conversation', max: number) => (
    <label className="form-field"><span>{t('channel.' + id)}</span><input name={id} maxLength={max} defaultValue={draft[id]} required autoComplete="off" /></label>
  );
  return (
    <>
      <div className="wx-channel-modal-intro">
        <p>{t('channel.composeHint')}</p>
        <div className="wx-channel-languages">
          {[['zh-CN', '中文'], ['en', 'English']].map(([locale, label]) => <button key={locale} type="button" data-action="set-language" data-locale={locale} aria-pressed={getLocale() === locale} onClick={() => { recapture(); setLocale(locale); }}>{label}</button>)}
        </div>
      </div>
      {!bindings.length ? <div className="wx-channel-error">{t('channel.emptySetup')}</div> : null}
      <form id="channel-message-form" noValidate onSubmit={e => e.preventDefault()} key={`${draft.bindingId}|${draft.kind}|${draft.rev || 0}`}>
        <label className="form-field"><span>{t('channel.binding')}</span>
          <select name="bindingId" required defaultValue={draft.bindingId} onChange={() => recapture('bindingId')}>
            <option value="">{t('channel.chooseBinding')}</option>
            {bindings.map(b => <option key={b.id} value={b.id}>{t(platformBy(b.platform).name)} · {b.name} · {ws.agents.find(a => a.id === b.assignedAgent)?.name || ''}</option>)}
          </select>
        </label>
        <div className="wx-channel-form-grid">
          <label className="form-field"><span>{t('channel.kind')}</span>
            <select name="kind" defaultValue={draft.kind} onChange={() => recapture('kind')}>
              <option value="direct">{t('channel.kind.direct')}</option>
              {groupAllowed ? <option value="group">{t('channel.kind.group')}</option> : null}
            </select>
          </label>
          {input('sender', 60)}
        </div>
        {input('conversation', 100)}
        {draft.kind === 'group' ? <label className="wx-channel-mention"><input type="checkbox" name="mentioned" defaultChecked={draft.mentioned} />{t('channel.mentioned')}</label> : null}
        <p className="wx-channel-form-note">{t(groupAllowed ? 'channel.triggerRule' : 'channel.directOnly')}</p>
        <label className="form-field"><span>{t('channel.message')}</span><textarea name="message" required maxLength={2000} rows={4} placeholder={t('channel.messagePlaceholder')} defaultValue={draft.message} /></label>
        <div className="wx-channel-form-grid">
          <label className="form-field"><span>{t('channel.project')}</span>
            <select name="projectId" defaultValue={draft.projectId}><option value="">{t('channel.noProject')}</option>{ws.projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          </label>
          <label className="form-field"><span>{t('channel.scenario')}</span>
            <select name="scenario" defaultValue={draft.scenario}>{['success', 'execution_error', 'delivery_error'].map(s => <option key={s} value={s}>{t('channel.scenario.' + s)}</option>)}</select>
          </label>
        </div>
        {draft.error ? <p className="wx-channel-error" role="alert">{t(draft.error)}</p> : null}
        <p className="wx-channel-form-note">{t('channel.submitHint')}</p>
      </form>
    </>
  );
}

ComposeDialog.Footer = function Footer() {
  const ctx = useWs();
  const { t } = ctx;
  const overlay = useOverlay();
  const toast = useToast();
  const draft = useChannelUi(s => s.compose);
  const set = useChannelUi(s => s.set);
  if (!draft) return null;
  const hasBindings = eligibleBindings(ctx.ws).length > 0;
  const cancel = () => { set({ compose: null }); overlay.close(); };
  const sample = () => set({ compose: { ...capture(draft), sender: t('channel.sampleSender'), conversation: t('channel.sampleConversation'), message: t('channel.sampleMessage'), mentioned: true, error: '', rev: (draft.rev || 0) + 1 } });
  const submit = async () => {
    const current = capture(draft);
    try {
      const result = await api.call<{ run: { taskId: string } }>('POST', `/tenants/${ctx.tenantId}/channel-messages`, current);
      cancel();
      await ctx.refresh();
      ctx.nav('task', result.run.taskId);
      toast(t('channel.accepted'));
    } catch (e) {
      set({ compose: { ...current, error: (e as { code?: string }).code || 'web.requestFailed' } });
    }
  };
  return (
    <div className="wx-channel-modal-footer">
      <button type="button" className="btn" data-action="channel-cancel-compose" onClick={cancel}>{t('channel.cancel')}</button>
      <div>
        <button type="button" className="btn" data-action="channel-fill-sample" onClick={sample}>{t('channel.fillSample')}</button>
        <button type="button" className="btn primary" data-action="channel-submit" disabled={!hasBindings} onClick={() => void submit()}>{t('channel.receive')}</button>
      </div>
    </div>
  );
};
