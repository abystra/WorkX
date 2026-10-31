/* eslint-disable @typescript-eslint/no-explicit-any */
import type { ReactNode } from 'react';
import { api } from '@/api/client';
import type { EcosystemBinding } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { bindingIsReady, capabilityBy, methodBy, platformBy } from '@/domain/ecosystem-model.js';
import { connectionSignature } from '@/domain/connection-model.js';
import { channelBindingReady } from '@/domain/channel-rules';
import { Avatar, Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { useChannelUi } from './store';
import { EcosystemWizard } from './EcosystemWizard';
import { openConnection } from './ConnectionDialog';
import { openCompose } from './ComposeDialog';

/** ecosystem.js button(): type=button, optional 15px icon. */
export function EcoButton({ action, label, icon, primary = false, onClick, disabled, title, ...rest }: {
  action: string; label: string; icon?: string; primary?: boolean; onClick?: () => void; disabled?: boolean; title?: string;
} & Record<`data-${string}`, string | undefined>) {
  const { t } = useWs();
  return (
    <button type="button" className={`btn${primary ? ' primary' : ''}`} data-action={action} onClick={onClick} disabled={disabled} title={title} {...rest}>
      {icon ? <Icon name={icon} size={15} /> : null}{t(label)}
    </button>
  );
}

export function PlatformMark({ platform }: { platform: { id: string; icon: string } }) {
  return <span className={`wx-eco-mark wx-eco-mark-${platform.id}`} aria-hidden="true"><Icon name={platform.icon} size={23} /></span>;
}

export const statusKey = (binding: any, data: any) => (!bindingIsReady(binding, data) ? 'eco.needsReview' : binding.enabled === false ? 'eco.paused' : 'eco.configured');

export function CapabilityTags({ binding }: { binding: any }) {
  const { t } = useWs();
  const caps = (Array.isArray(binding.capabilities) ? binding.capabilities : []).filter((id: string) => capabilityBy(id));
  return caps.length
    ? <>{caps.map((id: string) => <span key={id} className="wx-eco-cap-tag">{t(capabilityBy(id).name)}<small>{t('eco.authPending')}</small></span>)}</>
    : <span className="wx-eco-muted">{t('eco.capabilitiesPending')}</span>;
}

/** connection.js renderConnectionStatus(). */
export function ConnectionStatus({ binding }: { binding: any }) {
  const { t } = useWs();
  const saved = binding.connection;
  if (!saved || saved.signature !== connectionSignature(binding)) return <span className="wx-conn-summary">{t('conn.notConfigured')}</span>;
  const outcome = saved.test?.simulated ? saved.test.outcome : null;
  const key = outcome === 'success' ? 'conn.savedPassed' : outcome ? 'conn.savedFailed' : 'conn.savedUntested';
  return <span className={`wx-conn-summary${outcome === 'success' ? ' is-passed' : ''}`}>{t(key)}</span>;
}

/** Opens the four-step binding wizard (prototype newWizard). */
export function useOpenWizard() {
  const { t } = useWs();
  const overlay = useOverlay();
  const set = useChannelUi(s => s.set);
  return (options: { binding?: EcosystemBinding; platform?: string; agent?: string } = {}) => {
    const binding = options.binding as any, platform = binding?.platform || options.platform || '';
    const draft = binding ? { ...binding, capabilities: [...(binding.capabilities || [])] } : { platform, method: '', name: '', assignedAgent: options.agent || '', capabilities: [], enabled: true, transport: 'websocket' };
    set({ wizard: { step: binding ? 1 : platform ? 2 : 1, editingId: binding?.id || null, draft, error: '' } });
    overlay.modal(t(binding ? 'eco.editBinding' : 'eco.add'), <EcosystemWizard />, <EcosystemWizard.Footer />, { className: 'wx-eco-wizard' });
  };
}

function PreviewDialog({ bindingId }: { bindingId: string }) {
  const { t, ws } = useWs();
  const binding: any = ws.bindings.find(b => b.id === bindingId);
  if (!binding) return null;
  const method = methodBy(binding.method), platform = platformBy(binding.platform), agent = ws.agents.find(a => a.id === binding.assignedAgent);
  const kind = method?.kind, ready = bindingIsReady(binding, ws);
  const node = (icon: ReactNode, label: string, name: string) => <div>{icon}<span>{t(label)}</span><strong>{name}</strong></div>;
  const arrow = <span className="wx-eco-preview-arrow" aria-hidden="true"><Icon name="arrow" size={18} /></span>;
  const mate = node(agent ? <Avatar index={agent.avatar} size={40} /> : <Icon name="robot" size={28} />, 'eco.agent', agent?.name || t('eco.notAssigned'));
  const platformNode = node(<PlatformMark platform={platform} />, kind === 'notification' ? 'eco.notificationTarget' : kind === 'tools' ? 'eco.toolTarget' : 'eco.previewEntry', t(platform.name));
  const flow = !kind ? null : kind === 'dialogue'
    ? <>{platformNode}<span className="wx-eco-preview-arrow" aria-hidden="true">↔</span>{mate}{arrow}{node(<span className="wx-eco-mark"><Icon name="folder" size={23} /></span>, 'eco.previewResult', 'WorkX')}</>
    : <>{mate}{arrow}{platformNode}</>;
  return (
    <>
      <h3 className="wx-eco-preview-name">{binding.name || t('eco.unnamed')}</h3>
      <p className="wx-eco-preview-intro">{t(kind ? 'eco.preview.' + kind : 'eco.reviewBeforePreview')}</p>
      {flow ? <div className="wx-eco-preview-flow">{flow}</div> : null}
      <div className="wx-eco-preview-caps"><CapabilityTags binding={binding} /></div>
      <div className="wx-eco-form-note"><strong>{t(statusKey(binding, ws))}</strong><p>{t(!ready ? 'eco.reviewBeforePreview' : binding.enabled === false ? 'eco.pausedHint' : 'eco.previewLocalNote')}</p></div>
      <p className="wx-eco-form-footnote">{t('eco.authHint')}</p>
    </>
  );
}

function PreviewFooter({ bindingId }: { bindingId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const openWizard = useOpenWizard();
  const binding: any = ctx.ws.bindings.find(b => b.id === bindingId);
  if (!binding) return null;
  const ready = bindingIsReady(binding, ctx.ws), active = ready && binding.enabled !== false, kind = methodBy(binding.method)?.kind;
  return (
    <>
      <EcoButton action="close" label="eco.close" onClick={overlay.close} />
      {!ready ? <EcoButton action="eco-edit" label="eco.editBinding" primary data-id={binding.id} onClick={() => openWizard({ binding })} />
        : active && kind === 'dialogue' ? <EcoButton action="eco-try-task" label="eco.tryTask" primary data-id={binding.id} onClick={() => ctx.nav('new', binding.assignedAgent)} /> : null}
    </>
  );
}

function DeleteFooter({ bindingId }: { bindingId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  return (
    <>
      <EcoButton action="close" label="eco.cancel" onClick={overlay.close} />
      <EcoButton action="eco-delete-confirm" label="eco.delete" primary data-id={bindingId} onClick={() => { overlay.close(); void ctx.run(() => api.call('DELETE', `/tenants/${ctx.tenantId}/channel-bindings/${bindingId}`), 'eco.deleted'); }} />
    </>
  );
}

/** Binding list (prototype bindingRows). */
export function BindingRows({ bindings }: { bindings: EcosystemBinding[] }) {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const openWizard = useOpenWizard();
  return (
    <div className="wx-eco-bindings">
      {bindings.map((binding: any) => {
        const platform = platformBy(binding.platform), method = methodBy(binding.method), agent = ws.agents.find(a => a.id === binding.assignedAgent);
        const ready = bindingIsReady(binding, ws);
        const toggle = async () => {
          const enabling = binding.enabled === false;
          await ctx.run(() => api.call('PATCH', `/tenants/${ctx.tenantId}/channel-bindings/${binding.id}`, { enabled: enabling }), enabling ? 'eco.enabled' : 'eco.disabled');
        };
        return (
          <article key={binding.id} className="wx-eco-binding">
            <div className="wx-eco-binding-main">
              <div className="wx-eco-binding-heading">
                {platform ? <PlatformMark platform={platform} /> : null}
                <div><h3>{binding.name || t('eco.unnamed')}</h3><p>{platform ? t(platform.name) : t('eco.platformPending')}<span> / </span>{method ? t(method.name) : t('eco.modeUndecided')}</p></div>
                <span className={`wx-eco-status${ready && binding.enabled !== false ? ' is-configured' : ''}`}>{t(statusKey(binding, ws))}</span>
              </div>
              <div className="wx-eco-binding-details">
                <div className="wx-eco-binding-agent"><span>{t('eco.agent')}</span>{agent ? <><Avatar index={agent.avatar} size={24} /><strong>{agent.name}</strong></> : <strong>{t('eco.notAssigned')}</strong>}</div>
                <div className="wx-eco-binding-caps"><span>{t('eco.requestedCapabilities')}</span><div><CapabilityTags binding={binding} /></div></div>
              </div>
              <ConnectionStatus binding={binding} />
            </div>
            <div className="wx-eco-binding-actions">
              {method?.kind === 'dialogue' && ctx.runtime.simulated ? (
                <EcoButton action="channel-compose" label="workspace.simulateMessage" data-binding={binding.id} disabled={!channelBindingReady(binding, ws)} title={channelBindingReady(binding, ws) ? undefined : t('workspace.channelRequiresSetup')}
                  onClick={() => openCompose(ctx, overlay, binding.id)} />
              ) : null}
              {ready ? <EcoButton action="conn-open" label="conn.open" icon="settings" data-id={binding.id} onClick={() => openConnection(ctx, overlay, binding.id)} /> : null}
              <EcoButton action="eco-edit" label="eco.edit" icon="edit" data-id={binding.id} onClick={() => openWizard({ binding })} />
              <EcoButton action="eco-preview" label="eco.preview" icon="play" data-id={binding.id} onClick={() => overlay.modal(t('eco.previewTitle', { platform: t(platform?.name || '') }), <PreviewDialog bindingId={binding.id} />, <PreviewFooter bindingId={binding.id} />)} />
              {ready || binding.enabled !== false ? <EcoButton action="eco-toggle" label={binding.enabled === false ? 'eco.enable' : 'eco.disable'} data-id={binding.id} onClick={() => void toggle()} /> : null}
              <button type="button" className="text-btn wx-eco-delete" data-action="eco-delete" data-id={binding.id} aria-label={t('eco.deleteNamed', { name: binding.name })}
                onClick={() => overlay.modal(t('eco.deleteTitle'), <p className="wx-eco-preview-intro">{t('eco.deleteBody', { name: binding.name })}</p>, <DeleteFooter bindingId={binding.id} />)}>
                {t('eco.delete')}
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
