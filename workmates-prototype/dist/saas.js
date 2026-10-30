import { t } from './i18n.js';

const list = value => Array.isArray(value) ? value : [];
const uid = prefix => prefix + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
export function ensureSaasData(data) {
  if (!data.enterprise) data.enterprise = { id: 'wx-demo', name: 'WorkX' };
  if (!Array.isArray(data.departments)) data.departments = [];
  for (const member of list(data.teamMembers)) {
    if (!Object.hasOwn(member, 'departmentId')) member.departmentId = '';
    if (!['active', 'disabled'].includes(member.status)) member.status = 'active';
    if (member.role === 'owner') member.status = 'active';
  }
}
const tr = (ctx, key) => ctx.escape(t(key));
const button = (ctx, action, key, extra = '', primary = false) => `<button type="button" class="btn ${primary ? 'primary' : ''}" data-action="${action}" ${extra}>${tr(ctx,key)}</button>`;
const options = (ctx, selected = '', exclude = '') => `<option value="">${tr(ctx,'saas.root')}</option>` + list(ctx.data.departments).filter(d => d.id !== exclude && !isDescendant(ctx.data, d.id, exclude)).map(d => `<option value="${ctx.escape(d.id)}" ${selected === d.id ? 'selected' : ''}>${ctx.escape(d.name)}</option>`).join('');
export function isDescendant(data, candidate, ancestor) {
  if (!ancestor) return false;
  const seen = new Set();
  let current = list(data.departments).find(d => d.id === candidate);
  while (current && !seen.has(current.id)) {
    if (current.id === ancestor) return true;
    seen.add(current.id);
    current = data.departments.find(d => d.id === current.parentId);
  }
  return false;
}
export function renderEnterprise(ctx) {
  const e = ctx.escape;
  return `<section class="wx-saas-summary"><div><span class="wx-team-eyebrow">${tr(ctx,'saas.tenant')}</span><h2>${e(ctx.data.enterprise.name)}</h2><p>${tr(ctx,'saas.summary')}</p><small>${tr(ctx,'saas.tenantId')} · ${e(ctx.data.enterprise.id)}</small></div>${button(ctx,'saas-tenant','saas.editTenant')}</section>`;
}
export function renderOrganization(ctx) {
  const e = ctx.escape, visited = new Set();
  function branch(parentId, depth = 0) {
    return ctx.data.departments.filter(d => (d.parentId || '') === parentId && !visited.has(d.id)).map(d => {
      visited.add(d.id);
      const count = ctx.data.teamMembers.filter(m => m.departmentId === d.id).length;
      return `<div class="wx-saas-department" style="--depth:${Math.min(depth,6)}"><div><strong>${e(d.name)}</strong><small>${e(t('team.memberCount',{count}))}</small></div><div>${button(ctx,'saas-department','team.edit',`data-id="${e(d.id)}"`)}${button(ctx,'saas-delete-department','saas.delete',`data-id="${e(d.id)}"`)}</div></div>${branch(d.id, depth + 1)}`;
    }).join('');
  }
  return `<section class="wx-team-panel"><div class="wx-team-panel-heading"><h2>${tr(ctx,'saas.organization')}</h2>${button(ctx,'saas-department','saas.addDepartment')}</div><p class="wx-team-caption">${tr(ctx,'saas.orgNote')}</p><div class="wx-saas-root">${ctx.icon('users',18)}<strong>${e(ctx.data.enterprise.name)}</strong></div>${branch('') || `<p class="wx-team-caption">${tr(ctx,'saas.addDepartment')}</p>`}<p class="wx-team-caption">${tr(ctx,'saas.unassigned')} · ${e(ctx.data.teamMembers.filter(m => !m.departmentId).length)}</p></section>`;
}
export function renderRoles(ctx) {
  const rows = [['enterpriseManage','allow','allow','deny'],['roleManage','allow','allow','deny'],['transfer','allow','deny','deny'],['agentManage','allow','allow','deny'],['ecosystemManage','allow','allow','deny'],['taskUse','scoped','scoped','scoped'],['audit','allow','allow','deny']];
  return `<section class="wx-team-panel"><div class="wx-team-panel-heading"><h2>${tr(ctx,'saas.roles')}</h2></div><p class="wx-team-caption">${tr(ctx,'saas.roleNote')}</p><div class="wx-saas-table-scroll"><table class="wx-saas-table"><thead><tr><th scope="col">${tr(ctx,'saas.permission')}</th>${['owner','admin','member'].map(r=>`<th scope="col">${tr(ctx,'team.role.'+r)}</th>`).join('')}</tr></thead><tbody>${rows.map(([key,...values])=>`<tr><th scope="row">${tr(ctx,'saas.'+key)}</th>${values.map(v=>`<td class="is-${v}">${tr(ctx,'saas.'+v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="wx-team-caption">${tr(ctx,'saas.resourceNote')}</p></section>`;
}
export function memberMeta(member, ctx) {
  const department = ctx.data.departments.find(d=>d.id===member.departmentId);
  return `<small class="wx-saas-member-meta">${ctx.escape(department?.name || t('saas.unassigned'))} · ${tr(ctx,member.status==='disabled'?'saas.disabled':'saas.active')}</small>`;
}
function save(ctx) {
  ctx.data.teamActivity.unshift({id:uid('ev'),type:'enterpriseChanged',at:new Date().toISOString()});
  ctx.data.teamActivity = ctx.data.teamActivity.slice(0,80);
  ctx.persist();ctx.closeOverlay();ctx.render();ctx.toast(t('saas.saved'));
}
export function handleSaasAction(action, el, ctx) {
  if (!action.startsWith('saas-')) return false;
  const e=ctx.escape, data=ctx.data, entityId=el.dataset.id;
  const footer=(saveAction,extra='')=>button(ctx,'close','team.cancel')+button(ctx,saveAction,'team.save',extra,true);
  if(action==='saas-tenant') ctx.modal(t('saas.editTenant'),`<form id="saas-tenant-form"><label class="form-field"><span>${tr(ctx,'saas.tenantName')}</span><input name="name" maxlength="80" required value="${e(data.enterprise.name)}"></label><p class="prototype-note">${tr(ctx,'saas.boundary')}</p></form>`,footer('saas-save-tenant'));
  else if(action==='saas-save-tenant') {
    const form=document.querySelector('#saas-tenant-form');if(!form?.reportValidity())return true;
    const name=String(new FormData(form).get('name')||'').trim();if(!name||name.length>80){ctx.toast(t('saas.invalid'));return true;}
    data.enterprise.name=name;save(ctx);
  } else if(action==='saas-department') {
    const department=data.departments.find(d=>d.id===entityId);if(entityId&&!department)return true;
    ctx.modal(t(department?'saas.editDepartment':'saas.addDepartment'),`<form id="saas-department-form"><label class="form-field"><span>${tr(ctx,'saas.departmentName')}</span><input name="name" maxlength="60" required value="${e(department?.name||'')}"></label><label class="form-field"><span>${tr(ctx,'saas.parent')}</span><select name="parentId">${options(ctx,department?.parentId,department?.id)}</select></label></form>`,footer('saas-save-department',`data-id="${e(entityId||'')}"`));
  } else if(action==='saas-save-department') {
    const form=document.querySelector('#saas-department-form');if(!form?.reportValidity())return true;
    const fields=new FormData(form),name=String(fields.get('name')||'').trim(),parentId=String(fields.get('parentId')||'');
    const department=data.departments.find(d=>d.id===entityId);
    if(!name||name.length>60||(entityId&&!department)||(parentId&&!data.departments.some(d=>d.id===parentId))||isDescendant(data,parentId,entityId)){ctx.toast(t('saas.invalid'));return true;}
    if(data.departments.some(d=>d.id!==entityId&&d.parentId===parentId&&d.name.toLowerCase()===name.toLowerCase())){ctx.toast(t('saas.duplicate'));return true;}
    if(department)Object.assign(department,{name,parentId});else data.departments.push({id:uid('dep'),name,parentId});save(ctx);
  } else if(action==='saas-delete-department') {
    if(!data.departments.some(d=>d.id===entityId))return true;
    if(data.departments.some(d=>d.parentId===entityId)||data.teamMembers.some(m=>m.departmentId===entityId)){ctx.toast(t('saas.deleteBlocked'));return true;}
    data.departments=data.departments.filter(d=>d.id!==entityId);save(ctx);
  } else if(action==='saas-member') {
    const member=data.teamMembers.find(m=>m.id===entityId);if(!member)return true;
    ctx.modal(t('saas.manageMember'),`<form id="saas-member-form"><label class="form-field"><span>${tr(ctx,'team.name')}</span><input name="name" maxlength="40" required value="${e(member.name)}"></label><label class="form-field"><span>${tr(ctx,'saas.department')}</span><select name="departmentId">${options(ctx,member.departmentId).replace(tr(ctx,'saas.root'),tr(ctx,'saas.unassigned'))}</select></label><label class="form-field"><span>${tr(ctx,'team.role')}</span><select name="role" ${member.role==='owner'?'disabled':''}>${(member.role==='owner'?['owner']:['member','admin']).map(r=>`<option value="${r}" ${r===member.role?'selected':''}>${tr(ctx,'team.role.'+r)}</option>`).join('')}</select></label><label class="form-field"><span>${tr(ctx,'saas.status')}</span><select name="status" ${member.role==='owner'?'disabled':''}>${['active','disabled'].map(s=>`<option value="${s}" ${member.status===s?'selected':''}>${tr(ctx,'saas.'+s)}</option>`).join('')}</select></label><p class="prototype-note">${tr(ctx,member.role==='owner'?'saas.ownerProtected':'saas.memberNote')}</p></form>`,footer('saas-save-member',`data-id="${e(entityId)}"`));
  } else if(action==='saas-save-member') {
    const member=data.teamMembers.find(m=>m.id===entityId),form=document.querySelector('#saas-member-form');if(!member||!form?.reportValidity())return true;
    const fields=new FormData(form),name=String(fields.get('name')||'').trim(),departmentId=String(fields.get('departmentId')||''),role=fields.get('role'),status=fields.get('status');
    if(!name||name.length>40||(departmentId&&!data.departments.some(d=>d.id===departmentId))||(member.role!=='owner'&&(!['admin','member'].includes(role)||!['active','disabled'].includes(status)))){ctx.toast(t('saas.invalid'));return true;}
    Object.assign(member,{name,departmentId,...(member.role==='owner'?{status:'active'}:{role,status})});save(ctx);
  }
  return true;
}
