/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { CAPABILITIES, METHODS, PLATFORMS, bindingIsReady, methodBy, normalizeCapabilities, platformBy } from '@/domain/ecosystem-model.js';
import { Avatar, Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { useChannelUi, updateWizard, type WizardState } from './store';
import { openConnection } from './ConnectionDialog';

const STEPS = ['eco.stepPlatform', 'eco.stepMethod', 'eco.stepAgent', 'eco.stepCapabilities'];

/** Reads the current step's form into the draft (prototype captureEcosystemWizard). */
function capture(wizard: WizardState): WizardState {
  const form = document.getElementById('eco-wizard-form') as HTMLFormElement | null;
  if (!form) return wizard;
  const values = new FormData(form), draft = { ...wizard.draft };
  if (wizard.step === 2 && draft.method === 'wecom-ai-bot') draft.transport = values.get('transport') || draft.transport || 'websocket';
  if (wizard.step === 3) draft.assignedAgent = values.get('assignedAgent') || '';
  if (wizard.step === 4) { draft.name = String(values.get('name') || ''); draft.capabilities = normalizeCapabilities(draft.method, values.getAll('capabilities')); }
  return { ...wizard, draft };
}

function stageError(wizard: WizardState, data: any, all = false) {
  const draft = wizard.draft, method = methodBy(draft.method);
  if ((all || wizard.step === 1) && !platformBy(draft.platform)) return 'eco.requiredPlatform';
  if ((all || wizard.step === 2) && (!method || method.platform !== draft.platform || (method.id === 'wecom-ai-bot' && !['websocket', 'callback'].includes(draft.transport)))) return 'eco.requiredMethod';
  if ((all || wizard.step === 3) && !data.agents.some((a: any) => a.id === draft.assignedAgent)) return 'eco.selectAgent';
  if (all || wizard.step === 4) {
    if (!draft.name.trim() || draft.name.trim().length > 60) return 'eco.requiredName';
    if (!bindingIsReady({ ...draft, configured: true }, data)) return 'eco.requiredCapability';
  }
  return '';
}

/** Four-step binding wizard: platform → method → workmate → capabilities (prototype rerenderEcosystemWizard). */
export function EcosystemWizard() {
  const { t, ws } = useWs();
  const wizard = useChannelUi(s => s.wizard);
  if (!wizard) return null;
  const draft = wizard.draft, method = methodBy(draft.method), platform = platformBy(draft.platform);
  let body: React.ReactNode = null;
  if (wizard.step === 1) {
    body = <>
      <p className="wx-eco-step-intro">{t('eco.choosePlatformHint')}</p>
      <div className="wx-eco-platform-options">
        {PLATFORMS.map((item: any) => (
          <button key={item.id} type="button" className={`wx-eco-option${draft.platform === item.id ? ' is-selected' : ''}`} data-action="eco-platform" data-value={item.id} aria-pressed={draft.platform === item.id}
            onClick={() => { const w = capture(wizard); if (w.draft.platform !== item.id) Object.assign(w.draft, { platform: item.id, method: '', capabilities: [], transport: 'websocket' }); updateWizard({ ...w, error: '' }); }}>
            <span className={`wx-eco-mark wx-eco-mark-${item.id}`} aria-hidden="true"><Icon name={item.icon} size={23} /></span><strong>{t(item.name)}</strong><span>{t(item.description)}</span>
          </button>
        ))}
      </div>
    </>;
  } else if (wizard.step === 2) {
    body = <>
      <p className="wx-eco-step-intro">{t('eco.chooseMethodHint', { platform: t(platform?.name || 'eco.platformPending') })}</p>
      <div className="wx-eco-method-options">
        {METHODS.filter((m: any) => m.platform === draft.platform).map((item: any) => (
          <button key={item.id} type="button" className={`wx-eco-method-option${draft.method === item.id ? ' is-selected' : ''}`} data-action="eco-method" data-value={item.id} aria-pressed={draft.method === item.id}
            onClick={() => {
              const w = capture(wizard);
              w.draft.method = item.id;
              w.draft.capabilities = normalizeCapabilities(item.id, w.draft.capabilities);
              if (item.id === 'wecom-ai-bot' && !['websocket', 'callback'].includes(w.draft.transport)) w.draft.transport = 'websocket';
              updateWizard({ ...w, error: '' });
            }}>
            <span className="wx-eco-radio" aria-hidden="true" /><span><strong>{t(item.name)}<small>{t('eco.kind.' + item.kind)}</small></strong><span>{t(item.description)}</span></span>
          </button>
        ))}
      </div>
      {method?.id === 'wecom-ai-bot' ? (
        <label className="form-field wx-eco-transport"><span>{t('eco.transport')}</span>
          <select name="transport" defaultValue={draft.transport}><option value="websocket">{t('eco.websocket')}</option><option value="callback">{t('eco.callback')}</option></select>
          <small>{t('eco.transportHint')}</small>
        </label>
      ) : null}
    </>;
  } else if (wizard.step === 3) {
    const reused = ws.agents.filter(a => ws.bindings.some((b: any) => b.assignedAgent === a.id)).slice(0, 4);
    body = <>
      <p className="wx-eco-step-intro">{t('eco.chooseAgentHint')}</p>
      <label className="form-field"><span>{t('eco.agent')}</span>
        <select name="assignedAgent" required defaultValue={draft.assignedAgent}>
          <option value="">{t('eco.selectAgent')}</option>
          {ws.agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      {!ws.agents.length ? <p className="wx-eco-error">{t('eco.noAgents')}</p> : null}
      <div className="wx-eco-form-note"><strong>{t('eco.reuseAgentTitle')}</strong><p>{t('eco.reuseAgentHint')}</p></div>
      <div className="wx-eco-agent-reference">
        {reused.map(a => <span key={a.id}><Avatar index={a.avatar} size={24} /><strong>{a.name}</strong><small>{t('eco.bindingCount', { count: ws.bindings.filter((b: any) => b.assignedAgent === a.id).length })}</small></span>)}
      </div>
    </>;
  } else {
    const allowed = method ? [...method.required, ...method.optional] : [];
    body = <>
      <label className="form-field"><span>{t('eco.configName')}</span><input name="name" maxLength={60} required defaultValue={draft.name} placeholder={t('eco.namePlaceholder')} autoComplete="off" /></label>
      <div className="wx-eco-form-note"><strong>{t('eco.authPending')}</strong><p>{t('eco.authHint')}</p></div>
      {['messages', 'tools'].map(group => {
        const caps = CAPABILITIES.filter((c: any) => c.group === group && allowed.includes(c.id));
        if (!caps.length) return null;
        return (
          <fieldset key={group} className="wx-eco-capabilities"><legend>{t('eco.group.' + group)}</legend>
            {caps.map((cap: any) => (
              <label key={cap.id} className="wx-eco-capability">
                <input type="checkbox" name="capabilities" value={cap.id} defaultChecked={draft.capabilities.includes(cap.id)} disabled={method.required.includes(cap.id)} />
                <span><strong>{t(cap.name)}{method.required.includes(cap.id) ? <small>{t('eco.required')}</small> : null}</strong><span>{t(cap.description)}</span></span>
                <em>{t('eco.authPending')}</em>
              </label>
            ))}
          </fieldset>
        );
      })}
      {method?.kind === 'tools' ? <p className="wx-eco-form-footnote">{t('eco.atLeastOneTool')}</p> : null}
      <div className="wx-eco-review">
        <span>{t('eco.review')}</span>
        <strong>{platform ? t(platform.name) : ''} <i>→</i> {method ? t(method.name) : ''} <i>→</i> {ws.agents.find(a => a.id === draft.assignedAgent)?.name || ''}</strong>
        {method?.id === 'wecom-ai-bot' ? <small>{t(draft.transport === 'websocket' ? 'eco.websocket' : 'eco.callback')}</small> : null}
      </div>
    </>;
  }
  return (
    <>
      <ol className="wx-eco-stepper" aria-label={t('eco.setupProgress')}>
        {STEPS.map((key, index) => (
          <li key={key} className={index + 1 === wizard.step ? 'is-current' : index + 1 < wizard.step ? 'is-complete' : ''} aria-current={index + 1 === wizard.step ? 'step' : undefined}>
            <span>{index + 1 < wizard.step ? <Icon name="check" size={13} /> : index + 1}</span><strong>{t(key)}</strong>
          </li>
        ))}
      </ol>
      <form id="eco-wizard-form" data-step={wizard.step} onSubmit={e => e.preventDefault()} key={wizard.step}>
        <h3 className="wx-eco-step-title">{t(STEPS[wizard.step - 1])}</h3>
        {body}
        {wizard.error ? <p className="wx-eco-error" role="alert">{t(wizard.error)}</p> : null}
        <p className="wx-eco-form-footnote">{t('eco.localOnly')}</p>
      </form>
    </>
  );
}

EcosystemWizard.Footer = function Footer() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const toast = useToast();
  const wizard = useChannelUi(s => s.wizard);
  const set = useChannelUi(s => s.set);
  if (!wizard) return null;
  const cancel = () => { set({ wizard: null }); overlay.close(); };
  const back = () => { const w = capture(wizard); updateWizard({ ...w, error: '', step: Math.max(1, w.step - 1) }); };
  const next = () => {
    const w = capture(wizard);
    const error = stageError(w, ws);
    updateWizard({ ...w, error, step: error ? w.step : Math.min(4, w.step + 1) });
  };
  const save = async () => {
    const w = capture(wizard);
    const error = stageError(w, ws, true);
    if (error) { updateWizard({ ...w, error }); return; }
    try {
      const saved = await api.call<{ id: string }>('POST', `/tenants/${ctx.tenantId}/channel-bindings`, { ...w.draft, id: w.editingId || undefined });
      set({ wizard: null });
      overlay.close();
      await ctx.refresh();
      toast(t('eco.saved'));
      openConnection(ctx, overlay, saved.id, saved);
    } catch (e) {
      updateWizard({ ...w, error: (e as { code?: string }).code || 'web.requestFailed' });
    }
  };
  return (
    <div className="wx-eco-wizard-footer">
      <button type="button" className="btn" data-action="eco-cancel" onClick={cancel}>{t('eco.cancel')}</button>
      <div>
        {wizard.step > 1 ? <button type="button" className="btn" data-action="eco-back" onClick={back}>{t('eco.back')}</button> : null}
        <button type="button" className="btn primary" data-action={wizard.step < 4 ? 'eco-next' : 'eco-save'} onClick={() => (wizard.step < 4 ? next() : void save())}>{t(wizard.step < 4 ? 'eco.next' : 'eco.save')}</button>
      </div>
    </div>
  );
};
