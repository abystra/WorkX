import { t, getLocale } from './i18n.js';
import { methodBy, platformBy, capabilityBy } from './ecosystem-model.js';
import { connectionSpec, initialConnectionDraft, validateConnection, sanitizeConnection, demoConnectionParams, connectionSignature } from './connection-model.js';

const say = (ctx,key,params) => (ctx.t || t)(key,params);
const tr = (ctx,key,params) => ctx.escape(say(ctx,key,params));
const bindingFor = ctx => ctx.data.ecosystemBindings?.find(item => item.id === ctx.state.connection?.bindingId);
const button = (ctx,action,key,extra='',primary=false) => `<button type="button" class="btn${primary?' primary':''}" data-action="${action}" ${extra}>${tr(ctx,key)}</button>`;
let nextSession = 0;
const outcomes = ['success','credential_error','permission_error','timeout'];

export function closeConnection(ctx) {
  const session=ctx.state.connection;
  if (!session) return;
  for (const timer of session.timers || []) clearTimeout(timer);
  session.runToken++;
  if (session.draft) { session.draft.params={}; session.draft.confirmed=[]; session.draft.test=null; }
  session.visibleSecrets=[];
  ctx.state.connection=null;
}

export function openConnection(bindingId,ctx) {
  const binding=ctx.data.ecosystemBindings?.find(item=>item.id===bindingId);
  if (!binding || !methodBy(binding.method)) { ctx.toast(say(ctx,'conn.bindingIncomplete')); return; }
  ctx.closeOverlay();
  closeConnection(ctx);
  ctx.state.connection={bindingId,signature:connectionSignature(binding),sessionId:++nextSession,stage:'params',draft:initialConnectionDraft(binding),scenario:'success',visibleSecrets:[],error:'',errors:[],timers:[],runToken:0,running:false,progress:0,lastOutcome:null};
  rerenderConnection(ctx);
}

function resetResult(session,resetAuthorization=false) {
  session.draft.test=null;
  session.lastOutcome=null;
  session.progress=0;
  session.errors=[];
  session.error='';
  if (resetAuthorization) session.draft.confirmed=[];
}
function stopRunning(session) {
  for(const timer of session.timers || [])clearTimeout(timer);
  session.timers=[];
  session.runToken++;
  session.running=false;
}

export function captureConnection(ctx) {
  const session=ctx.state.connection, binding=bindingFor(ctx), form=document.querySelector('#connection-form');
  if (!session || !binding || !form) return false;
  const values=new FormData(form);
  if(session.stage==='params') {
    const comparable=params=>JSON.stringify(Object.entries(params).filter(([,value])=>String(value ?? '')!=='').sort(([left],[right])=>left.localeCompare(right)));
    const previous=comparable(session.draft.params),updated={...session.draft.params};
    const fields=connectionSpec(binding,session.draft.params).fields;
    for(const field of fields)updated[field.id]=String(values.get(field.id) ?? '');
    session.draft.params=Object.fromEntries(connectionSpec(binding,updated).fields.map(field=>[field.id,updated[field.id] ?? '']));
    if(previous!==comparable(session.draft.params)) { stopRunning(session); resetResult(session,true); }
  } else if(session.stage==='authorization') {
    const allowed=connectionSpec(binding,session.draft.params).steps.map(step=>step.id);
    const confirmed=[...new Set(values.getAll('confirmed'))].filter(id=>allowed.includes(id));
    if(JSON.stringify(confirmed)!==JSON.stringify(session.draft.confirmed))resetResult(session);
    session.draft.confirmed=confirmed;
  } else if(session.stage==='test') {
    const scenario=values.get('scenario');
    if(outcomes.includes(scenario))session.scenario=scenario;
  }
  return true;
}

export function handleConnectionChange(el,ctx) {
  if(!ctx.state.connection || !el?.closest?.('#connection-form'))return false;
  captureConnection(ctx);
  if(ctx.state.connection?.stage==='params' && String(el.tagName).toLowerCase()==='select')rerenderConnection(ctx);
  if(ctx.state.connection?.stage==='authorization') {
    const count=document.querySelector('.wx-conn-count'),binding=bindingFor(ctx);
    if(count && binding)count.textContent=ctx.state.connection.draft.confirmed.length+'/'+connectionSpec(binding,ctx.state.connection.draft.params).steps.length;
  }
  return true;
}

function renderField(field,session,ctx) {
  const value=session.draft.params[field.id] ?? '',id='conn-field-'+field.id;
  const issue=session.errors.find(error=>error.field===field.id);
  const hintId=id+'-hint', errorId=id+'-error';
  const attrs=`id="${ctx.escape(id)}" name="${ctx.escape(field.id)}" ${field.required?'required':''} aria-describedby="${ctx.escape(hintId)}${issue?' '+ctx.escape(errorId):''}" ${issue?'aria-invalid="true"':''}`;
  const shown=session.visibleSecrets.includes(field.id);
  const control=field.type==='select'
    ? `<select ${attrs}>${(field.options || []).map(option=>`<option value="${ctx.escape(option.value)}" ${String(value)===String(option.value)?'selected':''}>${tr(ctx,option.label)}</option>`).join('')}</select>`
    : `<div class="wx-conn-input"><input ${attrs} type="${field.sensitive&&!shown?'password':'text'}" value="${ctx.escape(value)}" maxlength="2048" autocomplete="off" spellcheck="false" ${field.sensitive?'data-sensitive="true"':''}>${field.sensitive?`<button type="button" class="wx-conn-reveal" data-action="conn-show-secret" data-field="${ctx.escape(field.id)}" aria-label="${tr(ctx,shown?'conn.hideField':'conn.showField',{field:say(ctx,field.label)})}" aria-pressed="${shown}">${tr(ctx,shown?'conn.hide':'conn.show')}</button>`:''}</div>`;
  return `<div class="form-field wx-conn-field"><label for="${ctx.escape(id)}">${tr(ctx,field.label)}${field.required?'<span class="wx-conn-required" aria-hidden="true">*</span>':`<small>${tr(ctx,'conn.optional')}</small>`}${field.sensitive?`<em>${tr(ctx,'conn.sessionOnly')}</em>`:''}</label>${control}<small id="${ctx.escape(hintId)}">${field.hint?tr(ctx,field.hint):''}</small>${issue?`<p id="${ctx.escape(errorId)}" class="wx-conn-field-error">${tr(ctx,issue.key)}</p>`:''}</div>`;
}
function renderParameters(binding,session,spec,ctx) {
  return `<div class="wx-conn-stage-heading"><div><h3>${tr(ctx,'conn.parametersTitle')}</h3><p>${tr(ctx,'conn.parametersIntro')}</p></div>${button(ctx,'conn-sample','conn.fillSample')}</div><div class="wx-conn-fields">${spec.fields.map(field=>renderField(field,session,ctx)).join('')}</div>${spec.callbackUrl?`<div class="wx-conn-callback"><div><strong>${tr(ctx,'conn.callbackTitle')}</strong><span>${tr(ctx,'conn.callbackHint')}</span></div><code>${ctx.escape(spec.callbackUrl)}</code></div>`:''}<div class="wx-conn-private-note">${ctx.icon('help',15)}<p>${tr(ctx,'conn.secretNote')}</p></div>`;
}
function renderAuthorization(binding,session,spec,ctx) {
  const capabilities=(binding.capabilities || []).map(id=>capabilityBy(id)).filter(Boolean);
  return `<div class="wx-conn-stage-heading"><div><h3>${tr(ctx,'conn.authorizationTitle')}</h3><p>${tr(ctx,'conn.authorizationIntro')}</p></div><span class="wx-conn-count">${session.draft.confirmed.length}/${spec.steps.length}</span></div><div class="wx-conn-capabilities"><span>${tr(ctx,'conn.requestedCapabilities')}</span><div>${capabilities.map(cap=>`<span>${tr(ctx,cap.name)}</span>`).join('')}</div><p>${tr(ctx,'conn.pendingAuthorization')}</p></div><ol class="wx-conn-auth-list">${spec.steps.map((step,index)=>`<li><div class="wx-conn-auth-number">${index+1}</div><div class="wx-conn-auth-content"><strong>${tr(ctx,step.title)}</strong><p>${tr(ctx,step.body)}</p>${step.url?`<a href="${ctx.escape(step.url)}" target="_blank" rel="noopener noreferrer">${tr(ctx,'conn.officialGuide')}${ctx.icon('external',12)}</a>`:''}<label class="wx-conn-auth-confirm"><input type="checkbox" name="confirmed" value="${ctx.escape(step.id)}" ${session.draft.confirmed.includes(step.id)?'checked':''}><span>${tr(ctx,'conn.confirmStep')}</span></label></div></li>`).join('')}</ol>`;
}
function stageState(session,index) {
  if(session.running)return index<session.progress?'passed':index===session.progress?'running':'pending';
  const result=session.draft.test;
  if(!result)return 'pending';
  if(result.outcome==='success')return 'passed';
  const failedAt=result.outcome==='credential_error'?1:result.outcome==='permission_error'?2:3;
  return index<failedAt?'passed':index===failedAt?'failed':'pending';
}
function testStepItems(session,spec,ctx) {
  const stages=spec.testStages || ['parameters','credentials','permissions','channel'];
  return stages.map((stage,index)=>{const state=stageState(session,index);return `<li class="is-${state}"><span class="wx-conn-test-dot">${state==='passed'?ctx.icon('check',12):state==='failed'?'!':index+1}</span><div><strong>${tr(ctx,'conn.testStage.'+stage)}</strong><small>${tr(ctx,'conn.stageState.'+state)}</small></div></li>`;}).join('');
}
function renderTest(binding,session,spec,ctx) {
  const result=session.draft.test;
  const resultKey=result?.outcome || session.lastOutcome;
  return `<div class="wx-conn-stage-heading"><div><h3>${tr(ctx,'conn.testTitle')}</h3><p>${tr(ctx,'conn.testIntro')}</p></div><span class="wx-conn-demo-badge">${tr(ctx,'conn.simulation')}</span></div><div class="wx-conn-test-controls"><label class="form-field"><span>${tr(ctx,'conn.scenario')}</span><select name="scenario" ${session.running?'disabled':''}>${outcomes.map(outcome=>`<option value="${outcome}" ${session.scenario===outcome?'selected':''}>${tr(ctx,'conn.outcome.'+outcome)}</option>`).join('')}</select></label>${session.running?button(ctx,'conn-stop','conn.cancelTest'):button(ctx,result?'conn-retry':'conn-test',result?'conn.retest':'conn.startTest','',true)}</div><ol class="wx-conn-test-steps" aria-live="polite">${testStepItems(session,spec,ctx)}</ol>${resultKey?`<div class="wx-conn-result ${resultKey==='success'?'is-success':'is-error'}" role="status"><strong>${tr(ctx,'conn.result.'+resultKey)}</strong><p>${tr(ctx,'conn.fix.'+resultKey)}</p>${resultKey==='credential_error'?button(ctx,'conn-fix-params','conn.fixParams'):resultKey==='permission_error'?button(ctx,'conn-fix-auth','conn.fixAuthorization'):''}</div>`:''}<p class="wx-conn-test-footnote">${tr(ctx,'conn.noMessageSent')}</p>`;
}
export function rerenderConnection(ctx) {
  const session=ctx.state.connection,binding=bindingFor(ctx);
  if(!session || !binding)return;
  const spec=connectionSpec(binding,session.draft.params),platform=platformBy(binding.platform),method=methodBy(binding.method);
  const stages=['params','authorization','test'];
  const body=`<div class="wx-conn-binding"><span class="wx-conn-platform ${binding.platform==='wecom'?'is-wecom':''}">${ctx.icon(platform?.icon || 'globe',20)}</span><div><strong>${ctx.escape(binding.name)}</strong><p>${tr(ctx,platform?.name || 'eco.platformPending')} · ${tr(ctx,method?.name || 'eco.modeUndecided')}</p></div><div class="wx-conn-top-tools"><span class="wx-conn-demo-badge">${tr(ctx,'conn.localPrototype')}</span><div class="wx-conn-languages" aria-label="${tr(ctx,'conn.language')}">${[['zh-CN','中文'],['en','English']].map(([locale,label])=>`<button type="button" data-action="set-language" data-locale="${locale}" aria-pressed="${getLocale()===locale}" lang="${locale}">${label}</button>`).join('')}</div></div></div><div class="wx-conn-tabs" role="tablist" aria-label="${tr(ctx,'conn.steps')}">${stages.map((stage,index)=>`<button type="button" role="tab" aria-selected="${session.stage===stage}" class="${session.stage===stage?'is-active':''}" data-action="conn-tab" data-stage="${stage}" ${session.running?'disabled':''}><span>${index+1}</span>${tr(ctx,'conn.tab.'+stage)}</button>`).join('')}</div><form id="connection-form" data-stage="${session.stage}" novalidate>${session.stage==='params'?renderParameters(binding,session,spec,ctx):session.stage==='authorization'?renderAuthorization(binding,session,spec,ctx):renderTest(binding,session,spec,ctx)}${session.error?`<p class="wx-conn-error" role="alert">${tr(ctx,session.error)}</p>`:''}<p class="wx-conn-save-hint">${tr(ctx,'conn.saveHint')}</p></form>`;
  const footer=`<div class="wx-conn-footer">${button(ctx,'conn-cancel','conn.cancel')}<div>${session.stage!=='params'?button(ctx,'conn-back','conn.back',session.running?'disabled':''):''}${button(ctx,'conn-save','conn.save',session.running?'disabled':'')}${session.stage!=='test'?button(ctx,'conn-next','conn.next','',true):''}</div></div>`;
  ctx.modal(say(ctx,'conn.title'),body,footer,'wx-connection-modal');
}

function preflight(session,binding,ctx,authorization=true) {
  session.errors=validateConnection(binding,session.draft);
  if(session.errors.length) { session.stage='params';session.error='conn.fixParameterErrors';return false; }
  const spec=connectionSpec(binding,session.draft.params);
  if(authorization && spec.steps.some(step=>!session.draft.confirmed.includes(step.id))) {session.stage='authorization';session.error='conn.finishAuthorization';return false;}
  session.error='';return true;
}
function startTest(ctx) {
  const session=ctx.state.connection,binding=bindingFor(ctx);
  if(!session || !binding || session.running)return;
  if(!preflight(session,binding,ctx)) {rerenderConnection(ctx);return;}
  stopRunning(session);
  resetResult(session);
  session.running=true;session.stage='test';session.progress=0;
  const runToken=session.runToken,signature=connectionSignature(binding),scenario=session.scenario;
  const stages=connectionSpec(binding,session.draft.params).testStages;
  const failAt=scenario==='credential_error'?1:scenario==='permission_error'?2:scenario==='timeout'?3:-1;
  const isCurrent=()=>ctx.state.connection===session && session.runToken===runToken && bindingFor(ctx)===binding && connectionSignature(binding)===signature && !!document.querySelector('#connection-form');
  const tick=()=>{
    if(!isCurrent()){stopRunning(session);return;}
    if(session.progress===failAt || session.progress>=stages.length-1) {
      session.running=false;session.timers=[];
      session.draft.test={status:scenario==='success'?'success':'error',outcome:scenario,at:Date.now(),simulated:true};
      rerenderConnection(ctx);return;
    }
    session.progress++;
    const progressList=document.querySelector('.wx-conn-test-steps');
    if(progressList)progressList.innerHTML=testStepItems(session,connectionSpec(binding,session.draft.params),ctx);
    else rerenderConnection(ctx);
    session.timers=[setTimeout(tick,300)];
  };
  rerenderConnection(ctx);
  session.timers=[setTimeout(tick,300)];
}

export function renderConnectionStatus(binding,ctx) {
  const saved=binding.connection;
  if(!saved || saved.signature!==connectionSignature(binding))return `<span class="wx-conn-summary">${tr(ctx,'conn.notConfigured')}</span>`;
  const outcome=saved.test?.simulated?saved.test.outcome:null;
  const key=outcome==='success'?'conn.savedPassed':outcome?'conn.savedFailed':'conn.savedUntested';
  return `<span class="wx-conn-summary${outcome==='success'?' is-passed':''}">${tr(ctx,key)}</span>`;
}

export function handleConnectionAction(action,el,ctx) {
  if(!action.startsWith('conn-'))return false;
  if(action==='conn-open'){openConnection(el.dataset.id,ctx);return true;}
  const session=ctx.state.connection,binding=bindingFor(ctx);
  if(action==='conn-cancel') {closeConnection(ctx);ctx.closeOverlay();return true;}
  if(!session)return true;
  if(!binding || connectionSignature(binding)!==session.signature) {closeConnection(ctx);ctx.closeOverlay();ctx.toast(say(ctx,'conn.bindingChanged'));return true;}
  if(action==='conn-stop') {stopRunning(session);session.draft.test=null;session.lastOutcome='cancelled';rerenderConnection(ctx);return true;}
  if(session.running)return true;
  captureConnection(ctx);
  session.error='';session.errors=[];
  if(action==='conn-tab') {if(['params','authorization','test'].includes(el.dataset.stage))session.stage=el.dataset.stage;}
  else if(action==='conn-next') {
    if(session.stage==='params') {if(preflight(session,binding,ctx,false))session.stage='authorization';}
    else if(preflight(session,binding,ctx,true))session.stage='test';
  } else if(action==='conn-back')session.stage=session.stage==='test'?'authorization':'params';
  else if(action==='conn-sample') {session.draft.params=demoConnectionParams(binding,session.draft.params);resetResult(session,true);session.visibleSecrets=[];}
  else if(action==='conn-show-secret') {
    const field=connectionSpec(binding,session.draft.params).fields.find(item=>item.id===el.dataset.field);
    if(field?.sensitive)session.visibleSecrets=session.visibleSecrets.includes(field.id)?session.visibleSecrets.filter(id=>id!==field.id):[...session.visibleSecrets,field.id];
  } else if(action==='conn-test' || action==='conn-retry') {startTest(ctx);return true;}
  else if(action==='conn-fix-params')session.stage='params';
  else if(action==='conn-fix-auth')session.stage='authorization';
  else if(action==='conn-save') {
    binding.connection=sanitizeConnection(binding,session.draft,session.draft.test);
    ctx.persist();closeConnection(ctx);ctx.closeOverlay();ctx.render();ctx.toast(say(ctx,'conn.saved'));return true;
  } else return false;
  rerenderConnection(ctx);return true;
}
