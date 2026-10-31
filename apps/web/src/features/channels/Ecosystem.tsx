/* eslint-disable @typescript-eslint/no-explicit-any */
import { useWs } from '@/app/workspace';
import { METHODS, PLATFORMS } from '@/domain/ecosystem-model.js';
import { Icon } from '@/ui/icons';
import { BindingRows, EcoButton, PlatformMark, useOpenWizard } from './BindingRows';

/** Ecosystem page (prototype renderEcosystem). */
export function Ecosystem() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const openWizard = useOpenWizard();
  const bindings = ws.bindings;
  return (
    <section className="wx-eco-page">
      <header className="wx-eco-heading">
        <div><h1>{t('eco.title')}</h1><p>{t('eco.subtitle')}</p></div>
        <EcoButton action="eco-add" label="eco.add" icon="plus" primary onClick={() => openWizard()} />
      </header>
      <div className="wx-eco-notice"><Icon name="help" size={17} /><p>{t('eco.notice')}</p></div>
      <div className="wx-eco-section-heading"><h2>{t('eco.platforms')}</h2><span>{t('eco.platformHint')}</span></div>
      <div className="wx-eco-grid">
        {PLATFORMS.map((platform: any) => (
          <article key={platform.id} className="wx-eco-card">
            <div className="wx-eco-card-top">
              <PlatformMark platform={platform} />
              <div className="wx-eco-card-name"><h2>{t(platform.name)}</h2><span>{t(platform.type)}</span></div>
              <span className="wx-eco-platform-count">{t('eco.bindingCount', { count: bindings.filter(b => b.platform === platform.id).length })}</span>
            </div>
            <p className="wx-eco-description">{t(platform.description)}</p>
            <ul className="wx-eco-method-list">
              {METHODS.filter((m: any) => m.platform === platform.id).map((m: any) => <li key={m.id}><span>{t(m.name)}</span><small>{t('eco.kind.' + m.kind)}</small></li>)}
            </ul>
            <div className="wx-eco-card-actions"><EcoButton action="eco-add" label="eco.addPlatform" icon="plus" data-platform={platform.id} onClick={() => openWizard({ platform: platform.id })} /></div>
          </article>
        ))}
      </div>
      <div className="wx-eco-section-heading wx-eco-bindings-heading"><h2>{t('eco.myBindings')}</h2><span>{t('eco.bindingCount', { count: bindings.length })}</span></div>
      {bindings.length ? <BindingRows bindings={bindings} /> : (
        <div className="wx-eco-empty">
          <Icon name="layers" size={26} /><h3>{t('eco.emptyTitle')}</h3><p>{t('eco.emptyBody')}</p>
          <EcoButton action="eco-add" label="eco.add" icon="plus" onClick={() => openWizard()} />
        </div>
      )}
      <aside className="wx-eco-extension">
        <span className="wx-eco-extension-icon"><Icon name="hub" size={25} /></span>
        <div><h2>{t('eco.extensionTitle')}</h2><p>{t('eco.extensionBody')}</p></div>
        <button type="button" className="text-btn" data-action="nav" data-page="scenarios" onClick={() => ctx.nav('scenarios')}>{t('eco.openScenarios')}<Icon name="arrow" size={15} /></button>
      </aside>
    </section>
  );
}
