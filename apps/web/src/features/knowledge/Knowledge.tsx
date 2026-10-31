import { api } from '@/api/client';
import type { KnowledgeSource } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { Checks } from '@/features/projects/ProjectDialogs';
import { Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';

// Knowledge sources (approved placement Q-15 / decision 30): a section in Workmate "Work Context" and a
// Library filter, no new sidebar item. New UI without a prototype reference (apps/web/docs/NEW-SCREENS.md).

/** Status tag; reuses the channel status tag colors (Part 15 §4.3). */
export function KnowledgeStatusTag({ source }: { source: KnowledgeSource }) {
  const { t } = useWs();
  const tone = source.status === 'ready' ? 'is-delivered' : source.status === 'failed' ? 'is-execution_failed' : 'is-running';
  return <span className={`wx-channel-status wx-knowledge-status ${tone}`}>{t('web.knowledge.status.' + source.status)}</span>;
}

function AttachKnowledgeDialog({ agentId }: { agentId: string }) {
  const { t, ws } = useWs();
  const agent = ws.agents.find(a => a.id === agentId);
  const attachedFiles = ws.knowledge.filter(k => agent?.knowledgeSourceIds?.includes(k.id)).map(k => k.fileId);
  const files = ws.library.map(f => ({ id: f.id, name: f.name || t('sec.untitled') }));
  return (
    <form id="knowledge-form" onSubmit={e => e.preventDefault()}>
      <p className="muted wx-knowledge-intro">{t('web.knowledge.dialogIntro')}</p>
      {files.length ? (
        <fieldset className="wx-team-fieldset"><legend>{t('sec.library')}</legend>
          <Checks items={files} selected={attachedFiles} name="files" image={() => <Icon name="file" size={16} />} />
        </fieldset>
      ) : <p className="muted">{t('web.knowledge.noFiles')}</p>}
    </form>
  );
}

AttachKnowledgeDialog.Footer = function Footer({ agentId }: { agentId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const form = document.getElementById('knowledge-form') as HTMLFormElement | null;
    if (!form) return;
    const fileIds = new FormData(form).getAll('files').map(String);
    const done = await ctx.run(async () => {
      // One source per file; creating is idempotent, so re-saving keeps existing sources and their status.
      const sources = await Promise.all(fileIds.map(fileId => api.createKnowledgeSource(ctx.tenantId, fileId)));
      return api.setAgentKnowledge(ctx.tenantId, agentId, sources.map(s => s.id));
    }, 'web.knowledge.saved');
    if (done) overlay.close();
  };
  return (
    <>
      <button type="button" className="btn" data-action="close" onClick={overlay.close}>{ctx.t('Cancel')}</button>
      <button type="button" className="btn primary" data-action="knowledge-save" onClick={() => void save()}>{ctx.t('web.knowledge.save')}</button>
    </>
  );
};

/** "Knowledge" section of the Work Context tab. */
export function AgentKnowledge({ agentId }: { agentId: string }) {
  const ctx = useWs();
  const { t, ws, runtime } = ctx;
  const overlay = useOverlay();
  const agent = ws.agents.find(a => a.id === agentId);
  if (!agent) return null;
  const sources = (agent.knowledgeSourceIds || []).map(id => ws.knowledge.find(k => k.id === id)).filter((k): k is KnowledgeSource => !!k);
  const open = () => overlay.modal(t('web.knowledge.dialogTitle'), <AttachKnowledgeDialog agentId={agentId} />, <AttachKnowledgeDialog.Footer agentId={agentId} />);
  const remove = (id: string) => void ctx.run(() => api.setAgentKnowledge(ctx.tenantId, agentId, sources.map(s => s.id).filter(x => x !== id)), 'web.knowledge.saved');
  return (
    <section className="wx-knowledge" aria-labelledby="knowledge-title">
      <div className="detail-label"><h2 id="knowledge-title">{t('web.knowledge.title')}</h2><button className="btn" data-action="knowledge-attach" onClick={open}><Icon name="plus" size={16} />{t('web.knowledge.attach')}</button></div>
      <p className="muted">{t('web.knowledge.intro')}</p>
      {sources.length ? (
        <ul className="wx-knowledge-list">
          {sources.map(source => (
            <li key={source.id} className="wx-knowledge-row">
              <Icon name="file" size={16} />
              <span className="wx-knowledge-name ellipsis">{source.name}</span>
              <KnowledgeStatusTag source={source} />
              <button type="button" className="text-btn" data-action="knowledge-remove" data-id={source.id} aria-label={t('web.knowledge.removeNamed', { name: source.name })} onClick={() => remove(source.id)}>{t('web.knowledge.remove')}</button>
            </li>
          ))}
        </ul>
      ) : <div className="instruction-box wx-knowledge-empty">{t('web.knowledge.empty')}</div>}
      {runtime.simulated ? <p className="prototype-note">{t('web.knowledge.simulated')}</p> : null}
    </section>
  );
}
