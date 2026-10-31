import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { useDrafts, useUi } from '@/state/ui';
import { Avatar, Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { CreateProjectDialog } from '@/features/projects/ProjectDialogs';
import { showFile } from '@/features/library/FileDialog';
import { startTask } from '@/features/tasks/Composer';
import { CreateAutomationDialog } from './AutomationDialog';
import { SecondaryEmpty, SecondaryHeader, dateText, scheduleText } from './common';
import { KnowledgeStatusTag } from '@/features/knowledge/Knowledge';

const CATEGORY: Record<string, string> = { Personal: 'sec.personal', Team: 'sec.team', 'Third-party': 'sec.thirdParty', Squads: 'sec.squads', Workmate: 'sec.workmate' };

export function Hub() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const { hubFilter: filter, secondaryQuery: query, set } = useUi();
  const q = query.toLowerCase();
  const agents = ws.agents.filter(a => (filter === 'all' || String(a.tag || 'Team').toLowerCase() === filter) && `${a.name} ${a.description === 'No description yet' ? t('No description yet') : a.description || ''}`.toLowerCase().includes(q));
  return (
    <div className="secondary-page sw-page-hub">
      <SecondaryHeader name="sec.hub" description="sec.hub.description" />
      <div className="sw-hub-intro">
        <span className="sw-hub-intro-icon"><Icon name="users" size={29} /></span>
        <div><div className="sw-eyebrow">{t('sec.hub.eyebrow')}</div><h2>{t('sec.hub.tagline')}</h2><p>{t('sec.hub.intro')}</p></div>
      </div>
      <div className="sw-hub-toolbar">
        <div className="sw-search"><Icon name="search" size={16} /><input data-secondary-search="" value={query} placeholder={t('sec.hub.search')} aria-label={t('sec.hub.search')} autoComplete="off" onChange={e => set({ secondaryQuery: e.target.value })} /></div>
        <div className="sw-hub-filters">
          {[['all', 'sec.all'], ['personal', 'sec.personal'], ['team', 'sec.team'], ['third-party', 'sec.thirdParty'], ['squads', 'sec.squads']].map(([key, label]) => (
            <button key={key} data-action="hub-filter" data-filter={key} className={key === filter ? 'is-selected' : ''} onClick={() => set({ hubFilter: key })}>{t(label)}</button>
          ))}
        </div>
      </div>
      <div className="sw-section-line"><h2>{t('sec.hub.explore')} <span>{agents.length}</span></h2><span className="sw-meta">{t('sec.hub.everyday')}</span></div>
      {agents.length ? (
        <div className="sw-hub-grid">
          {agents.map(a => {
            const skills = Number(a.skills) || 0, tag = a.tag || 'Workmate';
            const description = a.description === 'No description yet' ? t('No description yet') : a.description;
            return (
              <button key={a.id} className="sw-hub-card" data-action="agent-detail" data-id={a.id} onClick={() => ctx.nav('detail', a.id)}>
                <div className="sw-hub-card-top"><Avatar index={a.avatar || 0} size={44} /><span className="sw-hub-tag">{CATEGORY[tag] ? t(CATEGORY[tag]) : tag}</span></div>
                <h3>{a.name}</h3>
                <p>{description || t('sec.hub.fallback')}</p>
                <div className="sw-hub-footer"><span><Icon name="grid" size={13} /> {t(skills === 1 ? 'sec.skillsOne' : 'sec.skillCount', { count: skills })}</span><span>{t('sec.hub.view')} <Icon name="arrow" size={15} /></span></div>
              </button>
            );
          })}
        </div>
      ) : <SecondaryEmpty icon="search" name="sec.hub.emptyTitle" description="sec.hub.emptyDescription" />}
    </div>
  );
}

export function Projects() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const create = () => overlay.modal(t('New project'), <CreateProjectDialog />, <CreateProjectDialog.Footer />);
  return (
    <div className="secondary-page sw-page-projects">
      <SecondaryHeader name="sec.projects" description="sec.projects.description" action="create-project" label="sec.projects.new" onAction={create} />
      <div className="sw-section-line"><h2>{t('sec.projects.all')} <span>{ws.projects.length}</span></h2><span className="sw-meta">{t('sec.recentlyUpdated')}</span></div>
      {ws.projects.length ? (
        <div className="sw-project-grid">
          {ws.projects.map((p, index) => (
            <button key={p.id} className="sw-project-card" data-action="open-project" data-id={p.id} onClick={() => ctx.nav('project', p.id)}>
              <div className="sw-project-top"><span className={`sw-project-icon sw-color-${index % 4}`}><Icon name="folder" size={24} /></span><span className="sw-card-arrow"><Icon name="arrow" size={17} /></span></div>
              <h3>{p.name || t('sec.untitled')}</h3>
              <p>{p.description || t('sec.projects.fallback')}</p>
              <div className="sw-project-participants"><Icon name="users" size={13} /> {t('workspace.projectParticipants', { members: p.memberIds.length, agents: p.agentIds.length })}</div>
              <div className="sw-project-footer"><span><Icon name="chat" size={14} /> {t(p.tasks === 1 ? 'sec.tasksOne' : 'sec.taskCount', { count: p.tasks })}</span><span>{dateText(t, p.updated || 'Just updated')}</span></div>
            </button>
          ))}
          <button className="sw-project-card sw-project-add" data-action="create-project" onClick={create}><span><Icon name="plus" size={24} /></span><h3>{t('sec.projects.create')}</h3><p>{t('sec.projects.createDescription')}</p></button>
        </div>
      ) : <SecondaryEmpty icon="folder" name="sec.projects.emptyTitle" description="sec.projects.emptyDescription" />}
    </div>
  );
}

const SHEET_HEADERS = ['sec.sheet.project', 'sec.sheet.owner', 'sec.sheet.progress', 'sec.sheet.status'];
const SHEET_ROWS = ['sec.sheet.requirements', 'sec.sheet.design', 'sec.sheet.development', 'sec.sheet.improvement', 'sec.sheet.review'];

export function Library() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const { libraryFilter: filter, set } = useUi();
  const sourceFor = (fileId: string) => ws.knowledge.find(k => k.fileId === fileId);
  const selected = filter === 'all' ? ws.library : filter === 'knowledge' ? ws.library.filter(x => sourceFor(x.id)) : ws.library.filter(x => x.type === filter);
  return (
    <div className="secondary-page sw-page-library">
      <SecondaryHeader name="sec.library" description="sec.library.description" />
      <div className="sw-library-toolbar">
        <div className="sw-tabs">
          {[['all', 'sec.files.all'], ['doc', 'sec.files.documents'], ['slides', 'sec.files.presentations'], ['sheet', 'sec.files.spreadsheets'], ['knowledge', 'web.knowledge.filter']].map(([key, label]) => (
            <button key={key} data-action="library-filter" data-filter={key} className={filter === key ? 'is-selected' : ''} onClick={() => set({ libraryFilter: key })}>
              {t(label)}{key === 'all' ? <span>{ws.library.length}</span> : null}
            </button>
          ))}
        </div>
        <span className="sw-meta">{t('sec.recentlyCreated')}</span>
      </div>
      {selected.length ? (
        <div className="sw-file-grid">
          {selected.map(f => {
            const type = ['doc', 'slides', 'sheet'].includes(f.type) ? f.type : 'doc';
            const label = { doc: 'sec.file.document', slides: 'sec.file.presentation', sheet: 'sec.file.spreadsheet' }[type];
            const name = f.name || t('sec.untitled');
            const source = sourceFor(f.id);
            const preview = type === 'doc' ? (
              <div className="sw-mini-document"><span className="sw-mini-eyebrow">{t('sec.file.documentBrand')}</span><strong>{name}</strong><div className="sw-mini-rule" /><div className="sw-mini-line" /><div className="sw-mini-line" /><div className="sw-mini-line short" /><b>01 &nbsp; {t('sec.file.overview')}</b><div className="sw-mini-line" /><div className="sw-mini-line short" /></div>
            ) : type === 'slides' ? (
              <div className="sw-mini-slides"><span>{t('sec.file.presentationBrand')}</span><strong>{name}</strong><div className="sw-slide-rule" /><small>{t('sec.file.ideas')}</small><div className="sw-slide-shape" /></div>
            ) : (
              <div className="sw-mini-sheet"><div className="sw-sheet-title">{name}</div><div className="sw-sheet-grid">
                {Array.from({ length: 24 }, (_, j) => (
                  <span key={j} className={j < 4 ? 'sw-sheet-head' : ''}>{j < 4 ? t(SHEET_HEADERS[j]) : j % 4 === 0 ? t(SHEET_ROWS[Math.floor(j / 4) - 1]) : j % 4 === 2 ? `${[100, 85, 64, 40, 20][Math.floor(j / 4) - 1]}%` : ''}</span>
                ))}
              </div></div>
            );
            return (
              <button key={f.id} className="sw-file-card" data-action="open-file" data-id={f.id} onClick={() => showFile(ctx, overlay, f.id)}>
                <div className={`sw-file-preview sw-preview-${type}`}>{preview}</div>
                <div className="sw-file-details">
                  <span className={`sw-file-type sw-type-${type}`}><Icon name={type === 'sheet' ? 'grid' : type === 'slides' ? 'play' : 'file'} size={18} /></span>
                  <div><h3>{name}</h3><p>{t(label)}<span>·</span>{dateText(t, f.updated || 'Just now')}</p></div>
                  {source ? <KnowledgeStatusTag source={source} /> : null}
                </div>
              </button>
            );
          })}
        </div>
      ) : filter === 'knowledge'
        ? <SecondaryEmpty icon="file" name="web.knowledge.libraryEmptyTitle" description="web.knowledge.libraryEmptyBody" />
        : <SecondaryEmpty icon="file" name="sec.library.emptyTitle" description="sec.library.emptyDescription" />}
    </div>
  );
}

export function Automations() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  return (
    <div className="secondary-page sw-page-automations">
      <SecondaryHeader name="sec.automations" description="sec.automations.description" action="create-automation" label="sec.automations.create"
        onAction={() => overlay.modal(t('New automation'), <CreateAutomationDialog />, <CreateAutomationDialog.Footer />)} />
      <div className="sw-info-strip"><span className="sw-info-icon"><Icon name="bolt" size={18} /></span><div><strong>{t('sec.automations.tagline')}</strong><span>{t('sec.automations.intro')}</span></div></div>
      <div className="sw-section-line"><h2>{t('sec.automations.yours')} <span>{ws.automations.length}</span></h2><span className="sw-meta">{t('sec.automations.timezone')}</span></div>
      {ws.automations.length ? (
        <div className="sw-automation-list">
          {ws.automations.map((a, index) => {
            const enabled = a.enabled !== false;
            const name = a.name || t('sec.untitled');
            return (
              <article key={a.id} className="sw-automation-row">
                <div className="sw-automation-symbol"><Icon name={index % 2 ? 'calendar' : 'clock'} size={21} /></div>
                <div className="sw-automation-body">
                  <div className="sw-row-title"><h3>{name}</h3><span className={`sw-status ${enabled ? 'is-active' : ''}`}>{t(enabled ? 'sec.active' : 'sec.paused')}</span></div>
                  <p>{a.description || t('sec.automations.fallback')}</p>
                  <div className="sw-automation-meta"><span><Icon name="clock" size={13} />{scheduleText(t, a.schedule || 'Every weekday at 09:00')}</span><span>{t(enabled ? 'sec.automations.ready' : 'sec.automations.resumeAnytime')}</span></div>
                </div>
                <button className={`sw-switch ${enabled ? 'is-on' : ''}`} role="switch" aria-checked={enabled} aria-label={t(enabled ? 'sec.automations.pauseName' : 'sec.automations.resumeName', { name })} data-action="toggle-automation" data-id={a.id}
                  onClick={() => void ctx.run(() => api.update(ctx.tenantId, 'automations', a.id, { enabled: !enabled }), !enabled ? '自动化已恢复（演示）' : '自动化已暂停（演示）')}><span /></button>
              </article>
            );
          })}
        </div>
      ) : <SecondaryEmpty icon="clock" name="sec.automations.emptyTitle" description="sec.automations.emptyDescription" />}
      <div className="sw-subtle-note"><Icon name="check" size={14} /> {t('sec.automations.control')}</div>
    </div>
  );
}

export function Code() {
  const ctx = useWs();
  const { t, ws, tenantId } = ctx;
  const drafts = useDrafts(tenantId);
  const setDrafts = useUi(s => s.setDrafts);
  const start = () => {
    const input = document.getElementById('code-prompt') as HTMLTextAreaElement;
    if (!input.value.trim()) { input.focus(); return; }
    void startTask(ctx, input.value, 'code', (document.getElementById('code-project') as HTMLSelectElement).value);
  };
  return (
    <div className="secondary-page sw-page-code">
      <div className="sw-code-layout">
        <span className="sw-code-mark"><Icon name="code" size={32} /></span>
        <div className="sw-eyebrow">{t('sec.code.eyebrow')}</div>
        <h1>{t('sec.code.title')}</h1>
        <p className="sw-code-subtitle">{t('sec.code.description')}</p>
        <div className="sw-code-composer">
          <textarea id="code-prompt" placeholder={t('sec.code.placeholder')} aria-label={t('sec.code.label')} value={drafts.codeDraft} onChange={e => setDrafts(tenantId, { codeDraft: e.target.value })} />
          <div className="sw-code-composer-footer">
            <label className="sw-project-select"><Icon name="folder" size={16} />
              <select id="code-project" aria-label={t('sec.code.project')} value={drafts.codeProject} onChange={e => setDrafts(tenantId, { codeProject: e.target.value })}>
                <option value="">{t('sec.code.project')}</option>
                {ws.projects.map(p => <option key={p.id} value={p.id}>{p.name || t('sec.untitled')}</option>)}
              </select>
            </label>
            <button className="sw-code-send" data-action="start-code-task" aria-label={t('sec.code.start')} onClick={start}><Icon name="arrow" size={20} /></button>
          </div>
        </div>
        <div className="sw-code-hints"><span><Icon name="code" size={15} /> {t('sec.code.build')}</span><span><Icon name="check" size={15} /> {t('sec.code.fix')}</span><span><Icon name="book" size={15} /> {t('sec.code.understand')}</span></div>
        <div className="sw-code-projects">
          <div className="sw-section-line"><h2>{t('sec.code.recentProjects')}</h2></div>
          {ws.projects.length ? ws.projects.slice(0, 3).map(p => (
            <button key={p.id} className="sw-code-project" data-action="open-project" data-id={p.id} onClick={() => ctx.nav('project', p.id)}><span><Icon name="folder" size={18} />{p.name || t('sec.untitled')}</span><Icon name="chevron" size={16} /></button>
          )) : <p className="sw-meta">{t('sec.code.noProjects')}</p>}
        </div>
      </div>
    </div>
  );
}
