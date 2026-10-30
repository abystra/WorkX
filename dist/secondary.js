const list = value => Array.isArray(value) ? value : [];

export function renderSecondary(page, ctx) {
  const e = ctx.escape;
  const i = (name, size = 18) => ctx.icon(name, size);
  const title = item => item.name || item.title || 'Untitled';
  const header = (name, description, action, label) => `<header class="sw-page-heading"><div><h1>${name}</h1><p>${description}</p></div>${action ? `<button class="sw-primary" data-action="${action}">${i('plus', 16)}${label}</button>` : ''}</header>`;
  const empty = (icon, name, description) => `<div class="sw-empty"><span class="sw-empty-icon">${i(icon, 28)}</span><h3>${name}</h3><p>${description}</p></div>`;
  let html = '';

  if (page === 'automations') {
    const automations = list(ctx.automations);
    html = header('Automations', 'Let your workmates take care of recurring work.', 'create-automation', 'New automation');
    html += `<div class="sw-info-strip"><span class="sw-info-icon">${i('bolt', 18)}</span><div><strong>Good work, on autopilot.</strong><span>把重复的工作交给智能伙伴，在需要的时候收到结果。</span></div></div>`;
    html += `<div class="sw-section-line"><h2>Your automations <span>${automations.length}</span></h2><span class="sw-meta">All times in local timezone</span></div>`;
    html += automations.length ? `<div class="sw-automation-list">${automations.map((a, index) => {
      const enabled = a.enabled !== false && a.active !== false;
      return `<article class="sw-automation-row"><div class="sw-automation-symbol">${i(index % 2 ? 'calendar' : 'clock', 21)}</div><div class="sw-automation-body"><div class="sw-row-title"><h3>${e(title(a))}</h3><span class="sw-status ${enabled ? 'is-active' : ''}">${enabled ? 'Active' : 'Paused'}</span></div><p>${e(a.description || '由智能伙伴自动执行，并将结果整理到任务中。')}</p><div class="sw-automation-meta"><span>${i('clock', 13)}${e(a.schedule || 'Every weekday at 09:00')}</span>${a.nextRun ? `<span>Next run: ${e(a.nextRun)}</span>` : `<span>${enabled ? 'Ready for the next run' : 'Resume anytime'}</span>`}</div></div><button class="sw-switch ${enabled ? 'is-on' : ''}" role="switch" aria-checked="${enabled}" aria-label="${enabled ? 'Pause' : 'Resume'} ${e(title(a))}" data-action="toggle-automation" data-id="${e(String(a.id))}"><span></span></button></article>`;
    }).join('')}</div>` : empty('clock', 'Make room for more meaningful work', 'Create your first automation to get started.');
    html += `<div class="sw-subtle-note">${i('check', 14)} You’re in control. Pause or resume an automation at any time.</div>`;
  }

  if (page === 'projects') {
    const projects = list(ctx.projects);
    html = header('Projects', 'A shared space for your tasks, knowledge, and workmates.', 'create-project', 'New project');
    html += `<div class="sw-section-line"><h2>All projects <span>${projects.length}</span></h2><span class="sw-meta">Recently updated</span></div>`;
    html += projects.length ? `<div class="sw-project-grid">${projects.map((p, index) => `<button class="sw-project-card" data-action="open-project" data-id="${e(String(p.id))}"><div class="sw-project-top"><span class="sw-project-icon sw-color-${index % 4}">${i('folder', 24)}</span><span class="sw-card-arrow">${i('arrow', 17)}</span></div><h3>${e(title(p))}</h3><p>${e(p.description || '在这里整理项目资料，和智能伙伴一起推进工作。')}</p><div class="sw-project-footer"><span>${i('chat', 14)} ${typeof p.tasks === 'number' ? p.tasks : list(p.tasks).length} tasks</span><span>${e(p.updated || p.updatedAt || 'Just updated')}</span></div></button>`).join('')}<button class="sw-project-card sw-project-add" data-action="create-project"><span>${i('plus', 24)}</span><h3>Create a project</h3><p>让下一件重要的事，有一个专属空间</p></button></div>` : empty('folder', 'Your next big thing starts here', 'Create a project to keep everything in one place.');
  }

  if (page === 'library') {
    const items = list(ctx.library);
    const filter = ctx.libraryFilter || 'all';
    const selected = filter === 'all' ? items : items.filter(x => x.type === filter);
    html = header('Library', 'Everything you and your workmates have created, in one place.');
    html += `<div class="sw-library-toolbar"><div class="sw-tabs">${[['all','All files'],['doc','Documents'],['slides','Presentations'],['sheet','Spreadsheets']].map(([key,label]) => `<button data-action="library-filter" data-filter="${key}" class="${filter === key ? 'is-selected' : ''}">${label}${key === 'all' ? `<span>${items.length}</span>` : ''}</button>`).join('')}</div><span class="sw-meta">Recently created</span></div>`;
    html += selected.length ? `<div class="sw-file-grid">${selected.map((f, index) => {
      const type = ['doc','slides','sheet'].includes(f.type) ? f.type : 'doc';
      const label = {doc: 'Document', slides: 'Presentation', sheet: 'Spreadsheet'}[type];
      let preview = type === 'doc' ? `<div class="sw-mini-document"><span class="sw-mini-eyebrow">WORKMATES / DOCUMENT</span><strong>${e(title(f))}</strong><div class="sw-mini-rule"></div><div class="sw-mini-line"></div><div class="sw-mini-line"></div><div class="sw-mini-line short"></div><b>01 &nbsp; Overview</b><div class="sw-mini-line"></div><div class="sw-mini-line short"></div></div>` : type === 'slides' ? `<div class="sw-mini-slides"><span>WORKMATES PRESENTATION</span><strong>${e(title(f))}</strong><div class="sw-slide-rule"></div><small>Ideas into action.</small><div class="sw-slide-shape"></div></div>` : `<div class="sw-mini-sheet"><div class="sw-sheet-title">${e(title(f))}</div><div class="sw-sheet-grid">${Array.from({length:24}, (_, j) => `<span class="${j < 4 ? 'sw-sheet-head' : ''}">${j < 4 ? ['项目','负责人','进度','状态'][j] : j % 4 === 0 ? ['需求梳理','方案设计','开发实现','体验优化','项目复盘'][Math.floor(j/4)-1] : j % 4 === 2 ? `${[100,85,64,40,20][Math.floor(j/4)-1]}%` : ''}</span>`).join('')}</div></div>`;
      return `<button class="sw-file-card" data-action="open-file" data-id="${e(String(f.id))}"><div class="sw-file-preview sw-preview-${type}">${preview}</div><div class="sw-file-details"><span class="sw-file-type sw-type-${type}">${i(type === 'sheet' ? 'grid' : type === 'slides' ? 'play' : 'file', 18)}</span><div><h3>${e(title(f))}</h3><p>${label}<span>·</span>${e(f.updated || f.updatedAt || 'Just now')}</p></div></div></button>`;
    }).join('')}</div>` : empty('file', 'Nothing here just yet', 'Files created in your tasks will appear here.');
  }

  if (page === 'hub') {
    const filter = ctx.hubFilter || 'all';
    const query = String(ctx.query || '').toLowerCase();
    const agents = list(ctx.agents).filter(a => (filter === 'all' || String(a.tag || 'Team').toLowerCase() === filter) && `${a.name} ${a.description || ''}`.toLowerCase().includes(query));
    html = header('Hub', 'Find the right workmate for whatever comes next.');
    html += `<div class="sw-hub-intro"><span class="sw-hub-intro-icon">${i('users', 29)}</span><div><div class="sw-eyebrow">BETTER, TOGETHER</div><h2>A little expertise. A lot of possibility.</h2><p>从灵感到成果，找到与你并肩工作的智能伙伴。</p></div></div>`;
    html += `<div class="sw-hub-toolbar"><div class="sw-search">${i('search', 16)}<input data-secondary-search value="${e(ctx.query || '')}" placeholder="Search workmates and skills" aria-label="Search workmates and skills" autocomplete="off"></div><div class="sw-hub-filters">${[['all','All'],['personal','Personal'],['team','Team'],['third-party','Third-party'],['squads','Squads']].map(([key,label]) => `<button data-action="hub-filter" data-filter="${key}" class="${key === filter ? 'is-selected' : ''}">${label}</button>`).join('')}</div></div>`;
    html += `<div class="sw-section-line"><h2>Explore workmates <span>${agents.length}</span></h2><span class="sw-meta">Made for your everyday work</span></div>`;
    html += agents.length ? `<div class="sw-hub-grid">${agents.map(a => `<button class="sw-hub-card" data-action="agent-detail" data-id="${e(String(a.id))}"><div class="sw-hub-card-top">${ctx.avatar(a.avatar || 0, 44)}<span class="sw-hub-tag">${e(a.tag || 'Workmate')}</span></div><h3>${e(a.name)}</h3><p>${e(a.description || '你的专属智能伙伴，随时准备和你一起开始新的工作。')}</p><div class="sw-hub-footer"><span>${i('grid', 13)} ${Number(a.skills) || 0} skills</span><span>View workmate ${i('arrow', 15)}</span></div></button>`).join('')}</div>` : empty('search', 'No workmates found', 'Try another name or explore a different category.');
  }

  if (page === 'code') {
    const projects = list(ctx.projects);
    html = `<div class="sw-code-layout"><span class="sw-code-mark">${i('code', 32)}</span><div class="sw-eyebrow">YOUR IDEAS, BUILT</div><h1>What would you like to build?</h1><p class="sw-code-subtitle">和你的编程伙伴一起，把想法变成可以运行的作品。</p><div class="sw-code-composer"><textarea id="code-prompt" placeholder="Describe an app, fix a bug, or explore an idea…" aria-label="Describe your coding task"></textarea><div class="sw-code-composer-footer"><label class="sw-project-select">${i('folder', 16)}<select id="code-project" aria-label="Choose a project"><option value="">Choose a project</option>${projects.map(p => `<option value="${e(String(p.id))}">${e(title(p))}</option>`).join('')}</select></label><button class="sw-code-send" data-action="start-code-task" aria-label="Start coding task">${i('arrow', 20)}</button></div></div><div class="sw-code-hints"><span>${i('code', 15)} Build an app</span><span>${i('check', 15)} Fix a bug</span><span>${i('book', 15)} Understand a codebase</span></div><div class="sw-code-projects"><div class="sw-section-line"><h2>Recent projects</h2></div>${projects.slice(0,3).map(p => `<button class="sw-code-project" data-action="open-project" data-id="${e(String(p.id))}"><span>${i('folder', 18)}${e(title(p))}</span>${i('chevron', 16)}</button>`).join('') || `<p class="sw-meta">Your projects will appear here.</p>`}</div></div>`;
  }
  return `<div class="secondary-page sw-page-${page}">${html}</div>`;
}
