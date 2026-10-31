/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { PLATFORMS, platformBy } from '@/domain/ecosystem-model.js';
import { Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { EcoButton } from '@/features/channels/BindingRows';

function ScenarioForm({ id }: { id?: string }) {
  const { t, ws } = useWs();
  const item: any = ws.scenarios.find(s => s.id === id) || {};
  const field = (name: string, label: string, placeholder: string, required = false, multiline = false) => (
    <label className="form-field">
      <span>{t(label)}{required ? null : <> <small className="wx-scene-optional">{t('scene.optional')}</small></>}</span>
      {multiline
        ? <textarea name={name} maxLength={600} required={required} placeholder={t(placeholder)} defaultValue={item[name] || ''} />
        : <input name={name} maxLength={name === 'name' ? 60 : 100} required={required} defaultValue={item[name] || ''} placeholder={t(placeholder)} autoComplete="off" />}
    </label>
  );
  return (
    <form id="scenario-form" data-id={item.id || ''} onSubmit={e => e.preventDefault()}>
      {field('name', 'scene.name', 'scene.namePlaceholder', true)}
      {field('problem', 'scene.problem', 'scene.problemPlaceholder', true, true)}
      {field('role', 'scene.role', 'scene.rolePlaceholder')}
      <div className="wx-scene-form-columns">{field('input', 'scene.input', 'scene.inputPlaceholder', false, true)}{field('output', 'scene.output', 'scene.outputPlaceholder', false, true)}</div>
      <fieldset className="wx-scene-ecosystem-options">
        <legend>{t('scene.ecosystems')}</legend>
        {PLATFORMS.map((p: any) => <label key={p.id}><input type="checkbox" name="ecosystems" value={p.id} defaultChecked={(item.ecosystems || []).includes(p.id)} />{t(p.name)}</label>)}
        <p>{t('scene.ecosystemHint')}</p>
      </fieldset>
      <p className="wx-eco-form-footnote">{t('scene.draftNotice')}</p>
    </form>
  );
}

function useScenarioForm() {
  const ctx = useWs();
  const overlay = useOverlay();
  const open = (id?: string) => overlay.modal(ctx.t(id ? 'scene.editTitle' : 'scene.createTitle'), <ScenarioForm id={id} />, <ScenarioFooter id={id} />, { className: 'wx-scene-modal' });
  return open;
}

function ScenarioFooter({ id }: { id?: string }) {
  const ctx = useWs();
  const { t } = ctx;
  const overlay = useOverlay();
  const openForm = useScenarioForm();
  const required = (form: HTMLFormElement, name: string, key: string) => {
    const field = form.elements.namedItem(name) as HTMLInputElement;
    if (!field.value.trim()) { field.setCustomValidity(t(key)); field.reportValidity(); field.setCustomValidity(''); return false; }
    return true;
  };
  const save = async () => {
    const form = document.getElementById('scenario-form') as HTMLFormElement | null;
    if (!form || !form.reportValidity() || !required(form, 'name', 'scene.requiredName') || !required(form, 'problem', 'scene.requiredProblem')) return;
    const values = new FormData(form);
    const body = { name: values.get('name'), problem: values.get('problem'), role: values.get('role'), input: values.get('input'), output: values.get('output'), ecosystems: values.getAll('ecosystems') };
    const saved = await ctx.run(() => (id ? api.update(ctx.tenantId, 'scenarios', id, body) : api.create(ctx.tenantId, 'scenarios', body)), 'scene.saved');
    if (saved) overlay.close();
  };
  const remove = () => {
    const draft = ctx.ws.scenarios.find(s => s.id === id);
    if (!draft) return;
    overlay.modal(t('scene.deleteTitle'), <p>{t('scene.deleteBody', { name: draft.name })}</p>, <>
      <EcoButton action="scenario-edit" label="eco.cancel" data-id={id} onClick={() => openForm(id)} />
      <EcoButton action="scenario-delete-confirm" label="scene.remove" primary data-id={id} onClick={() => { overlay.close(); void ctx.run(() => api.call('DELETE', `/tenants/${ctx.tenantId}/scenarios/${id}`), 'scene.deleted'); }} />
    </>);
  };
  return (
    <>
      {id ? <button type="button" className="text-btn wx-scene-delete" data-action="scenario-delete" data-id={id} onClick={remove}>{t('scene.remove')}</button> : null}
      <EcoButton action="close" label="eco.cancel" onClick={overlay.close} />
      <EcoButton action="scenario-save" label="scene.save" primary onClick={() => void save()} />
    </>
  );
}

/** Business scenario drafts (prototype renderScenarios). */
export function Scenarios() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const openForm = useScenarioForm();
  const drafts: any[] = ws.scenarios;
  const create = <EcoButton action="scenario-create" label="scene.record" icon="plus" primary onClick={() => openForm()} />;
  return (
    <section className="wx-scene-page">
      <header className="wx-eco-heading">
        <div><div className="wx-scene-title-line"><h1>{t('scene.title')}</h1><span className="wx-eco-header-badge">{t('scene.reserved')}</span></div><p>{t('scene.subtitle')}</p></div>
        {create}
      </header>
      {drafts.length ? (
        <>
          <div className="wx-scene-list-heading"><h2>{t('scene.drafts')}</h2><span>{t('scene.draftCount', { count: drafts.length })}</span></div>
          <div className="wx-scene-list">
            {drafts.map(draft => (
              <article key={draft.id} className="wx-scene-draft">
                <div className="wx-scene-draft-icon"><Icon name="grid" size={21} /></div>
                <div className="wx-scene-draft-body">
                  <div className="wx-scene-draft-title"><h3>{draft.name}</h3><span className="wx-scene-draft-tag">{t('scene.draft')}</span></div>
                  <p>{draft.problem}</p>
                  <div className="wx-scene-draft-meta">
                    <span><Icon name="users" size={13} />{draft.role || t('scene.rolePending')}</span>
                    <span><Icon name="globe" size={13} />{(draft.ecosystems || []).filter((id: string) => platformBy(id)).map((id: string) => t(platformBy(id).name)).join(' · ') || t('scene.ecosystemPending')}</span>
                  </div>
                </div>
                <button type="button" className="btn" data-action="scenario-edit" data-id={draft.id} aria-label={t('scene.editNamed', { name: draft.name })} onClick={() => openForm(draft.id)}><Icon name="edit" size={14} />{t('scene.edit')}</button>
              </article>
            ))}
          </div>
          <p className="wx-scene-draft-note"><Icon name="help" size={14} />{t('scene.draftNotice')}</p>
        </>
      ) : (
        <div className="wx-scene-empty">
          <div className="wx-scene-empty-art" aria-hidden="true"><span><Icon name="users" size={24} /></span><i /><span className="wx-scene-empty-core"><Icon name="grid" size={34} /></span><i /><span><Icon name="robot" size={24} /></span></div>
          <span className="wx-scene-empty-kicker">{t('scene.emptyHint')}</span>
          <h2>{t('scene.emptyTitle')}</h2>
          <p>{t('scene.emptyBody')}</p>
          {create}
        </div>
      )}
      <div className="wx-scene-flow">{[1, 2, 3, 4].map(step => <div key={step}><span>0{step}</span><p>{t('scene.flow' + step)}</p></div>)}</div>
      <div className="wx-scene-footer"><span>{t('scene.draftNotice')}</span><button type="button" className="text-btn" data-action="nav" data-page="ecosystem" onClick={() => ctx.nav('ecosystem')}>{t('scene.ecosystemLink')}<Icon name="arrow" size={15} /></button></div>
    </section>
  );
}
