import { useModels } from '@/api/hooks';
import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { displayText } from '@/i18n';
import { useDrafts, useUi } from '@/state/ui';
import { Icon } from '@/ui/icons';
import { IconButton, useOverlay } from '@/ui/overlay';
import { AttachMenu, ModelMenu, MoreCapabilitiesMenu, ProjectMenu, VoiceDialog, modelLabel } from './ComposerMenus';

/** Starts a task (prototype startTask) and opens its conversation. */
export async function startTask(ctx: ReturnType<typeof useWs>, prompt: string, kind: 'work' | 'code' = 'work', projectId?: string) {
  const text = prompt.trim();
  if (!text) return;
  const ui = useUi.getState();
  const drafts = ui.drafts[ctx.tenantId] || { agent: '', selectedProject: '', attachment: '', model: 'Auto', capabilities: [] };
  const task = await ctx.run(() => api.create(ctx.tenantId, 'tasks', {
    prompt: text, kind, agentId: drafts.agent || ctx.ws.agents[0]?.id, projectId: projectId ?? drafts.selectedProject,
    attachment: drafts.attachment, model: drafts.model || 'Auto', capabilities: drafts.capabilities,
  }));
  if (!task) return;
  ui.setDrafts(ctx.tenantId, kind === 'code' ? { draft: '', attachment: '', codeDraft: '', codeProject: '' } : { draft: '', attachment: '' });
  ctx.nav('task', task.id);
}

/** Task composer (prototype composer()); `followup` is used inside a conversation. */
export function Composer({ followup = false }: { followup?: boolean }) {
  const ctx = useWs();
  const { t, ws, tenantId } = ctx;
  const overlay = useOverlay();
  const models = useModels();
  const drafts = useDrafts(tenantId);
  const setDrafts = useUi(s => s.setDrafts);
  const project = ws.projects.find(p => p.id === drafts.selectedProject);
  const send = async () => {
    if (!drafts.draft.trim()) return;
    if (ctx.page === 'task' && ctx.routeId) {
      const prompt = drafts.draft.trim();
      setDrafts(tenantId, { draft: '', attachment: '' });
      await ctx.run(() => api.sendMessage(tenantId, ctx.routeId!, prompt));
    } else {
      await startTask(ctx, drafts.draft);
    }
  };
  return (
    <div className="composer">
      {drafts.attachment ? (
        <div className="attachment-pill"><Icon name="file" size={14} />{drafts.attachment}<IconButton action="remove-attachment" icon="close" label={t('Remove attachment')} onClick={() => setDrafts(tenantId, { attachment: '' })} /></div>
      ) : null}
      <textarea id="task-prompt" aria-label={t('Task or goal')} placeholder={t(followup ? 'Ask a follow-up…' : "What's your task or goal?")} rows={2} value={drafts.draft}
        onChange={e => setDrafts(tenantId, { draft: e.target.value })} />
      <div className="composer-bottom">
        <IconButton action="attach-menu" icon="plus" label={t('Add attachment')} onClick={e => overlay.popover(e.currentTarget, <AttachMenu />)} />
        <span className="separator" />
        <button className="chip-btn" data-action="select-project" onClick={e => overlay.popover(e.currentTarget, <ProjectMenu />)}>
          <Icon name="folder" size={15} /><span>{project?.name || t('Select project')}</span><Icon name="chevron" size={10} />
        </button>
        {['Slides', 'Deep Research'].map((c, n) => (
          <button key={c} className={`chip-btn capability-chip ${drafts.capabilities.includes(c) ? 'active' : ''}`} data-action="capability" data-value={c}
            onClick={() => setDrafts(tenantId, { capabilities: drafts.capabilities.includes(c) ? drafts.capabilities.filter(x => x !== c) : [...drafts.capabilities, c] })}>
            <Icon name={n ? 'globe' : 'file'} size={15} />{t(c)}
          </button>
        ))}
        <button className="chip-btn more-cap" data-action="more-capabilities" onClick={e => overlay.popover(e.currentTarget, <MoreCapabilitiesMenu />)}><Icon name="grid" size={15} />{t('More')}</button>
        <button className="chip-btn model" data-action="select-model" onClick={e => overlay.popover(e.currentTarget, <ModelMenu />)}>
          {displayText(t, modelLabel(t, drafts.model, models.data))}<Icon name="chevron" size={10} />
        </button>
        <IconButton action="voice" icon="mic" label={t('Voice input')} className="mic-control" onClick={() => overlay.modal(t('Voice input'), <VoiceDialog />, <VoiceDialog.Footer />)} />
        <button className="send-btn" data-action="send-task" aria-label={t('Send task')} disabled={!drafts.draft.trim()} onClick={() => void send()}><Icon name="arrow" size={23} /></button>
      </div>
    </div>
  );
}
