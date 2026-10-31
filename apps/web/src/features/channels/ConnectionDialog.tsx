/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect } from 'react';
import { api } from '@/api/client';
import type { WorkspaceCtx } from '@/app/workspace';
import { useWs } from '@/app/workspace';
import { capabilityBy, methodBy, platformBy } from '@/domain/ecosystem-model.js';
import { connectionSignature, connectionSpec, demoConnectionParams, initialConnectionDraft, validateConnection } from '@/domain/connection-model.js';
import { getLocale, setLocale } from '@/i18n';
import { Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { useChannelUi, updateConnection, type ConnectionSession } from './store';

const OUTCOMES = ['success', 'credential_error', 'permission_error', 'timeout'];
let timer: ReturnType<typeof setTimeout> | undefined;

/**
 * Opens connection setup for a binding (prototype openConnection). Pass `saved` when the binding
 * was just created, because the caller's workspace snapshot does not contain it yet.
 */
export function openConnection(ctx: WorkspaceCtx, overlay: ReturnType<typeof useOverlay>, bindingId: string, saved?: unknown) {
  const binding: any = saved || ctx.ws.bindings.find(b => b.id === bindingId);
  useChannelUi.getState().set({
    connection: {
      bindingId, signature: binding ? connectionSignature(binding) : '', stage: 'params', draft: binding ? initialConnectionDraft(binding) : { params: {}, confirmed: [], test: null },
      scenario: 'success', visibleSecrets: [], error: '', errors: [], running: false, progress: 0, lastOutcome: null, runToken: 0,
    },
  });
  overlay.modal(ctx.t('conn.title'), <ConnectionDialog />, <ConnectionDialog.Footer />, { className: 'wx-connection-modal' });
}

/** Clears secrets and timers (prototype closeConnection). */
export function closeConnection() {
  clearTimeout(timer);
  useChannelUi.getState().set({ connection: null });
}

/** Copies the visible form into the session (prototype captureConnection). */
function capture(binding: any, session: ConnectionSession): ConnectionSession {
  const form = document.getElementById('connection-form') as HTMLFormElement | null;
  if (!form) return session;
  const values = new FormData(form);
  const next = { ...session, draft: { ...session.draft } };
  if (session.stage === 'params') {
    const comparable = (params: Record<string, string>) => JSON.stringify(Object.entries(params).filter(([, v]) => String(v ?? '') !== '').sort(([a], [b]) => a.localeCompare(b)));
    const previous = comparable(session.draft.params), updated: Record<string, string> = { ...session.draft.params };
    for (const field of connectionSpec(binding, session.draft.params).fields) updated[field.id] = String(values.get(field.id) ?? '');
    next.draft.params = Object.fromEntries(connectionSpec(binding, updated).fields.map((f: any) => [f.id, updated[f.id] ?? '']));
    if (previous !== comparable(next.draft.params)) Object.assign(next, { running: false, progress: 0, lastOutcome: null, errors: [], error: '' }, { draft: { ...next.draft, test: null, confirmed: [] } });
  } else if (session.stage === 'authorization') {
    const allowed = connectionSpec(binding, session.draft.params).steps.map((s: any) => s.id);
    const confirmed = [...new Set(values.getAll('confirmed').map(String))].filter(id => allowed.includes(id));
    if (JSON.stringify(confirmed) !== JSON.stringify(session.draft.confirmed)) Object.assign(next, { progress: 0, lastOutcome: null }, { draft: { ...next.draft, test: null } });
    next.draft.confirmed = confirmed;
  } else {
    const scenario = String(values.get('scenario'));
    if (OUTCOMES.includes(scenario)) next.scenario = scenario;
  }
  return next;
}

function preflight(binding: any, s: ConnectionSession, authorization = true): ConnectionSession | null {
  const errors = validateConnection(binding, s.draft);
  if (errors.length) return { ...s, errors, stage: 'params', error: 'conn.fixParameterErrors' };
  const spec = connectionSpec(binding, s.draft.params);
  if (authorization && spec.steps.some((step: any) => !s.draft.confirmed.includes(step.id))) return { ...s, stage: 'authorization', error: 'conn.finishAuthorization' };
  return null;
}

function stageState(s: ConnectionSession, index: number) {
  if (s.running) return index < s.progress ? 'passed' : index === s.progress ? 'running' : 'pending';
  const result = s.draft.test;
  if (!result) return 'pending';
  if (result.outcome === 'success') return 'passed';
  const failedAt = result.outcome === 'credential_error' ? 1 : result.outcome === 'permission_error' ? 2 : 3;
  return index < failedAt ? 'passed' : index === failedAt ? 'failed' : 'pending';
}

function useBinding() {
  const { ws } = useWs();
  const session = useChannelUi(s => s.connection);
  return { session, binding: session ? (ws.bindings.find(b => b.id === session.bindingId) as any) : undefined };
}

/** Parameters → authorization → test (prototype rerenderConnection). */
export function ConnectionDialog() {
  const { t } = useWs();
  const { session, binding } = useBinding();
  useEffect(() => closeConnection, []);
  if (!session || !binding) return null;
  const spec = connectionSpec(binding, session.draft.params), platform = platformBy(binding.platform), method = methodBy(binding.method);
  const act = (patch: (s: ConnectionSession) => ConnectionSession) => {
    const current = useChannelUi.getState().connection;
    if (current) useChannelUi.getState().set({ connection: patch(capture(binding, current)) });
  };
  const field = (f: any) => {
    const value = session.draft.params[f.id] ?? '', id = 'conn-field-' + f.id;
    const issue = session.errors.find(e => e.field === f.id), hintId = id + '-hint', errorId = id + '-error';
    const shown = session.visibleSecrets.includes(f.id);
    const common = { id, name: f.id, required: f.required, 'aria-describedby': hintId + (issue ? ' ' + errorId : ''), 'aria-invalid': issue ? true : undefined } as const;
    return (
      <div key={f.id} className="form-field wx-conn-field">
        <label htmlFor={id}>{t(f.label)}{f.required ? <span className="wx-conn-required" aria-hidden="true">*</span> : <small>{t('conn.optional')}</small>}{f.sensitive ? <em>{t('conn.sessionOnly')}</em> : null}</label>
        {f.type === 'select' ? (
          <select {...common} defaultValue={value} onChange={() => act(s => s)}>{(f.options || []).map((o: any) => <option key={o.value} value={o.value}>{t(o.label)}</option>)}</select>
        ) : (
          <div className="wx-conn-input">
            <input {...common} type={f.sensitive && !shown ? 'password' : 'text'} defaultValue={value} maxLength={2048} autoComplete="off" spellCheck={false} data-sensitive={f.sensitive ? 'true' : undefined} />
            {f.sensitive ? (
              <button type="button" className="wx-conn-reveal" data-action="conn-show-secret" data-field={f.id} aria-label={t(shown ? 'conn.hideField' : 'conn.showField', { field: t(f.label) })} aria-pressed={shown}
                onClick={() => act(s => ({ ...s, visibleSecrets: s.visibleSecrets.includes(f.id) ? s.visibleSecrets.filter(x => x !== f.id) : [...s.visibleSecrets, f.id] }))}>
                {t(shown ? 'conn.hide' : 'conn.show')}
              </button>
            ) : null}
          </div>
        )}
        <small id={hintId}>{f.hint ? t(f.hint) : ''}</small>
        {issue ? <p id={errorId} className="wx-conn-field-error">{t(issue.key)}</p> : null}
      </div>
    );
  };
  let stage: React.ReactNode;
  if (session.stage === 'params') {
    stage = <>
      <div className="wx-conn-stage-heading"><div><h3>{t('conn.parametersTitle')}</h3><p>{t('conn.parametersIntro')}</p></div>
        <button type="button" className="btn" data-action="conn-sample" onClick={() => act(s => ({ ...s, draft: { params: demoConnectionParams(binding, s.draft.params), confirmed: [], test: null }, visibleSecrets: [], lastOutcome: null, progress: 0, errors: [], error: '' }))}>{t('conn.fillSample')}</button>
      </div>
      <div className="wx-conn-fields" key={JSON.stringify(session.draft.params)}>{spec.fields.map(field)}</div>
      {spec.callbackUrl ? <div className="wx-conn-callback"><div><strong>{t('conn.callbackTitle')}</strong><span>{t('conn.callbackHint')}</span></div><code>{spec.callbackUrl}</code></div> : null}
      <div className="wx-conn-private-note"><Icon name="help" size={15} /><p>{t('conn.secretNote')}</p></div>
    </>;
  } else if (session.stage === 'authorization') {
    const caps = (binding.capabilities || []).map((id: string) => capabilityBy(id)).filter(Boolean);
    stage = <>
      <div className="wx-conn-stage-heading"><div><h3>{t('conn.authorizationTitle')}</h3><p>{t('conn.authorizationIntro')}</p></div><span className="wx-conn-count">{session.draft.confirmed.length}/{spec.steps.length}</span></div>
      <div className="wx-conn-capabilities"><span>{t('conn.requestedCapabilities')}</span><div>{caps.map((c: any) => <span key={c.id}>{t(c.name)}</span>)}</div><p>{t('conn.pendingAuthorization')}</p></div>
      <ol className="wx-conn-auth-list">
        {spec.steps.map((step: any, index: number) => (
          <li key={step.id}>
            <div className="wx-conn-auth-number">{index + 1}</div>
            <div className="wx-conn-auth-content">
              <strong>{t(step.title)}</strong><p>{t(step.body)}</p>
              {step.url ? <a href={step.url} target="_blank" rel="noopener noreferrer">{t('conn.officialGuide')}<Icon name="external" size={12} /></a> : null}
              <label className="wx-conn-auth-confirm"><input type="checkbox" name="confirmed" value={step.id} defaultChecked={session.draft.confirmed.includes(step.id)} onChange={() => act(s => s)} /><span>{t('conn.confirmStep')}</span></label>
            </div>
          </li>
        ))}
      </ol>
    </>;
  } else {
    const resultKey = session.draft.test?.outcome || session.lastOutcome;
    const stages = spec.testStages || ['parameters', 'credentials', 'permissions', 'channel'];
    stage = <>
      <div className="wx-conn-stage-heading"><div><h3>{t('conn.testTitle')}</h3><p>{t('conn.testIntro')}</p></div><span className="wx-conn-demo-badge">{t('conn.simulation')}</span></div>
      <div className="wx-conn-test-controls">
        <label className="form-field"><span>{t('conn.scenario')}</span>
          <select name="scenario" disabled={session.running} defaultValue={session.scenario} onChange={() => act(s => s)}>{OUTCOMES.map(o => <option key={o} value={o}>{t('conn.outcome.' + o)}</option>)}</select>
        </label>
        {session.running
          ? <button type="button" className="btn" data-action="conn-stop" onClick={() => { clearTimeout(timer); updateConnection({ running: false, draft: { ...session.draft, test: null }, lastOutcome: 'cancelled', runToken: session.runToken + 1 }); }}>{t('conn.cancelTest')}</button>
          : <button type="button" className="btn primary" data-action={session.draft.test ? 'conn-retry' : 'conn-test'} onClick={() => startTest(binding)}>{t(session.draft.test ? 'conn.retest' : 'conn.startTest')}</button>}
      </div>
      <ol className="wx-conn-test-steps" aria-live="polite">
        {stages.map((name: string, index: number) => {
          const state = stageState(session, index);
          return <li key={name} className={`is-${state}`}><span className="wx-conn-test-dot">{state === 'passed' ? <Icon name="check" size={12} /> : state === 'failed' ? '!' : index + 1}</span><div><strong>{t('conn.testStage.' + name)}</strong><small>{t('conn.stageState.' + state)}</small></div></li>;
        })}
      </ol>
      {resultKey ? (
        <div className={`wx-conn-result ${resultKey === 'success' ? 'is-success' : 'is-error'}`} role="status">
          <strong>{t('conn.result.' + resultKey)}</strong><p>{t('conn.fix.' + resultKey)}</p>
          {resultKey === 'credential_error' ? <button type="button" className="btn" data-action="conn-fix-params" onClick={() => act(s => ({ ...s, stage: 'params' }))}>{t('conn.fixParams')}</button>
            : resultKey === 'permission_error' ? <button type="button" className="btn" data-action="conn-fix-auth" onClick={() => act(s => ({ ...s, stage: 'authorization' }))}>{t('conn.fixAuthorization')}</button> : null}
        </div>
      ) : null}
      <p className="wx-conn-test-footnote">{t('conn.noMessageSent')}</p>
    </>;
  }
  return (
    <>
      <div className="wx-conn-binding">
        <span className={`wx-conn-platform ${binding.platform === 'wecom' ? 'is-wecom' : ''}`}><Icon name={platform?.icon || 'globe'} size={20} /></span>
        <div><strong>{binding.name}</strong><p>{t(platform?.name || 'eco.platformPending')} · {t(method?.name || 'eco.modeUndecided')}</p></div>
        <div className="wx-conn-top-tools">
          <span className="wx-conn-demo-badge">{t('conn.localPrototype')}</span>
          <div className="wx-conn-languages" aria-label={t('conn.language')}>
            {[['zh-CN', '中文'], ['en', 'English']].map(([locale, label]) => (
              <button key={locale} type="button" data-action="set-language" data-locale={locale} aria-pressed={getLocale() === locale} lang={locale} onClick={() => { act(s => s); setLocale(locale); }}>{label}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="wx-conn-tabs" role="tablist" aria-label={t('conn.steps')}>
        {(['params', 'authorization', 'test'] as const).map((name, index) => (
          <button key={name} type="button" role="tab" aria-selected={session.stage === name} className={session.stage === name ? 'is-active' : ''} data-action="conn-tab" data-stage={name} disabled={session.running}
            onClick={() => act(s => ({ ...s, stage: name, error: '', errors: [] }))}>
            <span>{index + 1}</span>{t('conn.tab.' + name)}
          </button>
        ))}
      </div>
      <form id="connection-form" data-stage={session.stage} noValidate onSubmit={e => e.preventDefault()} key={session.stage}>
        {stage}
        {session.error ? <p className="wx-conn-error" role="alert">{t(session.error)}</p> : null}
        <p className="wx-conn-save-hint">{t('conn.saveHint')}</p>
      </form>
    </>
  );
}

/** Simulated connection test with the prototype's 300 ms stage timing. */
function startTest(binding: any) {
  const initial = useChannelUi.getState().connection;
  if (!initial || initial.running) return;
  const captured = capture(binding, initial);
  const blocked = preflight(binding, captured);
  if (blocked) { useChannelUi.getState().set({ connection: blocked }); return; }
  clearTimeout(timer);
  const runToken = captured.runToken + 1, scenario = captured.scenario;
  const stages = connectionSpec(binding, captured.draft.params).testStages;
  const failAt = scenario === 'credential_error' ? 1 : scenario === 'permission_error' ? 2 : scenario === 'timeout' ? 3 : -1;
  useChannelUi.getState().set({ connection: { ...captured, running: true, stage: 'test', progress: 0, runToken, error: '', errors: [], lastOutcome: null, draft: { ...captured.draft, test: null } } });
  const tick = () => {
    const s = useChannelUi.getState().connection;
    if (!s || s.runToken !== runToken) return;
    if (s.progress === failAt || s.progress >= stages.length - 1) {
      updateConnection({ running: false, draft: { ...s.draft, test: { status: scenario === 'success' ? 'success' : 'error', outcome: scenario, at: Date.now(), simulated: true } } });
      return;
    }
    updateConnection({ progress: s.progress + 1 });
    timer = setTimeout(tick, 300);
  };
  timer = setTimeout(tick, 300);
}

ConnectionDialog.Footer = function Footer() {
  const ctx = useWs();
  const { t } = ctx;
  const overlay = useOverlay();
  const toast = useToast();
  const { session, binding } = useBinding();
  if (!session || !binding) return null;
  const cancel = () => { closeConnection(); overlay.close(); };
  const guard = () => {
    if (connectionSignature(binding) !== session.signature) { cancel(); toast(t('conn.bindingChanged')); return null; }
    return capture(binding, { ...session, error: '', errors: [] });
  };
  const back = () => { const s = guard(); if (s) useChannelUi.getState().set({ connection: { ...s, stage: s.stage === 'test' ? 'authorization' : 'params' } }); };
  const next = () => {
    const s = guard();
    if (!s) return;
    const blocked = preflight(binding, s, s.stage !== 'params');
    useChannelUi.getState().set({ connection: blocked || { ...s, stage: s.stage === 'params' ? 'authorization' : 'test' } });
  };
  const save = async () => {
    const s = guard();
    if (!s) return;
    // The server keeps only non-secret fields, confirmations and the simulated result (sanitizeConnection).
    await ctx.run(() => api.call('PUT', `/tenants/${ctx.tenantId}/channel-bindings/${binding.id}/connection`, { platform: binding.platform, draft: s.draft, test: s.draft.test }), 'conn.saved');
    cancel();
  };
  return (
    <div className="wx-conn-footer">
      <button type="button" className="btn" data-action="conn-cancel" onClick={cancel}>{t('conn.cancel')}</button>
      <div>
        {session.stage !== 'params' ? <button type="button" className="btn" data-action="conn-back" disabled={session.running} onClick={back}>{t('conn.back')}</button> : null}
        <button type="button" className="btn" data-action="conn-save" disabled={session.running} onClick={() => void save()}>{t('conn.save')}</button>
        {session.stage !== 'test' ? <button type="button" className="btn primary" data-action="conn-next" onClick={next}>{t('conn.next')}</button> : null}
      </div>
    </div>
  );
};
