import { ensureSaasData, renderEnterprise, renderOrganization, renderRoles, memberMeta, handleSaasAction } from './saas.js';
import { t, getLocale } from './i18n.js';
import { renderChannelTaskBadge } from './channel.js';

const list = value => Array.isArray(value) ? value : [];
const unique = values => [...new Set(values)];
const roles = ['owner', 'admin', 'member'];
const id = prefix => prefix + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

export function ensureTeamData(data) {
  if (!Array.isArray(data.teamMembers)) data.teamMembers = [
    { id: 'm1', name: 'Alex', role: 'owner' },
    { id: 'm2', name: 'Lin', role: 'admin' },
    { id: 'm3', name: 'Chen', role: 'member' },
  ];
  ensureSaasData(data);
  if (!Array.isArray(data.teamAgentIds)) data.teamAgentIds = list(data.agents).filter(a => a.tag === 'Team' || a.tag === 'Squads').map(a => a.id);
  if (!Array.isArray(data.teamActivity)) data.teamActivity = [];
  const memberIds = data.teamMembers.map(m => m.id);
  for (const project of list(data.projects)) {
    if (!Array.isArray(project.memberIds)) project.memberIds = ['p1', 'p2', 'p3'].includes(project.id) ? memberIds.slice(0, 3) : memberIds.slice(0, 1);
    if (!Array.isArray(project.agentIds)) {
      const taskAgents = list(data.tasks).filter(task => task.project === project.id).map(task => task.agent).filter(a => list(data.agents).some(agent => agent.id === a));
      project.agentIds = unique(taskAgents.length ? taskAgents : list(data.agents).slice(0, 1).map(a => a.id));
    }
    if (typeof project.sharedContext !== 'string') project.sharedContext = '';
  }
}

function helpers(ctx) {
  const e = ctx.escape;
  const tr = (key, params) => e(t(key, params));
  const i = (name, size = 18) => ctx.icon(name, size);
  const btn = (action, label, extra = '', type = '') => `<button class="btn ${type}" data-action="${action}" ${extra}>${tr(label)}</button>`;
  const person = (member, size = '') => `<span class="wx-team-person ${size}" aria-hidden="true">${e((member?.name || '?').slice(0, 1).toUpperCase())}</span>`;
  return { e, tr, i, btn, person };
}

function note(ctx) {
  const { tr, i } = helpers(ctx);
  return `<div class="wx-team-local">${i('users', 15)}<span><strong>${tr('team.local')}</strong>${tr('team.localNote')}</span></div>`;
}

function tabs(ctx, values, active, action) {
  const { tr } = helpers(ctx);
  return `<div class="wx-team-tabs" role="tablist">${values.map(([value, label]) => `<button type="button" role="tab" aria-selected="${value === active}" class="${value === active ? 'is-active' : ''}" data-action="${action}" data-tab="${value}">${tr(label)}</button>`).join('')}</div>`;
}

export function renderHomeTeam(ctx) {
  const { data } = ctx;
  const { tr, i } = helpers(ctx);
  const shared = list(data.agents).filter(a => list(data.teamAgentIds).includes(a.id));
  return `<section class="wx-team-home"><div class="wx-team-home-heading"><div><span class="wx-team-eyebrow">${tr('team.local')}</span><h1>${tr('team.homeTitle')}</h1><p>${tr('team.homeDescription')}</p></div><button class="text-btn" data-action="nav" data-page="team">${tr('team.manage')}${i('chevron', 13)}</button></div><div class="wx-team-home-footer"><div class="wx-team-home-counts"><span>${i('users', 14)}${tr('team.memberCount', { count: list(data.teamMembers).length })}</span><span>${i('robot', 14)}${tr('team.agentCount', { count: shared.length })}</span><span>${i('folder', 14)}${tr('team.projectCount', { count: list(data.projects).length })}</span></div><button class="text-btn" data-action="nav" data-page="projects">${tr('team.projects')}${i('arrow', 14)}</button></div></section>`;
}

function renderMembers(ctx) {
  const { data } = ctx;
  const { e, tr, btn, person } = helpers(ctx);
  return `<div class="wx-team-panel"><div class="wx-team-panel-heading"><h2>${tr('team.members')} <span>${list(data.teamMembers).length}</span></h2>${btn('team-add-member', 'team.addMember')}</div><p class="wx-team-caption">${tr('team.roleNote')}</p><div class="wx-team-members">${list(data.teamMembers).map(member => `<div class="wx-team-member"><div class="wx-team-identity">${person(member)}<div><strong>${e(member.name)}</strong>${memberMeta(member,ctx)}${member.id === 'm1' ? `<small>${tr('team.you')}</small>` : ''}</div></div><span class="wx-team-role">${tr('team.role.' + (roles.includes(member.role) ? member.role : 'member'))}</span><button class="text-btn" data-action="saas-member" data-id="${e(member.id)}">${tr('saas.manageMember')}</button></div>`).join('')}</div></div>`;
}

function renderSharedAgents(ctx) {
  const { data } = ctx;
  const { e, tr, i, btn } = helpers(ctx);
  const agents = list(data.agents).filter(a => list(data.teamAgentIds).includes(a.id));
  return `<div class="wx-team-panel"><div class="wx-team-panel-heading"><div><h2>${tr('team.agents')} <span>${agents.length}</span></h2><p>${tr('team.sharedDescription')}</p></div>${btn('team-manage-agents', 'team.manageAgents')}</div>${agents.length ? `<div class="wx-team-agent-grid">${agents.map(agent => `<button class="wx-team-agent-card" data-action="agent-detail" data-id="${e(agent.id)}"><div>${ctx.avatar(agent.avatar, 38)}<strong>${e(agent.name)}</strong></div><p>${e(agent.description && agent.description !== 'No description yet' ? agent.description : t('team.agentNoDescription'))}</p><span>${tr('team.viewAgent')}${i('chevron', 13)}</span></button>`).join('')}</div>` : `<div class="wx-team-empty">${i('robot', 28)}<h3>${tr('team.noAgents')}</h3><p>${tr('team.noAgentsDescription')}</p></div>`}</div>`;
}

function renderActivity(ctx) {
  const { data } = ctx;
  const { e, tr, i } = helpers(ctx);
  const events = list(data.teamActivity);
  return `<div class="wx-team-panel"><div class="wx-team-panel-heading"><h2>${tr('team.activity')}</h2><span class="wx-team-caption">${tr('team.activity.local')}</span></div>${events.length ? `<ol class="wx-team-activity">${events.map(event => {
    const date = new Date(event.at);
    const timestamp = Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(getLocale(), { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
    return `<li><span class="wx-team-activity-dot">${i('check', 12)}</span><div><p>${tr('team.activity.' + event.type, event)}</p><time>${e(timestamp)}</time></div>${event.projectId && list(data.projects).some(p => p.id === event.projectId) ? `<button class="text-btn" data-action="open-project" data-id="${e(event.projectId)}">${i('arrow', 15)}<span class="wx-team-sr-only">${tr('project.collaboration')}</span></button>` : ''}</li>`;
  }).join('')}</ol>` : `<div class="wx-team-empty">${i('clock', 28)}<h3>${tr('team.noActivity')}</h3><p>${tr('team.noActivityDescription')}</p></div>`}</div>`;
}

export function renderTeam(ctx) {
  const { tr, i } = helpers(ctx);
  const active = ['members', 'organization', 'roles', 'agents', 'activity'].includes(ctx.state.teamTab) ? ctx.state.teamTab : 'members';
  return `<div class="secondary-page wx-team-page"><header class="sw-page-heading"><div><h1>${tr('team.title')}</h1><p>${tr('team.description')}</p></div><span class="wx-team-page-symbol">${i('users', 25)}</span></header>${renderEnterprise(ctx)}<p class="wx-team-caption">${tr('saas.boundary')}</p>${note(ctx)}${tabs(ctx, [['members', 'team.members'], ['organization','saas.organization'], ['roles','saas.roles'], ['agents', 'team.agents'], ['activity', 'team.activity']], active, 'team-tab')}${active === 'organization' ? renderOrganization(ctx) : active === 'roles' ? renderRoles(ctx) : active === 'agents' ? renderSharedAgents(ctx) : active === 'activity' ? renderActivity(ctx) : renderMembers(ctx)}</div>`;
}

function taskCard(task, ctx) {
  const { data } = ctx;
  const { e, tr, i, person } = helpers(ctx);
  const owner = list(data.teamMembers).find(member => member.id === task.ownerId);
  const agent = list(data.agents).find(a => a.id === task.agent);
  const supporting = list(data.agents).filter(a => list(task.supportingAgentIds).includes(a.id));
  const file = list(data.library).find(f => f.id === task.file);
  return `<article class="wx-project-task"><button class="wx-project-task-title" data-action="open-task" data-id="${e(task.id)}" aria-label="${tr('project.openTask', { name: task.name })}">${e(task.name)}</button><div class="wx-project-task-people"><span title="${tr('project.owner')}">${owner ? person(owner, 'is-small') : i('users', 14)}${e(owner?.name || t('project.unassigned'))}</span>${agent ? `<span title="${tr('project.primaryAgent')}">${ctx.avatar(agent.avatar, 18)}${e(agent.name)}</span>` : ''}</div>${supporting.length ? `<div class="wx-project-supporting"><span>${tr('project.supportingAgents')}</span>${supporting.map(a => `<span title="${e(a.name)}">${ctx.avatar(a.avatar, 18)}${e(a.name)}</span>`).join('')}</div>` : ''}${task.kind==='channel'?renderChannelTaskBadge(task,ctx):''}<div class="wx-project-task-actions"><button class="text-btn" data-action="team-assign-task" data-id="${e(task.id)}">${tr('project.assign')}</button>${task.status === 'done' ? `<button class="text-btn ${task.reviewState === 'accepted' ? '' : 'is-accent'}" data-action="${task.reviewState === 'accepted' ? 'team-reopen-task' : 'team-accept-task'}" data-id="${e(task.id)}">${tr(task.reviewState === 'accepted' ? 'project.undoConfirm' : 'project.confirm')}</button>` : ''}</div>${file && task.status === 'done' ? `<button class="wx-project-task-file" data-action="open-file" data-id="${e(file.id)}">${i('file', 14)}<span>${tr('project.preview')}</span>${i('chevron', 11)}</button>` : ''}</article>`;
}

function renderBoard(project, ctx) {
  const { tr } = helpers(ctx);
  const tasks = list(ctx.data.tasks).filter(task => task.project === project.id && !task.archived);
  const groups = [
    ['running', 'project.running', 'project.emptyRunning', tasks.filter(task => !['done','failed','interrupted','cancelled'].includes(task.status))],
    ['review', 'project.review', 'project.emptyReview', tasks.filter(task => task.status === 'done' && task.reviewState !== 'accepted')],
    ['accepted', 'project.accepted', 'project.emptyAccepted', tasks.filter(task => task.status === 'done' && task.reviewState === 'accepted')],
  ];
  const attention=tasks.filter(task=>['failed','interrupted','cancelled'].includes(task.status));
  if(attention.length)groups.push(['attention','project.attention','project.emptyAttention',attention]);
  return `<p class="wx-project-board-note">${tr('project.boardNote')}</p><div class="wx-project-board${attention.length?' has-attention':''}">${groups.map(([key, label, empty, items]) => `<section class="wx-project-column is-${key}"><h2><span class="wx-project-status-dot"></span>${tr(label)}<small>${items.length}</small></h2><div class="wx-project-column-body">${items.length ? items.map(task => taskCard(task, ctx)).join('') : `<p class="wx-project-column-empty">${tr(empty)}</p>`}</div></section>`).join('')}</div>`;
}

function renderContext(project, ctx) {
  const { e, tr, i, btn } = helpers(ctx);
  const files = unique(list(ctx.data.tasks).filter(task => task.project === project.id && !task.archived && task.status === 'done').map(task => task.file).filter(Boolean)).map(id => list(ctx.data.library).find(file => file.id === id)).filter(Boolean);
  return `<div class="wx-project-context-layout"><section class="wx-team-panel"><div class="wx-team-panel-heading"><div><h2>${tr('project.contextTitle')}</h2><p>${tr('project.contextDescription')}</p></div>${btn('team-edit-context', 'team.edit', `data-id="${e(project.id)}"`)}</div><div class="wx-project-context ${project.sharedContext ? '' : 'is-empty'}">${e(project.sharedContext || t('project.emptyContext'))}</div><p class="wx-team-caption">${tr('project.contextNote')}</p></section><section class="wx-team-panel"><div class="wx-team-panel-heading"><div><h2>${tr('project.outcomes')} <span>${files.length}</span></h2><p>${tr('project.outcomesDescription')}</p></div></div>${files.length ? `<div class="wx-project-files">${files.map(file => `<button data-action="open-file" data-id="${e(file.id)}">${i('file', 21)}<span><strong>${e(file.name)}</strong><small>${tr('project.document')}</small></span>${i('chevron', 13)}</button>`).join('')}</div>` : `<p class="wx-project-empty-line">${i('file', 20)}${tr('project.noOutcomes')}</p>`}</section></div>`;
}

function renderRoster(project, ctx) {
  const { data } = ctx;
  const { e, tr, btn, person } = helpers(ctx);
  const members = list(data.teamMembers).filter(member => list(project.memberIds).includes(member.id));
  const agents = list(data.agents).filter(agent => list(project.agentIds).includes(agent.id));
  return `<div class="wx-project-roster-heading"><p>${tr('project.local')}</p>${btn('team-project-roster', 'project.manageRoster', `data-id="${e(project.id)}"`)}</div><div class="wx-project-roster-grid"><section class="wx-team-panel"><div class="wx-team-panel-heading"><div><h2>${tr('team.members')} <span>${members.length}</span></h2><p>${tr('project.peopleDescription')}</p></div></div>${members.map(member => `<div class="wx-project-person-row">${person(member)}<strong>${e(member.name)}</strong><span class="wx-team-role">${tr('team.role.' + (roles.includes(member.role) ? member.role : 'member'))}</span></div>`).join('')}</section><section class="wx-team-panel"><div class="wx-team-panel-heading"><div><h2>${tr('project.supportingAgents')} <span>${agents.length}</span></h2><p>${tr('project.agentsDescription')}</p></div></div>${agents.map(agent => `<button class="wx-project-person-row is-agent" data-action="agent-detail" data-id="${e(agent.id)}">${ctx.avatar(agent.avatar, 33)}<strong>${e(agent.name)}</strong><span>${tr('team.viewAgent')}</span></button>`).join('')}</section></div>`;
}

export function renderProjectWorkspace(project, ctx) {
  const { data } = ctx;
  const { e, tr, i, btn } = helpers(ctx);
  const active = ['tasks', 'context', 'members'].includes(ctx.state.projectTab) ? ctx.state.projectTab : 'tasks';
  const count = list(data.tasks).filter(task => task.project === project.id && !task.archived).length;
  return `<div class="secondary-page wx-project-page"><div class="wx-project-crumb"><button data-action="nav" data-page="projects">${tr('project.back')}</button>${i('chevron', 12)}<span>${tr('project.collaboration')}</span></div><header class="wx-project-heading"><span class="wx-project-symbol">${i('folder', 27)}</span><div><h1>${e(project.name)}</h1><p>${e(project.description || '')}</p><div class="wx-project-meta"><span>${tr('project.peopleCount', { count: list(project.memberIds).length })}</span><span>${tr('project.agentCount', { count: list(project.agentIds).length })}</span><span>${tr('project.taskCount', { count })}</span></div></div>${btn('project-new-task', 'project.newTask', `data-id="${e(project.id)}"`, 'primary')}</header>${tabs(ctx, [['tasks', 'project.tasks'], ['context', 'project.context'], ['members', 'project.members']], active, 'team-project-tab')}${active === 'context' ? renderContext(project, ctx) : active === 'members' ? renderRoster(project, ctx) : renderBoard(project, ctx)}</div>`;
}

function record(data, type, fields = {}) {
  data.teamActivity.unshift({ id: id('ev'), type, at: new Date().toISOString(), ...fields });
  data.teamActivity = data.teamActivity.slice(0, 80);
}

function finish(ctx, message) {
  ctx.persist();
  ctx.closeOverlay();
  ctx.render();
  ctx.toast(t(message));
}

function checks(items, selected, name, ctx, renderImage) {
  const { e } = helpers(ctx);
  return `<div class="wx-team-choice-list">${items.map(item => `<label class="wx-team-choice"><input type="checkbox" name="${name}" value="${e(item.id)}" ${selected.includes(item.id) ? 'checked' : ''}>${renderImage(item)}<span>${e(item.name)}</span></label>`).join('')}</div>`;
}

export function handleTeamAction(action, el, ctx) {
  if (handleSaasAction(action,el,ctx)) return true;
  if (!action.startsWith('team-')) return false;
  const { data, state } = ctx;
  const { e, tr, btn, person } = helpers(ctx);
  const entityId = el.dataset.id;
  if (action === 'team-tab' || action === 'team-project-tab') {
    const allowed = action === 'team-tab' ? ['members', 'organization', 'roles', 'agents', 'activity'] : ['tasks', 'context', 'members'];
    if (allowed.includes(el.dataset.tab)) state[action === 'team-tab' ? 'teamTab' : 'projectTab'] = el.dataset.tab;
    ctx.render();
    return true;
  }
  if (action === 'team-add-member') {
    ctx.modal(t('team.addMember'), `<form id="team-member-form"><label class="form-field"><span>${tr('team.name')}</span><input name="name" required maxlength="40" placeholder="${tr('team.namePlaceholder')}" autocomplete="off"></label><label class="form-field"><span>${tr('team.role')}</span><select name="role"><option value="member">${tr('team.role.member')}</option><option value="admin">${tr('team.role.admin')}</option></select></label><p class="prototype-note">${tr('team.localNote')}</p></form>`, btn('close', 'team.cancel') + btn('team-save-member', 'team.add', '', 'primary'));
    return true;
  }
  if (action === 'team-save-member') {
    const form = document.querySelector('#team-member-form');
    if (!form?.reportValidity()) return true;
    const values = new FormData(form), name = String(values.get('name') || '').trim();
    if (!name) { ctx.toast(t('team.nameRequired')); form.elements.name.focus(); return true; }
    data.teamMembers.push({ id: id('m'), name: name.slice(0, 40), role: values.get('role') === 'admin' ? 'admin' : 'member', departmentId: '', status: 'active' });
    record(data, 'memberAdded', { name });
    finish(ctx, 'team.memberAdded');
    return true;
  }
  if (action === 'team-edit-role') {
    const member = data.teamMembers.find(m => m.id === entityId);
    if (!member || member.role === 'owner') return true;
    ctx.modal(t('team.changeRole'), `<form id="team-role-form"><p>${e(member.name)}</p><label class="form-field"><span>${tr('team.role')}</span><select name="role">${['member', 'admin'].map(role => `<option value="${role}" ${member.role === role ? 'selected' : ''}>${tr('team.role.' + role)}</option>`).join('')}</select></label><p class="prototype-note">${tr('team.roleNote')}</p></form>`, btn('close', 'team.cancel') + btn('team-save-role', 'team.save', `data-id="${e(entityId)}"`, 'primary'));
    return true;
  }
  if (action === 'team-save-role') {
    const member = data.teamMembers.find(m => m.id === entityId), form = document.querySelector('#team-role-form');
    if (!member || member.role === 'owner' || !form) return true;
    member.role = new FormData(form).get('role') === 'admin' ? 'admin' : 'member';
    record(data, 'roleChanged', { name: member.name });
    finish(ctx, 'team.roleSaved');
    return true;
  }
  if (action === 'team-manage-agents') {
    ctx.modal(t('team.manageAgents'), `<form id="team-agents-form">${checks(list(data.agents), list(data.teamAgentIds), 'agents', ctx, a => ctx.avatar(a.avatar, 28))}<p class="prototype-note">${tr('team.sharingNote')}</p></form>`, btn('close', 'team.cancel') + btn('team-save-agents', 'team.save', '', 'primary'));
    return true;
  }
  if (action === 'team-save-agents') {
    const form = document.querySelector('#team-agents-form');
    if (!form) return true;
    const selected = new FormData(form).getAll('agents');
    data.teamAgentIds = list(data.agents).filter(a => selected.includes(a.id)).map(a => a.id);
    record(data, 'agentsChanged');
    finish(ctx, 'team.agentSaved');
    return true;
  }
  if (action === 'team-edit-context') {
    const project = data.projects.find(p => p.id === entityId);
    if (!project) return true;
    ctx.modal(t('project.editContext'), `<form id="team-context-form"><label class="form-field"><span>${tr('project.contextTitle')}</span><textarea name="context" rows="9" maxlength="6000" placeholder="${tr('project.contextPlaceholder')}">${e(project.sharedContext)}</textarea></label><p class="prototype-note">${tr('project.contextNote')}</p></form>`, btn('close', 'team.cancel') + btn('team-save-context', 'team.save', `data-id="${e(entityId)}"`, 'primary'));
    return true;
  }
  if (action === 'team-save-context') {
    const project = data.projects.find(p => p.id === entityId), form = document.querySelector('#team-context-form');
    if (!project || !form?.reportValidity()) return true;
    project.sharedContext = String(new FormData(form).get('context') || '').trim().slice(0, 6000);
    record(data, 'contextChanged', { project: project.name, projectId: project.id });
    finish(ctx, 'project.contextSaved');
    return true;
  }
  if (action === 'team-project-roster') {
    const project = data.projects.find(p => p.id === entityId);
    if (!project) return true;
    ctx.modal(t('project.manageRoster'), `<form id="team-roster-form"><fieldset class="wx-team-fieldset"><legend>${tr('team.members')}</legend>${checks(data.teamMembers, list(project.memberIds), 'members', ctx, member => person(member, 'is-small'))}</fieldset><fieldset class="wx-team-fieldset"><legend>${tr('project.supportingAgents')}</legend>${checks(list(data.agents), list(project.agentIds), 'agents', ctx, agent => ctx.avatar(agent.avatar, 26))}</fieldset><p class="prototype-note">${tr('project.rosterNote')}</p></form>`, btn('close', 'team.cancel') + btn('team-save-roster', 'team.save', `data-id="${e(entityId)}"`, 'primary'));
    return true;
  }
  if (action === 'team-save-roster') {
    const project = data.projects.find(p => p.id === entityId), form = document.querySelector('#team-roster-form');
    if (!project || !form) return true;
    const values = new FormData(form), members = data.teamMembers.filter(m => values.getAll('members').includes(m.id)).map(m => m.id), agents = list(data.agents).filter(a => values.getAll('agents').includes(a.id)).map(a => a.id);
    if (!members.length || !agents.length) { ctx.toast(t('project.rosterRequired')); return true; }
    project.memberIds = members;
    project.agentIds = agents;
    record(data, 'rosterChanged', { project: project.name, projectId: project.id });
    finish(ctx, 'project.rosterSaved');
    return true;
  }
  if (action === 'team-assign-task') {
    const task = data.tasks.find(item => item.id === entityId);
    if (!task) return true;
    const project = data.projects.find(p => p.id === task.project);
    const members = data.teamMembers.filter(m => !project || list(project.memberIds).includes(m.id));
    const agents = list(data.agents).filter(a => a.id !== task.agent && (!project || list(project.agentIds).includes(a.id)));
    const oldOwner = data.teamMembers.find(m => m.id === task.ownerId && !members.some(member => member.id === m.id));
    ctx.modal(t('project.assignTask'), `<form id="team-assignment-form"><p class="wx-team-dialog-title">${e(task.name)}</p><label class="form-field"><span>${tr('project.owner')}</span><select name="owner"><option value="">${tr('project.unassigned')}</option>${oldOwner ? `<option value="${e(oldOwner.id)}" selected>${e(oldOwner.name)} · ${tr('project.memberOutside')}</option>` : ''}${members.map(member => `<option value="${e(member.id)}" ${member.id === task.ownerId ? 'selected' : ''}>${e(member.name)}</option>`).join('')}</select></label><fieldset class="wx-team-fieldset"><legend>${tr('project.supportingAgents')}</legend>${agents.length ? checks(agents, list(task.supportingAgentIds), 'agents', ctx, a => ctx.avatar(a.avatar, 26)) : `<p class="wx-team-caption">${tr('project.noSupporting')}</p>`}</fieldset><p class="prototype-note">${tr('project.assignNote')}</p></form>`, btn('close', 'team.cancel') + btn('team-save-assignment', 'team.save', `data-id="${e(entityId)}"`, 'primary'));
    return true;
  }
  if (action === 'team-save-assignment') {
    const task = data.tasks.find(item => item.id === entityId), form = document.querySelector('#team-assignment-form');
    if (!task || !form) return true;
    const values = new FormData(form), project = data.projects.find(p => p.id === task.project), owner = values.get('owner');
    task.ownerId = data.teamMembers.some(m => m.id === owner && (!project || list(project.memberIds).includes(m.id) || m.id === task.ownerId)) ? owner : '';
    task.supportingAgentIds = list(data.agents).filter(a => a.id !== task.agent && (!project || list(project.agentIds).includes(a.id)) && values.getAll('agents').includes(a.id)).map(a => a.id);
    record(data, 'assigned', { task: task.name, projectId: task.project || '' });
    finish(ctx, 'project.assignSaved');
    return true;
  }
  if (action === 'team-accept-task' || action === 'team-reopen-task') {
    const task = data.tasks.find(item => item.id === entityId);
    if (!task) return true;
    if (task.status !== 'done') { ctx.toast(t('project.runningReview')); return true; }
    const accepted = action === 'team-accept-task';
    if ((task.reviewState === 'accepted') === accepted) return true;
    task.reviewState = accepted ? 'accepted' : 'review';
    record(data, accepted ? 'accepted' : 'reopened', { task: task.name, projectId: task.project || '' });
    finish(ctx, accepted ? 'project.confirmed' : 'project.reopened');
    return true;
  }
  return false;
}
