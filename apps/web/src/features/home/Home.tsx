import { api } from '@/api/client';
import type { Agent } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { displayText } from '@/i18n';
import { useUi } from '@/state/ui';
import { Avatar, Icon } from '@/ui/icons';
import { IconButton, useOverlay } from '@/ui/overlay';
import { CreateMenu } from '@/features/shell/menus';
import { CreateAgentDialog } from '@/features/agents/AgentDialogs';
import { TaskSection } from '@/features/tasks/TaskSection';
import { SUGGESTIONS } from '@/features/tasks/suggestions';
import { runIsActive, runNeedsAttention } from '@/features/channels/platforms';

export function agentDescription(t: (k: string) => string, a: Agent) {
  return a.description === 'No description yet' ? t('No description yet') : a.description;
}

export function AgentCard({ agent }: { agent: Agent }) {
  const ctx = useWs();
  const { t } = ctx;
  const setDrafts = useUi(s => s.setDrafts);
  return (
    <article className="agent-card" tabIndex={0} role="button" aria-label={t('ui.viewAgent', { name: agent.name })} data-action="agent-detail" data-id={agent.id}
      onClick={() => ctx.nav('detail', agent.id)}>
      <div className="agent-card-top">
        <Avatar index={agent.avatar} size={36} />
        <span className="agent-card-name" title={agent.name}>{agent.name}</span>
        <button className="chat-button" data-action="chat-agent" data-id={agent.id} aria-label={t('ui.chatAgent', { name: agent.name })}
          onClick={e => { e.stopPropagation(); setDrafts(ctx.tenantId, { draft: '' }); ctx.nav('new', agent.id); }}>
          <Icon name="chat" size={16} />
        </button>
      </div>
      <div className="agent-desc">{agentDescription(t, agent)}</div>
      <div className="agent-meta">
        <span><Icon name="chat" size={12} />{agent.tasks}</span>
        <span><Icon name={agent.tag === 'Squads' ? 'users' : 'layers'} size={12} />{agent.skills}</span>
        {agent.tag ? <span className="tag">{displayText(t, agent.tag)}</span> : null}
      </div>
    </article>
  );
}

function HomeTeam() {
  const ctx = useWs();
  const { t, ws, current } = ctx;
  const personal = current.type === 'personal';
  return (
    <section className="wx-team-home">
      <div className="wx-team-home-heading">
        <div>
          <span className="wx-team-eyebrow">{t('spaces.' + current.type)}</span>
          <h1>{t(personal ? 'spaces.homePersonal' : 'spaces.homeOrg')}</h1>
          <p>{t(personal ? 'spaces.homePersonalHint' : 'spaces.homeOrgHint')}</p>
        </div>
        <button className="text-btn" data-action="nav" data-page={personal ? 'settings' : 'team'} data-id="general" onClick={() => ctx.nav(personal ? 'settings' : 'team', 'general')}>
          {t(personal ? 'spaces.settings' : 'spaces.manage')}<Icon name="chevron" size={13} />
        </button>
      </div>
      <div className="wx-team-home-footer">
        <div className="wx-team-home-counts">
          <span><Icon name="robot" size={14} />{t('spaces.agentCount', { count: ws.agents.length })}</span>
          <span><Icon name="folder" size={14} />{t('team.projectCount', { count: ws.projects.length })}</span>
          {!personal ? <span><Icon name="users" size={14} />{t('team.memberCount', { count: ws.members.length })}</span> : null}
        </div>
        <button className="text-btn" data-action="nav" data-page="team" data-id="data" onClick={() => ctx.nav('team', 'data')}>{t('spaces.data')}<Icon name="arrow" size={14} /></button>
      </div>
    </section>
  );
}

function WorkspaceEntries() {
  const ctx = useWs();
  const { t } = ctx;
  return (
    <div className="workspace-entry-strip">
      <button className="workspace-entry" data-action="nav" data-page="ecosystem" onClick={() => ctx.nav('ecosystem')}>
        <Icon name="globe" size={23} />
        <div className="workspace-entry-copy"><strong>{t('workspace.ecosystem')} · {t('workspace.ecosystemIntro')}</strong><p>{t('workspace.ecosystemPlatforms')}</p></div>
        <Icon name="chevron" size={14} />
      </button>
      <button className="workspace-entry" data-action="nav" data-page="scenarios" onClick={() => ctx.nav('scenarios')}>
        <Icon name="grid" size={23} />
        <div className="workspace-entry-copy"><strong>{t('workspace.scenarios')} · {t('workspace.scenarioIntro')}</strong><p>{t('workspace.scenarioStatus')}</p></div>
        <Icon name="chevron" size={14} />
      </button>
    </div>
  );
}

function ChannelHome() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const runs = ws.channelRuns;
  const counts: [string, number][] = [['active', runs.filter(r => runIsActive(r.stage)).length], ['attention', runs.filter(r => runNeedsAttention(r.stage)).length], ['delivered', runs.filter(r => r.stage === 'delivered').length]];
  return (
    <section className="wx-channel-home">
      <div><Icon name="chat" size={20} /><div><strong>{t('channel.title')}</strong><p>{t('channel.homeHint')}</p></div></div>
      <div className="wx-channel-home-counts">{counts.map(([key, count]) => <span key={key}><strong>{count}</strong>{t('channel.count.' + key)}</span>)}</div>
      <button type="button" className="btn" data-action="nav" data-page="inbox" onClick={() => ctx.nav('inbox')}>{t('channel.openWorkbench')}</button>
    </section>
  );
}

function QuickStart() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const { recommendation, set, setDrafts } = useUi();
  const agentBy = (id: string) => ws.agents.find(a => a.id === id) || ws.agents[0];
  return (
    <section className="quick-section">
      <div className="section-heading">
        <h2>{t('Quick start')}</h2>
        <button className="text-btn" data-action="hide-quick" onClick={() => void ctx.run(() => api.updateTenant(ctx.tenantId, { hideQuick: true }), '已隐藏 Quick start，可在工作空间菜单中恢复')}>{t("Don't Show Again")}</button>
      </div>
      <div className="quick-grid">
        <div className="quick-card quick-add">
          <h3>{t('Add more Workmates')}</h3>
          <p>{t('Find skilled Workmates ready to work for you.')}</p>
          <button className="quick-action" data-action="nav" data-page="hub" onClick={() => ctx.nav('hub')}><Icon name="grid" size={15} />{t('Browse Workmates')}</button>
          <button className="quick-action" data-action="create-agent" onClick={() => overlay.modal(t('Create a Workmate'), <CreateAgentDialog />, <CreateAgentDialog.Footer />, { focus: '#agent-form input' })}>
            <Icon name="users" size={17} />{t('Create a Workmate')}
          </button>
        </div>
        <div className="quick-card">
          <div className="quick-card-head">
            <h3>{t('Kick off a task')}</h3>
            <IconButton action="refresh-recommendations" icon="refresh" label={t('Refresh recommendations')} onClick={() => set({ recommendation: (recommendation + 3) % SUGGESTIONS.length })} />
          </div>
          {[0, 1, 2].map(n => {
            const idx = (n + recommendation) % SUGGESTIONS.length, s = SUGGESTIONS[idx];
            return (
              <button key={idx} className="recommendation" data-action="suggestion" data-index={String(idx)}
                onClick={() => {
                  setDrafts(ctx.tenantId, { draft: t('suggestion.' + idx), capabilities: s.label === 'Slides' || s.label === 'Deep Research' ? [s.label] : [] });
                  ctx.nav('new', s.agent);
                }}>
                <Avatar index={agentBy(s.agent).avatar} size={20} /><span>{t('suggestion.' + idx)}</span><Icon name="arrow" size={15} />
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function Home() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  return (
    <div className="home-page">
      <HomeTeam />
      <WorkspaceEntries />
      <ChannelHome />
      <section>
        <div className="section-heading">
          <h2>{t('Workmates and squads')}</h2>
          <div className="heading-actions">
            <button className="text-btn" data-action="create-menu" onClick={e => overlay.popover(e.currentTarget, <CreateMenu />)}><Icon name="plus" size={14} />{t('Create')}</button>
            <span className="divider" />
            <button className="text-btn" data-action="nav" data-page="hub" onClick={() => ctx.nav('hub')}>{t('All')} <Icon name="chevron" size={11} /></button>
          </div>
        </div>
        <div className="agents-grid">{ws.agents.map(agent => <AgentCard key={agent.id} agent={agent} />)}</div>
      </section>
      {!ws.tenant.settings.hideQuick ? <QuickStart /> : null}
      <TaskSection />
    </div>
  );
}
