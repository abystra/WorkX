import { useWs } from '@/app/workspace';
import { Icon } from '@/ui/icons';
import { BindingRows, EcoButton, useOpenWizard } from './BindingRows';

/** Ecosystem tab on a workmate (prototype renderAgentEcosystem). */
export function AgentEcosystem({ agentId }: { agentId: string }) {
  const { t, ws } = useWs();
  const openWizard = useOpenWizard();
  const bindings = ws.bindings.filter(b => b.assignedAgent === agentId);
  return (
    <section className="wx-eco-agent-section">
      <div className="wx-eco-section-heading">
        <div><h2>{t('eco.agentBindings')}</h2><p>{t('eco.agentBindingsHint')}</p></div>
        <EcoButton action="eco-add" label="eco.add" icon="plus" data-agent={agentId} onClick={() => openWizard({ agent: agentId })} />
      </div>
      {bindings.length ? <BindingRows bindings={bindings} /> : <div className="wx-eco-agent-empty"><Icon name="globe" size={22} /><p>{t('eco.agentEmpty')}</p></div>}
    </section>
  );
}
