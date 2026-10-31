import { useModels } from '@/api/hooks';
import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { displayText } from '@/i18n';
import { useDrafts } from '@/state/ui';
import { useUi } from '@/state/ui';
import { Avatar, Icon } from '@/ui/icons';
import { IconButton, MenuItem, useOverlay } from '@/ui/overlay';
import { agentDescription } from '@/features/home/Home';
import { ModelMenu, modelLabel } from '@/features/tasks/ComposerMenus';
import { ProactiveDialog, ProactiveFooter } from '@/features/shell/dialogs';
import { AgentKnowledge } from '@/features/knowledge/Knowledge';
import { AgentEcosystem } from '@/features/channels/AgentEcosystem';
import { CreateAgentDialog } from './AgentDialogs';

const TABS = ['Instructions', 'Capabilities', 'Work Context', 'Ecosystem', 'Manage'];
const BUILTINS: [string, string, string][] = [['file', '文档与写作', '整理资料、提炼观点，生成专业文档。'], ['globe', '深度调研', '梳理问题，形成完整的研究框架。'], ['code', '代码与开发', '理解代码，协助开发与故障排查。'], ['grid', '数据分析', '清理数据，探索趋势与关键洞察。'], ['play', '演示文稿', '将想法整理成清晰的汇报材料。'], ['users', '团队协作', '拆解任务，协调伙伴与工作进度。']];

function EditTextDialog({ agentId, field }: { agentId: string; field: 'instructions' | 'context' }) {
  const { t, ws } = useWs();
  const agent = ws.agents.find(a => a.id === agentId)!;
  const fallback = field === 'instructions' ? t('ui.defaultInstructions') : t('ui.defaultContext');
  return (
    <label className="form-field"><span>{field === 'instructions' ? t('Instructions') : t('Work context')}</span>
      <textarea id="agent-text" rows={9} style={{ minHeight: 240 }} defaultValue={agent[field] || fallback} />
    </label>
  );
}

EditTextDialog.Footer = function Footer({ agentId, field }: { agentId: string; field: 'instructions' | 'context' }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const value = (document.getElementById('agent-text') as HTMLTextAreaElement).value;
    overlay.close();
    await ctx.run(() => api.update(ctx.tenantId, 'agents', agentId, { [field]: value }), '已保存');
  };
  return (
    <>
      <button className="btn" data-action="close" onClick={overlay.close}>{ctx.t('Cancel')}</button>
      <button className="btn primary" data-action="save-agent-text" data-field={field} onClick={() => void save()}>{ctx.t('Save')}</button>
    </>
  );
};

function AddCapabilityDialog() {
  const { t, runtime } = useWs();
  return (
    <>
      <label className="form-field"><span>{t('Capability name')}</span><input id="capability-name" placeholder={t('e.g. 竞品分析')} maxLength={40} /></label>
      {runtime.simulated ? <p className="prototype-note">{t('将能力添加到当前伙伴的演示配置。')}</p> : null}
    </>
  );
}

AddCapabilityDialog.Footer = function Footer({ agentId }: { agentId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const input = document.getElementById('capability-name') as HTMLInputElement;
    const name = input.value.trim();
    if (!name) { input.focus(); return; }
    overlay.close();
    await ctx.run(() => api.update(ctx.tenantId, 'agents', agentId, { addSkill: name }), '已添加能力');
  };
  return (
    <>
      <button className="btn" data-action="close" onClick={overlay.close}>{ctx.t('Cancel')}</button>
      <button className="btn primary" data-action="save-capability" onClick={() => void save()}>{ctx.t('Add')}</button>
    </>
  );
};

/** Workmate detail (prototype details()). */
export function AgentDetail() {
  const ctx = useWs();
  const { t, ws, routeId, tenantId } = ctx;
  const overlay = useOverlay();
  const models = useModels();
  const { detailTab, set, setDrafts } = useUi();
  const drafts = useDrafts(tenantId);
  const agent = ws.agents.find(a => a.id === routeId) || ws.agents[0];
  const editAgent = () => overlay.modal(t('Edit workmate'), <CreateAgentDialog editId={agent.id} />, <CreateAgentDialog.Footer editId={agent.id} />, { focus: '#agent-form input' });
  const newTask = () => { setDrafts(tenantId, { draft: '' }); ctx.nav('new', agent.id); };
  let body: React.ReactNode = null;
  if (detailTab === 'Instructions') {
    body = <>
      <div className="detail-label"><h2>{t('Instructions')}</h2><button className="btn" data-action="edit-instructions" onClick={() => overlay.modal(t('Edit instructions'), <EditTextDialog agentId={agent.id} field="instructions" />, <EditTextDialog.Footer agentId={agent.id} field="instructions" />)}><Icon name="edit" size={16} />{t('Edit')}</button></div>
      <div className="instruction-box">{agent.instructions || t('ui.defaultInstructions')}</div>
    </>;
  } else if (detailTab === 'Capabilities') {
    const items = [...BUILTINS.map(([ic, title, desc]) => [ic, t(title), t(desc)]), ...(agent.extraSkills || []).map(s => ['layers', s, t('已添加到当前伙伴的演示能力。')])];
    body = <>
      <div className="detail-label"><h2>{t('Skills & tools')}</h2><button className="btn" data-action="add-capability" onClick={() => overlay.modal(t('Add capability'), <AddCapabilityDialog />, <AddCapabilityDialog.Footer agentId={agent.id} />)}><Icon name="plus" size={16} />{t('Add capability')}</button></div>
      <div className="capability-grid">{items.map(([ic, title, desc], i) => <div className="capability-item" key={i}><Icon name={ic} size={22} /><h3>{title}</h3><p>{desc}</p></div>)}</div>
    </>;
  } else if (detailTab === 'Work Context') {
    body = <>
      <div className="detail-label"><h2>{t('Work context')}</h2><button className="btn" data-action="add-context" onClick={() => overlay.modal(t('Edit work context'), <EditTextDialog agentId={agent.id} field="context" />, <EditTextDialog.Footer agentId={agent.id} field="context" />)}><Icon name="plus" size={16} />{t('Add context')}</button></div>
      <p className="muted">{t('给伙伴一些工作背景，让每次协作更有默契。')}</p>
      <div className="instruction-box">{agent.context || t('ui.defaultContext')}</div>
      <AgentKnowledge agentId={agent.id} />
    </>;
  } else if (detailTab === 'Ecosystem') {
    body = <AgentEcosystem agentId={agent.id} />;
  } else if (detailTab === 'Manage') {
    body = <>
      <h2>{t('Workmate settings')}</h2>
      <div className="instruction-box">
        <div className="detail-label"><div>{t('Basic information')}<p className="muted" style={{ fontSize: 12, margin: '4px 0' }}>{t('名称、介绍与伙伴头像')}</p></div><button className="btn" data-action="edit-agent" data-id={agent.id} onClick={editAgent}><Icon name="edit" size={16} />{t('Edit')}</button></div>
        <div className="detail-label"><div>{t('Display on Home')}<p className="muted" style={{ fontSize: 12, margin: '4px 0' }}>{t('当前伙伴已添加至你的工作台')}</p></div><Icon name="checkcircle" size={20} /></div>
      </div>
    </>;
  }
  return (
    <div className="detail-page">
      <div className="breadcrumbs">
        <button data-action="nav" data-page="home" onClick={() => ctx.nav('home')}>{t('Home')}</button><Icon name="chevron" size={12} />
        <button data-action="chat-agent" data-id={agent.id} onClick={newTask}>{agent.name}</button><Icon name="chevron" size={12} />
        <span>{t('Details')}</span>
        <IconButton action="agent-menu" icon="more" label={t('More workmate actions')} data-id={agent.id} style={{ marginLeft: 'auto' }} onClick={e => overlay.popover(e.currentTarget, <>
          <MenuItem action="edit-agent" data-id={agent.id} label={t('Edit workmate')} icon="edit" onClick={() => { overlay.close(); editAgent(); }} />
          <MenuItem action="chat-agent" data-id={agent.id} label={t('New task')} icon="chat" onClick={newTask} />
        </>)} />
      </div>
      <section className="agent-profile">
        <Avatar index={agent.avatar} size={64} />
        <div className="grow">
          <div className="row">
            <h1>{agent.name}</h1>
            {agent.tag ? <span className="tag">{displayText(t, agent.tag)}</span> : null}
            <IconButton action="edit-agent" icon="edit" label={t('Edit basic info')} data-id={agent.id} onClick={editAgent} />
          </div>
          <p>{agentDescription(t, agent)}</p>
          <div className="profile-controls">
            <button className="soft-chip" data-action="select-model" onClick={e => overlay.popover(e.currentTarget, <ModelMenu />)}><Icon name="star" size={12} />{displayText(t, modelLabel(t, drafts.model, models.data))}<Icon name="chevron" size={10} /></button>
            <button className="soft-chip" data-action="proactive" onClick={() => overlay.modal(t('Proactive help'), <ProactiveDialog />, <ProactiveFooter />)}><Icon name="moon" size={12} />{t(ws.tenant.settings.proactive ? 'ui.proactiveOn' : 'ui.proactiveOff')} <Icon name="chevron" size={10} /></button>
          </div>
        </div>
        <div className="profile-cta">
          <button className="btn" data-action="nav" data-page="ecosystem" onClick={() => ctx.nav('ecosystem')}><Icon name="globe" size={16} />{t('workspace.ecosystem')}</button>
          <button className="btn" data-action="chat-agent" data-id={agent.id} onClick={newTask}><Icon name="edit" size={16} />{t('New Task')}</button>
        </div>
      </section>
      <div className="detail-tabs">
        <div className="tabs underlined" role="tablist">
          {TABS.map(tab => (
            <button key={tab} className={`tab-btn ${detailTab === tab ? 'active' : ''}`} role="tab" aria-selected={detailTab === tab} data-action="detail-tab" data-tab={tab} onClick={() => set({ detailTab: tab })}>
              {t(tab === 'Ecosystem' ? 'workspace.ecosystem' : tab)}
            </button>
          ))}
        </div>
      </div>
      <div className="detail-body">{body}</div>
    </div>
  );
}
