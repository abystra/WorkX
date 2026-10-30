import { t, getLocale } from './i18n.js';

const list = value => Array.isArray(value) ? value : [];
const relativeDateKeys = {Today:'sec.today',Yesterday:'sec.yesterday','Just now':'sec.justNow','Just updated':'sec.justUpdated'};
const frequencyKeys = {'Every weekday':'sec.schedule.weekday','Every day':'sec.schedule.day','Every Monday':'sec.schedule.monday','Every Friday':'sec.schedule.friday'};
const categoryKeys = {Personal:'sec.personal',Team:'sec.team','Third-party':'sec.thirdParty',Squads:'sec.squads',Workmate:'sec.workmate'};
const dateText = value => {
  if (relativeDateKeys[value]) return t(relativeDateKeys[value]);
  const october = /^Oct (\d{1,2})$/.exec(String(value));
  return october && getLocale() === 'zh-CN' ? `10月${october[1]}日` : value;
};
const scheduleText = value => {
  const match = /^(Every weekday|Every day|Every Monday|Every Friday) at (\d{2}:\d{2})$/.exec(String(value));
  return match ? t('sec.schedule.at', {frequency:t(frequencyKeys[match[1]]),time:match[2]}) : value;
};

export function renderSecondary(page, ctx) {
  const e = ctx.escape;
  const tr = (key, params) => e(t(key, params));
  const i = (name, size = 18) => ctx.icon(name, size);
  const title = item => item.name || item.title || t('sec.untitled');
  const header = (name, description, action, label) => `<header class="sw-page-heading"><div><h1>${tr(name)}</h1><p>${tr(description)}</p></div>${action ? `<button class="sw-primary" data-action="${action}">${i('plus', 16)}${tr(label)}</button>` : ''}</header>`;
  const empty = (icon, name, description) => `<div class="sw-empty"><span class="sw-empty-icon">${i(icon, 28)}</span><h3>${tr(name)}</h3><p>${tr(description)}</p></div>`;
  let html = '';

  if (page === 'automations') {
    const automations = list(ctx.automations);
    html = header('sec.automations', 'sec.automations.description', 'create-automation', 'sec.automations.create');
    html += `<div class="sw-info-strip"><span class="sw-info-icon">${i('bolt', 18)}</span><div><strong>${tr('sec.automations.tagline')}</strong><span>${tr('sec.automations.intro')}</span></div></div>`;
    html += `<div class="sw-section-line"><h2>${tr('sec.automations.yours')} <span>${automations.length}</span></h2><span class="sw-meta">${tr('sec.automations.timezone')}</span></div>`;
    html += automations.length ? `<div class="sw-automation-list">${automations.map((a, index) => {
      const enabled = a.enabled !== false && a.active !== false;
      return `<article class="sw-automation-row"><div class="sw-automation-symbol">${i(index % 2 ? 'calendar' : 'clock', 21)}</div><div class="sw-automation-body"><div class="sw-row-title"><h3>${e(title(a))}</h3><span class="sw-status ${enabled ? 'is-active' : ''}">${tr(enabled ? 'sec.active' : 'sec.paused')}</span></div><p>${e(a.description || t('sec.automations.fallback'))}</p><div class="sw-automation-meta"><span>${i('clock', 13)}${e(scheduleText(a.schedule || 'Every weekday at 09:00'))}</span>${a.nextRun ? `<span>${tr('sec.automations.next',{time:dateText(a.nextRun)})}</span>` : `<span>${tr(enabled ? 'sec.automations.ready' : 'sec.automations.resumeAnytime')}</span>`}</div></div><button class="sw-switch ${enabled ? 'is-on' : ''}" role="switch" aria-checked="${enabled}" aria-label="${tr(enabled ? 'sec.automations.pauseName' : 'sec.automations.resumeName',{name:title(a)})}" data-action="toggle-automation" data-id="${e(String(a.id))}"><span></span></button></article>`;
    }).join('')}</div>` : empty('clock', 'sec.automations.emptyTitle', 'sec.automations.emptyDescription');
    html += `<div class="sw-subtle-note">${i('check', 14)} ${tr('sec.automations.control')}</div>`;
  }

  if (page === 'projects') {
    const projects = list(ctx.projects);
    html = header('sec.projects', 'sec.projects.description', 'create-project', 'sec.projects.new');
    html += `<div class="sw-section-line"><h2>${tr('sec.projects.all')} <span>${projects.length}</span></h2><span class="sw-meta">${tr('sec.recentlyUpdated')}</span></div>`;
    html += projects.length ? `<div class="sw-project-grid">${projects.map((p, index) => {
      const count = typeof p.tasks === 'number' ? p.tasks : list(p.tasks).length;
      return `<button class="sw-project-card" data-action="open-project" data-id="${e(String(p.id))}"><div class="sw-project-top"><span class="sw-project-icon sw-color-${index % 4}">${i('folder', 24)}</span><span class="sw-card-arrow">${i('arrow', 17)}</span></div><h3>${e(title(p))}</h3><p>${e(p.description || t('sec.projects.fallback'))}</p><div class="sw-project-participants">${i('users',13)} ${tr('workspace.projectParticipants',{members:list(p.memberIds).length,agents:list(p.agentIds).length})}</div><div class="sw-project-footer"><span>${i('chat', 14)} ${tr(count === 1 ? 'sec.tasksOne' : 'sec.taskCount',{count})}</span><span>${e(dateText(p.updated || p.updatedAt || 'Just updated'))}</span></div></button>`;
    }).join('')}<button class="sw-project-card sw-project-add" data-action="create-project"><span>${i('plus', 24)}</span><h3>${tr('sec.projects.create')}</h3><p>${tr('sec.projects.createDescription')}</p></button></div>` : empty('folder', 'sec.projects.emptyTitle', 'sec.projects.emptyDescription');
  }

  if (page === 'library') {
    const items = list(ctx.library);
    const filter = ctx.libraryFilter || 'all';
    const selected = filter === 'all' ? items : items.filter(x => x.type === filter);
    html = header('sec.library', 'sec.library.description');
    html += `<div class="sw-library-toolbar"><div class="sw-tabs">${[['all','sec.files.all'],['doc','sec.files.documents'],['slides','sec.files.presentations'],['sheet','sec.files.spreadsheets']].map(([key,label]) => `<button data-action="library-filter" data-filter="${key}" class="${filter === key ? 'is-selected' : ''}">${tr(label)}${key === 'all' ? `<span>${items.length}</span>` : ''}</button>`).join('')}</div><span class="sw-meta">${tr('sec.recentlyCreated')}</span></div>`;
    html += selected.length ? `<div class="sw-file-grid">${selected.map(f => {
      const type = ['doc','slides','sheet'].includes(f.type) ? f.type : 'doc';
      const label = {doc:'sec.file.document',slides:'sec.file.presentation',sheet:'sec.file.spreadsheet'}[type];
      const sheetHeaders = ['sec.sheet.project','sec.sheet.owner','sec.sheet.progress','sec.sheet.status'];
      const sheetRows = ['sec.sheet.requirements','sec.sheet.design','sec.sheet.development','sec.sheet.improvement','sec.sheet.review'];
      let preview = type === 'doc' ? `<div class="sw-mini-document"><span class="sw-mini-eyebrow">${tr('sec.file.documentBrand')}</span><strong>${e(title(f))}</strong><div class="sw-mini-rule"></div><div class="sw-mini-line"></div><div class="sw-mini-line"></div><div class="sw-mini-line short"></div><b>01 &nbsp; ${tr('sec.file.overview')}</b><div class="sw-mini-line"></div><div class="sw-mini-line short"></div></div>` : type === 'slides' ? `<div class="sw-mini-slides"><span>${tr('sec.file.presentationBrand')}</span><strong>${e(title(f))}</strong><div class="sw-slide-rule"></div><small>${tr('sec.file.ideas')}</small><div class="sw-slide-shape"></div></div>` : `<div class="sw-mini-sheet"><div class="sw-sheet-title">${e(title(f))}</div><div class="sw-sheet-grid">${Array.from({length:24}, (_, j) => `<span class="${j < 4 ? 'sw-sheet-head' : ''}">${j < 4 ? tr(sheetHeaders[j]) : j % 4 === 0 ? tr(sheetRows[Math.floor(j/4)-1]) : j % 4 === 2 ? `${[100,85,64,40,20][Math.floor(j/4)-1]}%` : ''}</span>`).join('')}</div></div>`;
      return `<button class="sw-file-card" data-action="open-file" data-id="${e(String(f.id))}"><div class="sw-file-preview sw-preview-${type}">${preview}</div><div class="sw-file-details"><span class="sw-file-type sw-type-${type}">${i(type === 'sheet' ? 'grid' : type === 'slides' ? 'play' : 'file', 18)}</span><div><h3>${e(title(f))}</h3><p>${tr(label)}<span>·</span>${e(dateText(f.updated || f.updatedAt || 'Just now'))}</p></div></div></button>`;
    }).join('')}</div>` : empty('file', 'sec.library.emptyTitle', 'sec.library.emptyDescription');
  }

  if (page === 'hub') {
    const filter = ctx.hubFilter || 'all';
    const query = String(ctx.query || '').toLowerCase();
    const agents = list(ctx.agents).filter(a => (filter === 'all' || String(a.tag || 'Team').toLowerCase() === filter) && `${a.name} ${a.description || ''}`.toLowerCase().includes(query));
    html = header('sec.hub', 'sec.hub.description');
    html += `<div class="sw-hub-intro"><span class="sw-hub-intro-icon">${i('users', 29)}</span><div><div class="sw-eyebrow">${tr('sec.hub.eyebrow')}</div><h2>${tr('sec.hub.tagline')}</h2><p>${tr('sec.hub.intro')}</p></div></div>`;
    html += `<div class="sw-hub-toolbar"><div class="sw-search">${i('search', 16)}<input data-secondary-search value="${e(ctx.query || '')}" placeholder="${tr('sec.hub.search')}" aria-label="${tr('sec.hub.search')}" autocomplete="off"></div><div class="sw-hub-filters">${[['all','sec.all'],['personal','sec.personal'],['team','sec.team'],['third-party','sec.thirdParty'],['squads','sec.squads']].map(([key,label]) => `<button data-action="hub-filter" data-filter="${key}" class="${key === filter ? 'is-selected' : ''}">${tr(label)}</button>`).join('')}</div></div>`;
    html += `<div class="sw-section-line"><h2>${tr('sec.hub.explore')} <span>${agents.length}</span></h2><span class="sw-meta">${tr('sec.hub.everyday')}</span></div>`;
    html += agents.length ? `<div class="sw-hub-grid">${agents.map(a => {
      const skills = Number(a.skills) || 0;
      const tag = a.tag || 'Workmate';
      return `<button class="sw-hub-card" data-action="agent-detail" data-id="${e(String(a.id))}"><div class="sw-hub-card-top">${ctx.avatar(a.avatar || 0, 44)}<span class="sw-hub-tag">${categoryKeys[tag] ? tr(categoryKeys[tag]) : e(tag)}</span></div><h3>${e(a.name)}</h3><p>${e(a.description || t('sec.hub.fallback'))}</p><div class="sw-hub-footer"><span>${i('grid', 13)} ${tr(skills === 1 ? 'sec.skillsOne' : 'sec.skillCount',{count:skills})}</span><span>${tr('sec.hub.view')} ${i('arrow', 15)}</span></div></button>`;
    }).join('')}</div>` : empty('search', 'sec.hub.emptyTitle', 'sec.hub.emptyDescription');
  }

  if (page === 'code') {
    const projects = list(ctx.projects);
    html = `<div class="sw-code-layout"><span class="sw-code-mark">${i('code', 32)}</span><div class="sw-eyebrow">${tr('sec.code.eyebrow')}</div><h1>${tr('sec.code.title')}</h1><p class="sw-code-subtitle">${tr('sec.code.description')}</p><div class="sw-code-composer"><textarea id="code-prompt" placeholder="${tr('sec.code.placeholder')}" aria-label="${tr('sec.code.label')}">${e(ctx.codeDraft || '')}</textarea><div class="sw-code-composer-footer"><label class="sw-project-select">${i('folder', 16)}<select id="code-project" aria-label="${tr('sec.code.project')}"><option value="">${tr('sec.code.project')}</option>${projects.map(p => `<option value="${e(String(p.id))}" ${String(p.id) === String(ctx.codeProject || '') ? 'selected' : ''}>${e(title(p))}</option>`).join('')}</select></label><button class="sw-code-send" data-action="start-code-task" aria-label="${tr('sec.code.start')}">${i('arrow', 20)}</button></div></div><div class="sw-code-hints"><span>${i('code', 15)} ${tr('sec.code.build')}</span><span>${i('check', 15)} ${tr('sec.code.fix')}</span><span>${i('book', 15)} ${tr('sec.code.understand')}</span></div><div class="sw-code-projects"><div class="sw-section-line"><h2>${tr('sec.code.recentProjects')}</h2></div>${projects.slice(0,3).map(p => `<button class="sw-code-project" data-action="open-project" data-id="${e(String(p.id))}"><span>${i('folder', 18)}${e(title(p))}</span>${i('chevron', 16)}</button>`).join('') || `<p class="sw-meta">${tr('sec.code.noProjects')}</p>`}</div></div>`;
  }
  return `<div class="secondary-page sw-page-${page}">${html}</div>`;
}
