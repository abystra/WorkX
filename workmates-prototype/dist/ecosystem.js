import { t } from './i18n.js';
import { openConnection, renderConnectionStatus } from './connection.js';
import { reconcileConnection } from './connection-model.js';
import { channelBindingReady } from './channel-model.js';
import { PLATFORMS, METHODS, CAPABILITIES, platformBy, methodBy, capabilityBy, normalizeCapabilities, bindingIsReady, ensureEcosystemData } from './ecosystem-model.js';
export { ensureEcosystemData } from './ecosystem-model.js';
const text = (ctx, key, params) => (ctx.t || t)(key, params);
const translated = (ctx, key, params) => ctx.escape(text(ctx, key, params));
const button = (ctx, action, key, extra = '', primary = false, symbol = '') => `<button type="button" class="btn${primary ? ' primary' : ''}" data-action="${action}" ${extra}>${symbol ? ctx.icon(symbol, 15) : ''}${translated(ctx, key)}</button>`;
function platformMark(platform, ctx) { return `<span class="wx-eco-mark wx-eco-mark-${platform.id}" aria-hidden="true">${ctx.icon(platform.icon, 23)}</span>`; }
function statusKey(binding, ctx) { return !bindingIsReady(binding, ctx.data) ? 'eco.needsReview' : binding.enabled === false ? 'eco.paused' : 'eco.configured'; }
function capabilityTags(binding, ctx) {
  const caps = (Array.isArray(binding.capabilities) ? binding.capabilities : []).filter(id => capabilityBy(id));
  return caps.length ? caps.map(id => `<span class="wx-eco-cap-tag">${translated(ctx, capabilityBy(id).name)}<small>${translated(ctx, 'eco.authPending')}</small></span>`).join('') : `<span class="wx-eco-muted">${translated(ctx, 'eco.capabilitiesPending')}</span>`;
}
function bindingRows(bindings, ctx) {
  const tr = (key, params) => translated(ctx, key, params);
  return `<div class="wx-eco-bindings">${bindings.map(binding => {
    const platform = platformBy(binding.platform), method = methodBy(binding.method), agent = ctx.data.agents.find(item => item.id === binding.assignedAgent), id = ctx.escape(binding.id);
    const ready = bindingIsReady(binding, ctx.data);
    return `<article class="wx-eco-binding"><div class="wx-eco-binding-main"><div class="wx-eco-binding-heading">${platform ? platformMark(platform, ctx) : ''}<div><h3>${ctx.escape(binding.name || text(ctx, 'eco.unnamed'))}</h3><p>${platform ? tr(platform.name) : tr('eco.platformPending')}<span> / </span>${method ? tr(method.name) : tr('eco.modeUndecided')}</p></div><span class="wx-eco-status${ready && binding.enabled !== false ? ' is-configured' : ''}">${tr(statusKey(binding, ctx))}</span></div><div class="wx-eco-binding-details"><div class="wx-eco-binding-agent"><span>${tr('eco.agent')}</span>${agent ? ctx.avatar(agent.avatar, 24) + `<strong>${ctx.escape(agent.name)}</strong>` : `<strong>${tr('eco.notAssigned')}</strong>`}</div><div class="wx-eco-binding-caps"><span>${tr('eco.requestedCapabilities')}</span><div>${capabilityTags(binding, ctx)}</div></div></div>${renderConnectionStatus(binding, ctx)}</div><div class="wx-eco-binding-actions">${method?.kind==='dialogue' ? button(ctx, 'channel-compose', 'workspace.simulateMessage', `data-binding="${id}" ${channelBindingReady(binding,ctx.data)?'':`disabled title="${tr('workspace.channelRequiresSetup')}"`}`) : ''}${ready ? button(ctx, 'conn-open', 'conn.open', `data-id="${id}"`, false, 'settings') : ''}${button(ctx, 'eco-edit', 'eco.edit', `data-id="${id}"`, false, 'edit')}${button(ctx, 'eco-preview', 'eco.preview', `data-id="${id}"`, false, 'play')}${ready || binding.enabled !== false ? button(ctx, 'eco-toggle', binding.enabled === false ? 'eco.enable' : 'eco.disable', `data-id="${id}"`) : ''}<button type="button" class="text-btn wx-eco-delete" data-action="eco-delete" data-id="${id}" aria-label="${tr('eco.deleteNamed', {name: binding.name})}">${tr('eco.delete')}</button></div></article>`;
  }).join('')}</div>`;
}
export function renderEcosystem(ctx) {
  ensureEcosystemData(ctx.data);
  const tr = (key, params) => translated(ctx, key, params), bindings = ctx.data.ecosystemBindings;
  const cards = PLATFORMS.map(platform => `<article class="wx-eco-card"><div class="wx-eco-card-top">${platformMark(platform, ctx)}<div class="wx-eco-card-name"><h2>${tr(platform.name)}</h2><span>${tr(platform.type)}</span></div><span class="wx-eco-platform-count">${tr('eco.bindingCount', {count: bindings.filter(item => item.platform === platform.id).length})}</span></div><p class="wx-eco-description">${tr(platform.description)}</p><ul class="wx-eco-method-list">${METHODS.filter(item => item.platform === platform.id).map(method => `<li><span>${tr(method.name)}</span><small>${tr('eco.kind.' + method.kind)}</small></li>`).join('')}</ul><div class="wx-eco-card-actions">${button(ctx, 'eco-add', 'eco.addPlatform', `data-platform="${platform.id}"`, false, 'plus')}</div></article>`).join('');
  return `<section class="wx-eco-page"><header class="wx-eco-heading"><div><h1>${tr('eco.title')}</h1><p>${tr('eco.subtitle')}</p></div>${button(ctx, 'eco-add', 'eco.add', '', true, 'plus')}</header><div class="wx-eco-notice">${ctx.icon('help', 17)}<p>${tr('eco.notice')}</p></div><div class="wx-eco-section-heading"><h2>${tr('eco.platforms')}</h2><span>${tr('eco.platformHint')}</span></div><div class="wx-eco-grid">${cards}</div><div class="wx-eco-section-heading wx-eco-bindings-heading"><h2>${tr('eco.myBindings')}</h2><span>${tr('eco.bindingCount', {count: bindings.length})}</span></div>${bindings.length ? bindingRows(bindings, ctx) : `<div class="wx-eco-empty">${ctx.icon('layers', 26)}<h3>${tr('eco.emptyTitle')}</h3><p>${tr('eco.emptyBody')}</p>${button(ctx, 'eco-add', 'eco.add', '', false, 'plus')}</div>`}<aside class="wx-eco-extension"><span class="wx-eco-extension-icon">${ctx.icon('hub', 25)}</span><div><h2>${tr('eco.extensionTitle')}</h2><p>${tr('eco.extensionBody')}</p></div><button type="button" class="text-btn" data-action="nav" data-page="scenarios">${tr('eco.openScenarios')}${ctx.icon('arrow', 15)}</button></aside></section>`;
}
export function renderAgentEcosystem(agentId, ctx) {
  ensureEcosystemData(ctx.data);
  const tr = (key, params) => translated(ctx, key, params), bindings = ctx.data.ecosystemBindings.filter(item => item.assignedAgent === agentId);
  return `<section class="wx-eco-agent-section"><div class="wx-eco-section-heading"><div><h2>${tr('eco.agentBindings')}</h2><p>${tr('eco.agentBindingsHint')}</p></div>${button(ctx, 'eco-add', 'eco.add', `data-agent="${ctx.escape(agentId)}"`, false, 'plus')}</div>${bindings.length ? bindingRows(bindings, ctx) : `<div class="wx-eco-agent-empty">${ctx.icon('globe', 22)}<p>${tr('eco.agentEmpty')}</p></div>`}</section>`;
}
function newWizard(ctx, options = {}) {
  const binding = options.binding, platform = binding?.platform || options.platform || '';
  const draft = binding ? {...binding, capabilities: [...(binding.capabilities || [])]} : {platform, method: '', name: '', assignedAgent: options.agent || '', capabilities: [], enabled: true, transport: 'websocket'};
  ctx.state.ecosystemWizard = {step: binding ? 1 : platform ? 2 : 1, editingId: binding?.id || null, draft, error: ''};
  rerenderEcosystemWizard(ctx);
}
export function captureEcosystemWizard(ctx) {
  const wizard = ctx.state.ecosystemWizard, form = document.querySelector('#eco-wizard-form');
  if (!wizard || !form) return false;
  const values = new FormData(form);
  if (wizard.step === 2 && wizard.draft.method === 'wecom-ai-bot') wizard.draft.transport = values.get('transport') || wizard.draft.transport || 'websocket';
  if (wizard.step === 3) wizard.draft.assignedAgent = values.get('assignedAgent') || '';
  if (wizard.step === 4) {
    wizard.draft.name = String(values.get('name') || '');
    wizard.draft.capabilities = normalizeCapabilities(wizard.draft.method, values.getAll('capabilities'));
  }
  return true;
}
function wizardStageError(wizard, ctx, all = false) {
  const draft = wizard.draft, method = methodBy(draft.method);
  if ((all || wizard.step === 1) && !platformBy(draft.platform)) return 'eco.requiredPlatform';
  if ((all || wizard.step === 2) && (!method || method.platform !== draft.platform || (method.id === 'wecom-ai-bot' && !['websocket','callback'].includes(draft.transport)))) return 'eco.requiredMethod';
  if ((all || wizard.step === 3) && !ctx.data.agents.some(agent => agent.id === draft.assignedAgent)) return 'eco.selectAgent';
  if (all || wizard.step === 4) {
    if (!draft.name.trim() || draft.name.trim().length > 60) return 'eco.requiredName';
    if (!bindingIsReady({...draft, configured: true}, ctx.data)) return 'eco.requiredCapability';
  }
  return '';
}
export function rerenderEcosystemWizard(ctx) {
  const wizard = ctx.state.ecosystemWizard;
  if (!wizard) return;
  const tr = (key, params) => translated(ctx, key, params), draft = wizard.draft, method = methodBy(draft.method), platform = platformBy(draft.platform);
  const steps = ['eco.stepPlatform','eco.stepMethod','eco.stepAgent','eco.stepCapabilities'];
  const stepper = `<ol class="wx-eco-stepper" aria-label="${tr('eco.setupProgress')}">${steps.map((key, index) => `<li class="${index + 1 === wizard.step ? 'is-current' : index + 1 < wizard.step ? 'is-complete' : ''}" ${index + 1 === wizard.step ? 'aria-current="step"' : ''}><span>${index + 1 < wizard.step ? ctx.icon('check', 13) : index + 1}</span><strong>${tr(key)}</strong></li>`).join('')}</ol>`;
  let body = '';
  if (wizard.step === 1) body = `<p class="wx-eco-step-intro">${tr('eco.choosePlatformHint')}</p><div class="wx-eco-platform-options">${PLATFORMS.map(item => `<button type="button" class="wx-eco-option${draft.platform === item.id ? ' is-selected' : ''}" data-action="eco-platform" data-value="${item.id}" aria-pressed="${draft.platform === item.id}">${platformMark(item, ctx)}<strong>${tr(item.name)}</strong><span>${tr(item.description)}</span></button>`).join('')}</div>`;
  if (wizard.step === 2) body = `<p class="wx-eco-step-intro">${tr('eco.chooseMethodHint', {platform: text(ctx, platform?.name || 'eco.platformPending')})}</p><div class="wx-eco-method-options">${METHODS.filter(item => item.platform === draft.platform).map(item => `<button type="button" class="wx-eco-method-option${draft.method === item.id ? ' is-selected' : ''}" data-action="eco-method" data-value="${item.id}" aria-pressed="${draft.method === item.id}"><span class="wx-eco-radio" aria-hidden="true"></span><span><strong>${tr(item.name)}<small>${tr('eco.kind.' + item.kind)}</small></strong><span>${tr(item.description)}</span></span></button>`).join('')}</div>${method?.id === 'wecom-ai-bot' ? `<label class="form-field wx-eco-transport"><span>${tr('eco.transport')}</span><select name="transport"><option value="websocket" ${draft.transport === 'websocket' ? 'selected' : ''}>${tr('eco.websocket')}</option><option value="callback" ${draft.transport === 'callback' ? 'selected' : ''}>${tr('eco.callback')}</option></select><small>${tr('eco.transportHint')}</small></label>` : ''}`;
  if (wizard.step === 3) body = `<p class="wx-eco-step-intro">${tr('eco.chooseAgentHint')}</p><label class="form-field"><span>${tr('eco.agent')}</span><select name="assignedAgent" required><option value="">${tr('eco.selectAgent')}</option>${ctx.data.agents.map(agent => `<option value="${ctx.escape(agent.id)}" ${agent.id === draft.assignedAgent ? 'selected' : ''}>${ctx.escape(agent.name)}</option>`).join('')}</select></label>${!ctx.data.agents.length ? `<p class="wx-eco-error">${tr('eco.noAgents')}</p>` : ''}<div class="wx-eco-form-note"><strong>${tr('eco.reuseAgentTitle')}</strong><p>${tr('eco.reuseAgentHint')}</p></div><div class="wx-eco-agent-reference">${ctx.data.agents.filter(agent => ctx.data.ecosystemBindings.some(item => item.assignedAgent === agent.id)).slice(0, 4).map(agent => `<span>${ctx.avatar(agent.avatar, 24)}<strong>${ctx.escape(agent.name)}</strong><small>${tr('eco.bindingCount', {count: ctx.data.ecosystemBindings.filter(item => item.assignedAgent === agent.id).length})}</small></span>`).join('')}</div>`;
  if (wizard.step === 4) {
    const allowed = method ? [...method.required,...method.optional] : [];
    body = `<label class="form-field"><span>${tr('eco.configName')}</span><input name="name" maxlength="60" required value="${ctx.escape(draft.name)}" placeholder="${tr('eco.namePlaceholder')}" autocomplete="off"></label><div class="wx-eco-form-note"><strong>${tr('eco.authPending')}</strong><p>${tr('eco.authHint')}</p></div>${['messages','tools'].map(group => {
      const caps = CAPABILITIES.filter(item => item.group === group && allowed.includes(item.id));
      if (!caps.length) return '';
      return `<fieldset class="wx-eco-capabilities"><legend>${tr('eco.group.' + group)}</legend>${caps.map(cap => `<label class="wx-eco-capability"><input type="checkbox" name="capabilities" value="${cap.id}" ${draft.capabilities.includes(cap.id) ? 'checked' : ''} ${method.required.includes(cap.id) ? 'disabled' : ''}><span><strong>${tr(cap.name)}${method.required.includes(cap.id) ? `<small>${tr('eco.required')}</small>` : ''}</strong><span>${tr(cap.description)}</span></span><em>${tr('eco.authPending')}</em></label>`).join('')}</fieldset>`;
    }).join('')}${method?.kind === 'tools' ? `<p class="wx-eco-form-footnote">${tr('eco.atLeastOneTool')}</p>` : ''}<div class="wx-eco-review"><span>${tr('eco.review')}</span><strong>${platform ? tr(platform.name) : ''} <i>→</i> ${method ? tr(method.name) : ''} <i>→</i> ${ctx.escape(ctx.data.agents.find(agent => agent.id === draft.assignedAgent)?.name || '')}</strong>${method?.id === 'wecom-ai-bot' ? `<small>${tr(draft.transport === 'websocket' ? 'eco.websocket' : 'eco.callback')}</small>` : ''}</div>`;
  }
  ctx.closeOverlay();
  ctx.modal(text(ctx, wizard.editingId ? 'eco.editBinding' : 'eco.add'), `${stepper}<form id="eco-wizard-form" data-step="${wizard.step}"><h3 class="wx-eco-step-title">${tr(steps[wizard.step - 1])}</h3>${body}${wizard.error ? `<p class="wx-eco-error" role="alert">${tr(wizard.error)}</p>` : ''}<p class="wx-eco-form-footnote">${tr('eco.localOnly')}</p></form>`, `<div class="wx-eco-wizard-footer">${button(ctx, 'eco-cancel', 'eco.cancel')}<div>${wizard.step > 1 ? button(ctx, 'eco-back', 'eco.back') : ''}${button(ctx, wizard.step < 4 ? 'eco-next' : 'eco-save', wizard.step < 4 ? 'eco.next' : 'eco.save', '', true)}</div></div>`, 'wx-eco-wizard');
}
function showPreview(binding, ctx) {
  const tr = (key, params) => translated(ctx, key, params), method = methodBy(binding.method), platform = platformBy(binding.platform), agent = ctx.data.agents.find(item => item.id === binding.assignedAgent);
  if (!platform) return;
  const kind = method?.kind, ready = bindingIsReady(binding, ctx.data), active = ready && binding.enabled !== false;
  const node = (icon, label, name) => `<div>${icon}<span>${tr(label)}</span><strong>${ctx.escape(name)}</strong></div>`;
  const arrow = `<span class="wx-eco-preview-arrow" aria-hidden="true">${ctx.icon('arrow', 18)}</span>`;
  const mate = node(agent ? ctx.avatar(agent.avatar, 40) : ctx.icon('robot', 28), 'eco.agent', agent?.name || text(ctx, 'eco.notAssigned'));
  const platformNode = node(platformMark(platform, ctx), kind === 'notification' ? 'eco.notificationTarget' : kind === 'tools' ? 'eco.toolTarget' : 'eco.previewEntry', text(ctx, platform.name));
  const flow = !kind ? '' : kind === 'dialogue' ? platformNode + `<span class="wx-eco-preview-arrow" aria-hidden="true">↔</span>` + mate + arrow + node(`<span class="wx-eco-mark">${ctx.icon('folder', 23)}</span>`, 'eco.previewResult', 'WorkX') : mate + arrow + platformNode;
  ctx.closeOverlay();
  ctx.modal(text(ctx, 'eco.previewTitle', {platform: text(ctx, platform.name)}), `<h3 class="wx-eco-preview-name">${ctx.escape(binding.name || text(ctx, 'eco.unnamed'))}</h3><p class="wx-eco-preview-intro">${tr(kind ? 'eco.preview.' + kind : 'eco.reviewBeforePreview')}</p>${flow ? `<div class="wx-eco-preview-flow">${flow}</div>` : ''}<div class="wx-eco-preview-caps">${capabilityTags(binding, ctx)}</div><div class="wx-eco-form-note"><strong>${tr(statusKey(binding, ctx))}</strong><p>${tr(!ready ? 'eco.reviewBeforePreview' : binding.enabled === false ? 'eco.pausedHint' : 'eco.previewLocalNote')}</p></div><p class="wx-eco-form-footnote">${tr('eco.authHint')}</p>`, button(ctx, 'close', 'eco.close') + (!ready ? button(ctx, 'eco-edit', 'eco.editBinding', `data-id="${ctx.escape(binding.id)}"`, true) : active && kind === 'dialogue' ? button(ctx, 'eco-try-task', 'eco.tryTask', `data-id="${ctx.escape(binding.id)}"`, true) : ''));
}
export function renderScenarios(ctx) {
  ensureEcosystemData(ctx.data);
  const e = ctx.escape;
  const tr = (key, params) => translated(ctx, key, params);
  const drafts = ctx.data.scenarioDrafts;
  const body = drafts.length ? `<div class="wx-scene-list-heading"><h2>${tr('scene.drafts')}</h2><span>${tr('scene.draftCount', {count: drafts.length})}</span></div><div class="wx-scene-list">${drafts.map(draft => `<article class="wx-scene-draft"><div class="wx-scene-draft-icon">${ctx.icon('grid', 21)}</div><div class="wx-scene-draft-body"><div class="wx-scene-draft-title"><h3>${e(draft.name)}</h3><span class="wx-scene-draft-tag">${tr('scene.draft')}</span></div><p>${e(draft.problem)}</p><div class="wx-scene-draft-meta"><span>${ctx.icon('users', 13)}${e(draft.role || text(ctx, 'scene.rolePending'))}</span><span>${ctx.icon('globe', 13)}${(draft.ecosystems || []).filter(id => platformBy(id)).map(id => tr(platformBy(id).name)).join(' · ') || tr('scene.ecosystemPending')}</span></div></div><button type="button" class="btn" data-action="scenario-edit" data-id="${e(draft.id)}" aria-label="${tr('scene.editNamed', {name: draft.name})}">${ctx.icon('edit', 14)}${tr('scene.edit')}</button></article>`).join('')}</div><p class="wx-scene-draft-note">${ctx.icon('help', 14)}${tr('scene.draftNotice')}</p>` : `<div class="wx-scene-empty"><div class="wx-scene-empty-art" aria-hidden="true"><span>${ctx.icon('users', 24)}</span><i></i><span class="wx-scene-empty-core">${ctx.icon('grid', 34)}</span><i></i><span>${ctx.icon('robot', 24)}</span></div><span class="wx-scene-empty-kicker">${tr('scene.emptyHint')}</span><h2>${tr('scene.emptyTitle')}</h2><p>${tr('scene.emptyBody')}</p>${button(ctx, 'scenario-create', 'scene.record', '', true, 'plus')}</div>`;
  return `<section class="wx-scene-page"><header class="wx-eco-heading"><div><div class="wx-scene-title-line"><h1>${tr('scene.title')}</h1><span class="wx-eco-header-badge">${tr('scene.reserved')}</span></div><p>${tr('scene.subtitle')}</p></div>${button(ctx, 'scenario-create', 'scene.record', '', true, 'plus')}</header>${body}<div class="wx-scene-flow">${[1, 2, 3, 4].map(step => `<div><span>0${step}</span><p>${tr('scene.flow' + step)}</p></div>`).join('')}</div><div class="wx-scene-footer"><span>${tr('scene.draftNotice')}</span><button type="button" class="text-btn" data-action="nav" data-page="ecosystem">${tr('scene.ecosystemLink')}${ctx.icon('arrow', 15)}</button></div></section>`;
}

function showScenarioForm(draft, ctx) {
  const e = ctx.escape;
  const tr = (key, params) => translated(ctx, key, params);
  const item = draft || {};
  const field = (name, label, placeholder, required = false, multiline = false) => `<label class="form-field"><span>${tr(label)}${required ? '' : ` <small class="wx-scene-optional">${tr('scene.optional')}</small>`}</span>${multiline ? `<textarea name="${name}" maxlength="600" ${required ? 'required' : ''} placeholder="${tr(placeholder)}">${e(item[name] || '')}</textarea>` : `<input name="${name}" maxlength="${name === 'name' ? 60 : 100}" ${required ? 'required' : ''} value="${e(item[name] || '')}" placeholder="${tr(placeholder)}" autocomplete="off">`}</label>`;
  ctx.closeOverlay();
  ctx.modal(text(ctx, draft ? 'scene.editTitle' : 'scene.createTitle'), `<form id="scenario-form" data-id="${e(item.id || '')}">${field('name', 'scene.name', 'scene.namePlaceholder', true)}${field('problem', 'scene.problem', 'scene.problemPlaceholder', true, true)}${field('role', 'scene.role', 'scene.rolePlaceholder')}<div class="wx-scene-form-columns">${field('input', 'scene.input', 'scene.inputPlaceholder', false, true)}${field('output', 'scene.output', 'scene.outputPlaceholder', false, true)}</div><fieldset class="wx-scene-ecosystem-options"><legend>${tr('scene.ecosystems')}</legend>${PLATFORMS.map(platform => `<label><input type="checkbox" name="ecosystems" value="${platform.id}" ${(item.ecosystems || []).includes(platform.id) ? 'checked' : ''}>${tr(platform.name)}</label>`).join('')}<p>${tr('scene.ecosystemHint')}</p></fieldset><p class="wx-eco-form-footnote">${tr('scene.draftNotice')}</p></form>`, (draft ? `<button type="button" class="text-btn wx-scene-delete" data-action="scenario-delete" data-id="${e(draft.id)}">${tr('scene.remove')}</button>` : '') + button(ctx, 'close', 'eco.cancel') + button(ctx, 'scenario-save', 'scene.save', '', true), 'wx-scene-modal');
}

function requiredText(form, name, ctx, key) {
  const field = form.elements.namedItem(name);
  if (!field.value.trim()) {
    field.setCustomValidity(text(ctx, key));
    field.reportValidity();
    field.setCustomValidity('');
    return false;
  }
  return true;
}

export function handleEcosystemAction(action, el, ctx) {
  if (!action.startsWith('eco-') && !action.startsWith('scenario-')) return false;
  ensureEcosystemData(ctx.data);
  const id = el.dataset.id, binding = ctx.data.ecosystemBindings.find(item => item.id === id);
  const wizard = ctx.state.ecosystemWizard;
  if (action === 'eco-add' || action === 'eco-configure') {
    const platform = platformBy(el.dataset.platform || (action === 'eco-configure' ? id : ''))?.id || '';
    const agent = ctx.data.agents.some(item => item.id === el.dataset.agent) ? el.dataset.agent : '';
    newWizard(ctx, {platform, agent});
  } else if (action === 'eco-edit') {
    if (binding) newWizard(ctx, {binding});
  } else if (action === 'eco-cancel') {
    ctx.state.ecosystemWizard = null; ctx.closeOverlay();
  } else if (['eco-platform','eco-method','eco-next','eco-back','eco-save'].includes(action)) {
    if (!wizard) return true;
    captureEcosystemWizard(ctx);
    wizard.error = '';
    if (action === 'eco-platform') {
      if (wizard.step !== 1 || !platformBy(el.dataset.value)) return true;
      if (wizard.draft.platform !== el.dataset.value) Object.assign(wizard.draft, {platform: el.dataset.value, method: '', capabilities: [], transport: 'websocket'});
    } else if (action === 'eco-method') {
      const method = methodBy(el.dataset.value);
      if (wizard.step !== 2 || !method || method.platform !== wizard.draft.platform) return true;
      wizard.draft.method = method.id;
      wizard.draft.capabilities = normalizeCapabilities(method.id, wizard.draft.capabilities);
      if (method.id === 'wecom-ai-bot' && !['websocket','callback'].includes(wizard.draft.transport)) wizard.draft.transport = 'websocket';
    } else if (action === 'eco-back') wizard.step = Math.max(1, wizard.step - 1);
    else if (action === 'eco-next') {
      wizard.error = wizardStageError(wizard, ctx);
      if (!wizard.error) wizard.step = Math.min(4, wizard.step + 1);
    } else {
      if (wizard.step !== 4) return true;
      wizard.error = wizardStageError(wizard, ctx, true);
      if (!wizard.error) {
        const existing = ctx.data.ecosystemBindings.find(item => item.id === wizard.editingId);
        if (wizard.editingId && !existing) { wizard.error = 'eco.bindingMissing'; rerenderEcosystemWizard(ctx); return true; }
        const draft = wizard.draft;
        const saved = {id: existing?.id || 'eco-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8), platform: draft.platform, method: draft.method, name: draft.name.trim(), assignedAgent: draft.assignedAgent, capabilities: normalizeCapabilities(draft.method, draft.capabilities), configured: true, enabled: existing ? existing.enabled !== false : true, ...(draft.method === 'wecom-ai-bot' ? {transport: draft.transport} : {})};
        reconcileConnection(existing, saved);
        if (existing) ctx.data.ecosystemBindings.splice(ctx.data.ecosystemBindings.indexOf(existing), 1, saved);
        else ctx.data.ecosystemBindings.unshift(saved);
        ctx.state.ecosystemWizard = null; ctx.persist(); ctx.closeOverlay(); ctx.render(); ctx.toast(text(ctx, 'eco.saved')); openConnection(saved.id, ctx); return true;
      }
    }
    rerenderEcosystemWizard(ctx);
  } else if (action === 'eco-toggle') {
    if (!binding) return true;
    if (binding.enabled === false && !bindingIsReady(binding, ctx.data)) { ctx.toast(text(ctx, 'eco.reviewBeforeResume')); return true; }
    binding.enabled = binding.enabled === false;
    ctx.persist(); ctx.render(); ctx.toast(text(ctx, binding.enabled ? 'eco.enabled' : 'eco.disabled'));
  } else if (action === 'eco-preview') {
    if (binding) showPreview(binding, ctx);
  } else if (action === 'eco-try-task') {
    if (binding && binding.enabled !== false && bindingIsReady(binding, ctx.data) && methodBy(binding.method)?.kind === 'dialogue') { ctx.closeOverlay(); ctx.navigate('new', binding.assignedAgent); }
  } else if (action === 'eco-delete') {
    if (binding) {
      ctx.closeOverlay();
      ctx.modal(text(ctx, 'eco.deleteTitle'), `<p class="wx-eco-preview-intro">${translated(ctx, 'eco.deleteBody', {name: binding.name})}</p>`, button(ctx, 'close', 'eco.cancel') + button(ctx, 'eco-delete-confirm', 'eco.delete', `data-id="${ctx.escape(id)}"`, true));
    }
  } else if (action === 'eco-delete-confirm') {
    if (!binding) return true;
    ctx.data.ecosystemBindings = ctx.data.ecosystemBindings.filter(item => item.id !== id);
    ctx.persist(); ctx.closeOverlay(); ctx.render(); ctx.toast(text(ctx, 'eco.deleted'));
  }
else if (action === 'scenario-create') showScenarioForm(null, ctx);
  else if (action === 'scenario-edit') {
    const draft = ctx.data.scenarioDrafts.find(item => item.id === id);
    if (draft) showScenarioForm(draft, ctx);
  } else if (action === 'scenario-save') {
    const form = document.querySelector('#scenario-form');
    if (!form || !form.reportValidity() || !requiredText(form, 'name', ctx, 'scene.requiredName') || !requiredText(form, 'problem', ctx, 'scene.requiredProblem')) return true;
    const values = new FormData(form);
    const changes = {name: values.get('name').trim(), problem: values.get('problem').trim(), role: values.get('role').trim(), input: values.get('input').trim(), output: values.get('output').trim(), ecosystems: values.getAll('ecosystems').filter(value => platformBy(value)), status: 'draft'};
    const draft = ctx.data.scenarioDrafts.find(item => item.id === form.dataset.id);
    if (draft) Object.assign(draft, changes);
    else ctx.data.scenarioDrafts.unshift({id: 'sc-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7), ...changes});
    ctx.persist(); ctx.closeOverlay(); ctx.render(); ctx.toast(text(ctx, 'scene.saved'));
  } else if (action === 'scenario-delete') {
    const draft = ctx.data.scenarioDrafts.find(item => item.id === id);
    if (draft) {
      ctx.closeOverlay();
      ctx.modal(text(ctx, 'scene.deleteTitle'), `<p>${translated(ctx, 'scene.deleteBody', {name: draft.name})}</p>`, button(ctx, 'scenario-edit', 'eco.cancel', `data-id="${ctx.escape(id)}"`) + button(ctx, 'scenario-delete-confirm', 'scene.remove', `data-id="${ctx.escape(id)}"`, true));
    }
  } else if (action === 'scenario-delete-confirm') {
    if (!ctx.data.scenarioDrafts.some(item => item.id === id)) return true;
    ctx.data.scenarioDrafts = ctx.data.scenarioDrafts.filter(item => item.id !== id);
    ctx.persist(); ctx.closeOverlay(); ctx.render(); ctx.toast(text(ctx, 'scene.deleted'));
  } else return false;
  return true;
}
