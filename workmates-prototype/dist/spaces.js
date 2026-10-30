import { t, getLocale } from './i18n.js';
import { spaceBy, spaceName, canManageSpace, createOrganization, inviteMembers, transitionInvitation, expireInvitations, saveConnectionMetadata, updateResourceSharing, resourceCollections } from './spaces-model.js';
import { renderRoles } from './saas.js';

const text=(ctx,key,params)=>ctx.escape(t(key,params));
const name=(ctx,space=spaceBy(ctx.spaces))=>ctx.escape(spaceName(space,t('spaces.personal')));
const btn=(ctx,action,key,extra='',primary=false)=>`<button type="button" class="btn${primary?' primary':''}" data-action="${action}" ${extra}>${text(ctx,key)}</button>`;
const field=(ctx,key,body)=>`<label class="form-field"><span>${text(ctx,key)}</span>${body}</label>`;
const note=ctx=>`<p class="ws-local-note">${ctx.icon('help',14)}<span>${text(ctx,'spaces.local')}</span></p>`;
const initials=space=>space.type==='personal'?'A':space.name.slice(0,1).toUpperCase();
function mark(ctx,space,size=''){return `<span class="ws-mark ${space.type==='organization'?'is-org':''} ${size}">${space.type==='personal'?ctx.icon('users',18):ctx.escape(initials(space))}</span>`;}
export function renderSpaceMenu(ctx) {
  const current=spaceBy(ctx.spaces);
  return `<div class="ws-menu"><div class="ws-menu-account"><strong>${ctx.escape(ctx.spaces.user.name)}</strong><small>${ctx.escape(ctx.spaces.user.email)}</small></div><div class="menu-caption">${text(ctx,'spaces.switch')}</div>${ctx.spaces.spaces.map(space=>`<button class="menu-item ws-switch-item" role="menuitemradio" aria-checked="${current.id===space.id}" data-action="space-switch" data-id="${ctx.escape(space.id)}">${mark(ctx,space)}<span><strong>${name(ctx,space)}</strong><small>${text(ctx,space.type==='personal'?'spaces.scope.private':'spaces.organization')}</small></span>${space.id===current.id?ctx.icon('check',16):''}</button>`).join('')}<button class="menu-item" data-action="space-create">${ctx.icon('plus',17)}<span>${text(ctx,'spaces.create')}</span></button><div class="menu-separator"></div>${current.type==='organization'&&canManageSpace(ctx.data)?`<button class="menu-item" data-action="space-invite">${ctx.icon('users',17)}<span>${text(ctx,'spaces.invite')}</span></button><button class="menu-item" data-action="nav" data-page="team" data-id="general">${ctx.icon('settings',17)}<span>${text(ctx,'spaces.manage')}</span></button>`:`<button class="menu-item" data-action="nav" data-page="team" data-id="data">${ctx.icon('folder',17)}<span>${text(ctx,'spaces.data')}</span></button>`}<button class="menu-item" data-action="nav" data-page="settings" data-id="general">${ctx.icon('settings',17)}<span>${text(ctx,'spaces.settings')}</span></button><div class="menu-separator"></div>${[['help','help','Getting started'],...(ctx.data.hideQuick?[['restore-quick','grid','Show Quick start']]:[]),['shortcuts','keyboard','Keyboard shortcuts'],['about','book','About this prototype']].map(([action,ic,label])=>`<button class="menu-item" data-action="${action}">${ctx.icon(ic,17)}<span>${text(ctx,label)}</span></button>`).join('')}</div>`;
}
export function renderSpaceContext(ctx) {
  const space=spaceBy(ctx.spaces);
  return `<div class="ws-context"><button data-action="profile" aria-label="${text(ctx,'spaces.switch')}">${mark(ctx,space,'is-tiny')}<strong>${name(ctx)}</strong><span>${text(ctx,'spaces.'+space.type)}</span>${ctx.icon('chevron',11)}</button><button class="ws-context-data" data-action="nav" data-page="team" data-id="data">${ctx.icon('layers',13)}<span>${text(ctx,'spaces.contextHint')}</span></button></div>`;
}
export function renderSettingsSidebar(ctx) {
  const personal=ctx.state.page==='settings',space=spaceBy(ctx.spaces),isOrg=space.type==='organization';
  const groups=personal?[["spaces.account",[['general','settings','spaces.general'],['profile','users','spaces.profile'],['spaces','layers','spaces.mySpaces']]]]:[
    ['spaces.general',[['general','settings','spaces.workspaceSettings']]],
    ['spaces.identity',isOrg?[['members','users','spaces.members'],['permissions','layers','spaces.permissions']]:[]],
    ['spaces.governance',[['data','folder','spaces.data'],['connections','globe','spaces.integrations'],['usage','grid','spaces.usage'],...(isOrg?[['activity','clock','spaces.activity']]:[])]]
  ];
  return `<aside class="sidebar ws-settings-sidebar"><button class="ws-back" data-action="nav" data-page="home">${ctx.icon('arrow',16)}${text(ctx,'spaces.back')}</button><h2>${text(ctx,personal?'spaces.settings':isOrg?'spaces.manage':'spaces.workspaceSettings')}</h2>${!personal?`<button class="ws-settings-selector" data-action="profile" aria-label="${text(ctx,'spaces.switch')}">${mark(ctx,space)}<span>${name(ctx)}</span>${ctx.icon('chevron',12)}</button>`:`<div class="ws-settings-account"><span class="profile-avatar">${ctx.escape(ctx.spaces.user.name.slice(0,1).toUpperCase())}</span><span>${ctx.escape(ctx.spaces.user.name)}</span></div>`}<nav aria-label="${text(ctx,personal?'spaces.settings':'spaces.workspaceSettings')}">${groups.filter(([,items])=>items.length).map(([label,items])=>`<div class="ws-nav-label">${text(ctx,label)}</div>${items.map(([id,ic,label])=>`<a class="ws-nav-item ${ctx.state.settingsTab===id?'is-active':''}" href="#${personal?'settings':'team'}/${id}" data-action="nav" data-page="${personal?'settings':'team'}" data-id="${id}" ${ctx.state.settingsTab===id?'aria-current="page"':''}>${ctx.icon(ic,17)}${text(ctx,label)}</a>`).join('')}`).join('')}</nav><div class="ws-settings-bottom"><button data-action="profile">${mark(ctx,space,'is-tiny')}<span>${name(ctx)}</span>${ctx.icon('more',16)}</button><button class="text-btn" data-action="nav" data-page="${personal?'team':'settings'}" data-id="general">${text(ctx,personal?(isOrg?'spaces.manage':'spaces.workspaceSettings'):'spaces.settings')}</button></div></aside>`;
}
const section=(title,body,extra='')=>`<section class="ws-section ${extra}">${title?`<h2>${title}</h2>`:''}${body}</section>`;
const row=(label,value,hint='')=>`<div class="ws-setting-row"><div><strong>${label}</strong>${hint?`<p>${hint}</p>`:''}</div><div>${value}</div></div>`;
const empty=(ctx,key,ic='folder')=>`<div class="ws-empty">${ctx.icon(ic,26)}<p>${text(ctx,key)}</p></div>`;
function general(ctx,personal) {
  const {data,spaces}=ctx,space=spaceBy(spaces);
  if(personal)return section(text(ctx,'spaces.general'),row(text(ctx,'spaces.language'),`<select aria-label="${text(ctx,'spaces.language')}" data-space-locale><option value="zh-CN" ${getLocale()==='zh-CN'?'selected':''}>中文</option><option value="en" ${getLocale()==='en'?'selected':''}>English</option></select>`,text(ctx,'spaces.languageHint'))+row(text(ctx,'spaces.notifications'),`<button class="ws-toggle ${spaces.user.notifications?'is-on':''}" role="switch" aria-checked="${!!spaces.user.notifications}" aria-label="${text(ctx,'spaces.notifications')}" data-action="space-toggle-notifications"><span></span></button>`,text(ctx,'spaces.notificationsHint')));
  return section('',`<div class="ws-org-identity">${mark(ctx,space,'is-large')}<div><h2>${name(ctx)}</h2><span>${text(ctx,'spaces.'+space.type)}</span></div></div>`+row(text(ctx,'spaces.spaceId'),`<code>${ctx.escape(space.id)}</code>`)+row(text(ctx,'spaces.spaceType'),text(ctx,'spaces.'+space.type))+row(text(ctx,'spaces.plan'),text(ctx,'spaces.demoPlan'))+(canManageSpace(data)?`<form id="space-name-form" data-tenant="${ctx.escape(space.id)}">${field(ctx,'spaces.spaceName',`<input name="name" maxlength="80" required value="${name(ctx)}">`)}<div class="ws-form-footer">${btn(ctx,'space-save-name','team.save','',true)}</div></form>`:''))+section(text(ctx,'spaces.isolationTitle'),`<p class="ws-body-copy">${text(ctx,'spaces.isolationHint')}</p>${space.type==='personal'?`<div class="ws-callout"><p>${text(ctx,'spaces.personalOnly')}</p>${btn(ctx,'space-create','spaces.create')}</div>`:''}`);
}
function profile(ctx) {
  return section(text(ctx,'spaces.profile'),`<form id="space-profile-form">${field(ctx,'spaces.displayName',`<input name="name" required maxlength="40" value="${ctx.escape(ctx.spaces.user.name)}">`)}${field(ctx,'spaces.email',`<input type="email" value="${ctx.escape(ctx.spaces.user.email)}" readonly>`)}<p class="ws-body-copy">${text(ctx,'spaces.accountHint')}</p><div class="ws-form-footer">${btn(ctx,'space-save-profile','team.save','',true)}</div></form>`);
}
function mySpaces(ctx) {
  return section('',`<div class="ws-space-list">${ctx.spaces.spaces.map(space=>`<div>${mark(ctx,space)}<div><strong>${name(ctx,space)}</strong><small>${text(ctx,'spaces.'+space.type)} · ${text(ctx,'spaces.owner')}</small></div>${btn(ctx,'space-switch','spaces.enter',`data-id="${ctx.escape(space.id)}"`)}</div>`).join('')}</div><div class="ws-form-footer">${btn(ctx,'space-create','spaces.create','',true)}</div>`);
}
function members(ctx) {
  const {data}=ctx,e=ctx.escape;
  expireInvitations(data);
  return `<div class="ws-panel-actions"><p>${text(ctx,'spaces.memberHint')}</p>${canManageSpace(data)?btn(ctx,'space-invite','spaces.invite','',true):''}</div>`+section(`${text(ctx,'spaces.membersCount')} <small>${data.teamMembers.length}</small>`,`<div class="ws-member-list">${data.teamMembers.map(m=>`<div class="ws-member"><span class="ws-mark">${e(m.name.slice(0,1).toUpperCase())}</span><div><strong>${e(m.name)} ${m.id==='m1'?`<small>${text(ctx,'team.you')}</small>`:''}</strong><span>${e(m.email||'—')}</span></div><span class="ws-pill">${text(ctx,'team.role.'+m.role)}</span><span class="ws-member-status">${text(ctx,m.status==='disabled'?'spaces.disabled':'saas.active')}</span>${canManageSpace(data)?`<button class="icon-btn" data-action="saas-member" data-id="${e(m.id)}" aria-label="${text(ctx,'saas.manageMember')} · ${e(m.name)}">${ctx.icon('edit',15)}</button>`:''}</div>`).join('')}</div>`)+section(text(ctx,'spaces.pending'),data.invitations.length?`<div class="ws-invitations">${data.invitations.slice().reverse().map(i=>`<div><div><strong>${e(i.email)}</strong><small>${text(ctx,'team.role.'+i.role)} · ${text(ctx,'spaces.invitation.'+i.status)}</small></div>${i.status==='pending'&&canManageSpace(data)?`<div>${btn(ctx,'space-accept-invite','spaces.acceptDemo',`data-id="${e(i.id)}"`)}<button class="text-btn" data-action="space-cancel-invite" data-id="${e(i.id)}">${text(ctx,'spaces.cancelInvite')}</button></div>`:''}</div>`).join('')}</div>`:empty(ctx,'spaces.noInvitations','users'));
}
function resources(ctx) {
  const collection=resourceCollections.includes(ctx.state.resourceTab)?ctx.state.resourceTab:'projects',data=ctx.data,e=ctx.escape;
  return `<p class="ws-body-copy">${text(ctx,'spaces.resourceHint')}</p><div class="ws-resource-tabs" role="tablist">${resourceCollections.map(c=>`<button role="tab" aria-selected="${c===collection}" class="${c===collection?'is-active':''}" data-action="space-resource-tab" data-id="${c}">${text(ctx,'spaces.kind.'+c)}<small>${data[c].length}</small></button>`).join('')}</div>`+section('',data[collection].length?`<div class="ws-resources">${data[collection].map(r=>`<div><span class="ws-resource-icon">${ctx.icon(collection==='agents'?'robot':collection==='projects'?'folder':'file',19)}</span><div><strong>${e(r.name)}</strong><small>${text(ctx,'spaces.ownerLabel',{name:data.teamMembers.find(m=>m.id===r.resourceOwnerId)?.name||'—'})} · ${name(ctx)}</small></div><span class="ws-pill">${text(ctx,'spaces.scope.'+r.visibility)}</span>${r.resourceOwnerId==='m1'?`<button class="text-btn" data-action="space-sharing" data-id="${e(r.id)}" data-collection="${collection}">${text(ctx,'spaces.sharing')}</button>`:''}</div>`).join('')}</div>`:empty(ctx,'spaces.emptyResources'));
}
function connections(ctx) {
  const {data}=ctx,e=ctx.escape;
  return `<div class="ws-panel-actions"><p>${text(ctx,'spaces.credentialsHint')}</p>${btn(ctx,'space-add-connection','spaces.addConnection','',true)}</div>`+section(text(ctx,'spaces.connectionsCount'),data.connections.length?data.connections.map(c=>`<article class="ws-connection"><div class="ws-connection-top"><span class="ws-mark">${ctx.icon(c.provider==='skill'?'code':'globe',20)}</span><div><strong>${e(c.name)}</strong><small>${e(c.provider==='feishu'?t('eco.feishu'):c.provider==='wecom'?t('eco.wecom'):c.provider.toUpperCase())} · ${text(ctx,'spaces.auth.'+c.authMode)}</small></div><span class="ws-pill ${c.enabled?'':'is-muted'}">${text(ctx,!c.enabled?'spaces.disabled':c.authMode==='none'?'spaces.noAuth':'spaces.needsAuth')}</span></div><div class="ws-connection-meta"><span>${name(ctx)} · ${text(ctx,c.ownerScope==='space'?'spaces.sharedConnection':'spaces.memberConnection')}</span>${btn(ctx,'space-toggle-connection',c.enabled?'spaces.disable':'spaces.enable',`data-id="${e(c.id)}"`)}</div>${c.agentIds.length?`<div class="ws-bound-agents">${text(ctx,'spaces.boundAgents')}：${c.agentIds.map(id=>e(data.agents.find(a=>a.id===id)?.name||id)).join('、')}</div>`:''}<p class="ws-mini-note">${text(ctx,'spaces.bindingHint')}</p></article>`).join(''):empty(ctx,'spaces.noConnections','globe'))+section(text(ctx,'spaces.channelConnections'),`<p class="ws-body-copy">${text(ctx,'spaces.channelHint')}</p>${data.ecosystemBindings.length?data.ecosystemBindings.map(b=>`<div class="ws-setting-row"><div><strong>${e(b.name)}</strong><p>${text(ctx,'spaces.channelScope')} · ${name(ctx)}</p></div><span>${e(b.platform==='feishu'?t('eco.feishu'):t('eco.wecom'))}</span></div>`).join(''):empty(ctx,'spaces.noChannels','chat')}<div class="ws-form-footer">${btn(ctx,'nav','spaces.ecosystem','data-page="ecosystem"')}</div>`);
}
export function renderSettings(ctx) {
  const personal=ctx.state.page==='settings',space=spaceBy(ctx.spaces),tab=ctx.state.settingsTab||'general';
  const labels={general:personal?'spaces.general':'spaces.workspaceSettings',profile:'spaces.profile',spaces:'spaces.mySpaces',members:'spaces.members',permissions:'spaces.permissions',data:'spaces.data',connections:'spaces.integrations',usage:'spaces.usage',activity:'spaces.activity'};
  let body;
  if(personal)body=tab==='profile'?profile(ctx):tab==='spaces'?mySpaces(ctx):general(ctx,true);
  else if(space.type==='personal'&&['members','permissions','activity'].includes(tab))body=section('',`<p>${text(ctx,'spaces.personalOnly')}</p>${btn(ctx,'space-create','spaces.create')}`);
  else if(tab==='members')body=members(ctx);
  else if(tab==='permissions')body=`<p class="ws-body-copy">${text(ctx,'spaces.departmentsHint')}</p>${section('',renderRoles(ctx))}`;
  else if(tab==='data')body=resources(ctx);
  else if(tab==='connections')body=connections(ctx);
  else if(tab==='usage')body=`<p class="ws-body-copy">${text(ctx,'spaces.usageHint')}</p><div class="ws-usage-grid">${[...resourceCollections,'membersCount','connectionsCount'].map(c=>`<div><span>${text(ctx,resourceCollections.includes(c)?'spaces.kind.'+c:'spaces.'+c)}</span><strong>${c==='membersCount'?ctx.data.teamMembers.filter(m=>m.status==='active').length:c==='connectionsCount'?ctx.data.connections.length:ctx.data[c].length}</strong></div>`).join('')}</div>`;
  else if(tab==='activity')body=section('',ctx.data.teamActivity.length?`<ol class="ws-activity">${ctx.data.teamActivity.map(a=>`<li>${ctx.icon('checkcircle',17)}<div><strong>${text(ctx,'spaces.event.'+(a.spaceEvent||'legacy'))}</strong><time>${ctx.escape(new Date(a.at).toLocaleString(getLocale()))}</time></div></li>`).join('')}</ol>`:empty(ctx,'spaces.activityEmpty','clock'));
  else body=general(ctx,false);
  return `<div class="ws-settings-content"><header><div class="ws-breadcrumb">${text(ctx,personal?'spaces.account':'spaces.'+space.type)}${!personal?' / '+name(ctx):''}</div><h1>${text(ctx,labels[tab]||labels.general)}</h1><p>${text(ctx,personal?(tab==='spaces'?'spaces.spacesHint':'spaces.globalHint'):tab==='general'?'spaces.overviewHint':'spaces.contextHint')}</p></header>${body}${note(ctx)}</div>`;
}
function event(ctx,type){ctx.data.teamActivity.unshift({id:'ev-'+Date.now()+Math.random(),at:new Date().toISOString(),spaceEvent:type,tenantId:ctx.data.tenantId});ctx.data.teamActivity=ctx.data.teamActivity.slice(0,80);}
function finish(ctx,key,type){if(type)event(ctx,type);ctx.persist();ctx.closeOverlay();ctx.render();ctx.toast(t(key));}
function formFor(ctx,id){const form=document.querySelector(id);return form&&(!form.dataset?.tenant||form.dataset.tenant===ctx.data.tenantId)&&form.reportValidity()?new FormData(form):null;}
const footer=(ctx,action,extra='')=>btn(ctx,'close','team.cancel')+btn(ctx,action,'team.save',extra,true);
export function handleSpacesAction(action,el,ctx) {
  if(!action.startsWith('space-'))return false;
  const {data,spaces}=ctx,e=ctx.escape,id=el.dataset.id;
  if(action==='space-switch'){ctx.switchWorkspace(id);return true;}
  if(action==='space-create')ctx.modal(t('spaces.create'),`<p class="ws-body-copy">${text(ctx,'spaces.createHint')}</p><form id="space-create-form">${field(ctx,'spaces.orgName',`<input name="name" maxlength="80" required placeholder="${text(ctx,'spaces.orgPlaceholder')}" autocomplete="organization">`)}</form>`,btn(ctx,'close','team.cancel')+btn(ctx,'space-save-organization','spaces.create','',true),'ws-dialog');
  else if(action==='space-save-organization') {
    const values=formFor(ctx,'#space-create-form');if(!values)return true;
    const result=createOrganization(spaces,values.get('name'));if(result.error){ctx.toast(t(result.error));return true;}
    result.space.data.teamActivity.unshift({id:'ev-created',at:new Date().toISOString(),spaceEvent:'created',tenantId:result.space.id});ctx.switchWorkspace(result.space.id,{page:'team',tab:'general',notice:'spaces.created'});
  } else if(action==='space-save-name') {
    if(!canManageSpace(data)){ctx.toast(t('spaces.noPermission'));return true;}
    const values=formFor(ctx,'#space-name-form');if(!values)return true;const value=String(values.get('name')||'').trim();
    if(!value||value.length>80){ctx.toast(t('spaces.invalidName'));return true;}
    if(spaces.spaces.some(s=>s.id!==data.tenantId&&s.type==='organization'&&s.name.toLowerCase()===value.toLowerCase())){ctx.toast(t('spaces.duplicateName'));return true;}
    spaceBy(spaces).name=value;data.enterprise.name=value;finish(ctx,'spaces.saved','settings');
  } else if(action==='space-save-profile') {
    const values=formFor(ctx,'#space-profile-form');if(!values)return true;const value=String(values.get('name')||'').trim();
    if(!value||value.length>40){ctx.toast(t('spaces.profileInvalid'));return true;}
    spaces.user.name=value;for(const space of spaces.spaces){const me=space.data.teamMembers.find(m=>m.id==='m1');if(me)me.name=value;}finish(ctx,'spaces.saved');
  } else if(action==='space-toggle-notifications'){spaces.user.notifications=!spaces.user.notifications;finish(ctx,'spaces.saved');}
  else if(action==='space-invite') {
    if(!canManageSpace(data)){ctx.toast(t('spaces.noPermission'));return true;}
    ctx.modal(t('spaces.invite'),`<p class="ws-body-copy">${text(ctx,'spaces.inviteHint')}</p><div class="ws-dialog-space">${mark(ctx,spaceBy(spaces))}<strong>${name(ctx)}</strong></div><form id="space-invite-form" data-tenant="${e(data.tenantId)}">${field(ctx,'spaces.emails',`<textarea name="emails" rows="3" maxlength="5000" required placeholder="${text(ctx,'spaces.emailsPlaceholder')}"></textarea>`)}${field(ctx,'team.role',`<select name="role"><option value="member">${text(ctx,'team.role.member')}</option><option value="admin">${text(ctx,'team.role.admin')}</option></select>`)}</form>`,btn(ctx,'close','team.cancel')+btn(ctx,'space-save-invite','spaces.createInvitations','',true),'ws-dialog');
  } else if(action==='space-save-invite') {
    const values=formFor(ctx,'#space-invite-form');if(!values)return true;
    const result=inviteMembers(data,{emails:values.get('emails'),role:values.get('role')});if(result.error){ctx.toast(t(result.error));return true;}
    ctx.state.settingsTab='members';finish(ctx,'spaces.invited','invited');ctx.navigate('team','members');
  } else if(action==='space-accept-invite'||action==='space-cancel-invite') {
    const result=transitionInvitation(data,id,action==='space-accept-invite'?'accept':'cancel');if(result.error){ctx.toast(t(result.error));return true;}finish(ctx,'spaces.invitationChanged','invitation');
  } else if(action==='space-resource-tab'){if(resourceCollections.includes(id)){ctx.state.resourceTab=id;ctx.render();}}
  else if(action==='space-sharing') {
    const collection=el.dataset.collection,r=resourceCollections.includes(collection)&&data[collection].find(r=>r.id===id);if(!r||r.resourceOwnerId!=='m1')return true;
    const scopes=data.spaceType==='personal'?['private']:['private','selected','project','space'];
    ctx.modal(t('spaces.sharing'),`<p class="ws-body-copy">${text(ctx,'spaces.sharingHint')}</p><div class="ws-dialog-space">${ctx.icon('file',19)}<strong>${e(r.name)}</strong><span>${name(ctx)}</span></div><form id="space-sharing-form" data-tenant="${e(data.tenantId)}">${field(ctx,'spaces.sharingScope',`<select name="visibility">${scopes.map(s=>`<option value="${s}" ${r.visibility===s?'selected':''}>${text(ctx,'spaces.scope.'+s)}</option>`).join('')}</select>`)}${data.spaceType==='organization'?`<div data-sharing-scope="project" ${r.visibility==='project'?'':'hidden'}>${field(ctx,'spaces.project',`<select name="projectId">${collection==='projects'?'':`<option value="">${text(ctx,'spaces.chooseProject')}</option>`}${(collection==='projects'?[r]:data.projects).map(p=>`<option value="${e(p.id)}" ${(r.project||r.sharingProjectId|| (collection==='projects'?r.id:''))===p.id?'selected':''}>${e(p.name)}</option>`).join('')}</select>`)}</div><fieldset class="wx-team-fieldset" data-sharing-scope="selected" ${r.visibility==='selected'?'':'hidden'}><legend>${text(ctx,'spaces.chooseMembers')}</legend>${data.teamMembers.filter(m=>m.status==='active'&&m.id!=='m1').map(m=>`<label class="wx-team-choice"><input type="checkbox" name="members" value="${e(m.id)}" ${r.sharedMemberIds?.includes(m.id)?'checked':''}>${e(m.name)}</label>`).join('')}</fieldset>`:''}</form>`,footer(ctx,'space-save-sharing',`data-id="${e(id)}" data-collection="${e(collection)}"`),'ws-dialog');
  } else if(action==='space-save-sharing') {
    const values=formFor(ctx,'#space-sharing-form');if(!values)return true;
    const result=updateResourceSharing(data,el.dataset.collection,id,{visibility:values.get('visibility'),memberIds:values.getAll('members'),projectId:values.get('projectId')});if(result.error){ctx.toast(t(result.error));return true;}finish(ctx,'spaces.saved','sharing');
  } else if(action==='space-add-connection') {
    ctx.modal(t('spaces.addConnection'),`<p class="ws-body-copy">${text(ctx,'spaces.connectionFormHint')}</p><div class="ws-dialog-space">${mark(ctx,spaceBy(spaces))}<strong>${name(ctx)}</strong></div><form id="space-connection-form" data-tenant="${e(data.tenantId)}">${field(ctx,'spaces.connectionName','<input name="name" required maxlength="80" autocomplete="off">')}<div class="ws-form-grid">${field(ctx,'spaces.provider',`<select name="provider">${['feishu','wecom','mcp','skill','api'].map(p=>`<option value="${p}">${e(p==='feishu'?t('eco.feishu'):p==='wecom'?t('eco.wecom'):p.toUpperCase())}</option>`).join('')}</select>`)}${field(ctx,'spaces.authMode',`<select name="authMode">${['oauth','static','none','exchange','envfile'].map(a=>`<option value="${a}">${text(ctx,'spaces.auth.'+a)}</option>`).join('')}</select>`)}</div>${field(ctx,'spaces.connectionOwnership',`<select name="ownerScope"><option value="member">${text(ctx,'spaces.memberConnection')}</option>${canManageSpace(data)?`<option value="space">${text(ctx,'spaces.sharedConnection')}</option>`:''}</select>`)}<fieldset class="wx-team-fieldset"><legend>${text(ctx,'spaces.boundAgents')}</legend>${data.agents.map(a=>`<label class="wx-team-choice"><input type="checkbox" name="agents" value="${e(a.id)}">${ctx.avatar(a.avatar,22)}${e(a.name)}</label>`).join('')}</fieldset></form>`,footer(ctx,'space-save-connection'),'ws-dialog');
  } else if(action==='space-save-connection') {
    const values=formFor(ctx,'#space-connection-form');if(!values)return true;
    const result=saveConnectionMetadata(data,{name:values.get('name'),provider:values.get('provider'),authMode:values.get('authMode'),ownerScope:values.get('ownerScope'),agentIds:values.getAll('agents')});if(result.error){ctx.toast(t(result.error));return true;}finish(ctx,'spaces.connectionRegistered','connection');
  } else if(action==='space-toggle-connection') {
    const connection=data.connections.find(c=>c.id===id);if(!connection)return true;
    if(connection.ownerScope==='space'?!canManageSpace(data):connection.ownerId!=='m1'){ctx.toast(t('spaces.noPermission'));return true;}
    connection.enabled=!connection.enabled;finish(ctx,'spaces.saved','connection');
  }
  return true;
}


export function handleSpacesChange(el) {
  if(!el.matches?.('#space-sharing-form select[name="visibility"]'))return false;
  for(const group of document.querySelectorAll('#space-sharing-form [data-sharing-scope]'))group.hidden=group.dataset.sharingScope!==el.value;
  return true;
}
