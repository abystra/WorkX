import { t, getLocale } from './i18n.js';
import { platformBy } from './ecosystem-model.js';
import { ensureChannelData, recoverChannelRuns, channelBindingReady, eligibleBindings, receiveChannelMessage, retryChannelExecution, retryChannelDelivery, cancelChannelRun } from './channel-model.js';
export { ensureChannelData, recoverChannelRuns, channelBindingReady } from './channel-model.js';
const say=(ctx,key,params)=>(ctx.t||t)(key,params);
const tr=(ctx,key,params)=>ctx.escape(say(ctx,key,params));
const button=(ctx,action,key,extra='',primary=false)=>`<button type="button" class="btn${primary?' primary':''}" data-action="${action}" ${extra}>${tr(ctx,key)}</button>`;
const active=run=>['received','running','result','sending'].includes(run.stage);
const attention=run=>['execution_failed','delivery_failed','cancelled','interrupted'].includes(run.stage);
const clock=value=>Number.isFinite(value)?new Date(value).toLocaleTimeString(getLocale(),{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'';
const platform=(run,ctx)=>tr(ctx,platformBy(run.platform)?.name||'eco.platformPending');
const status=(run,ctx)=>`<span class="wx-channel-status is-${ctx.escape(run.stage)}">${tr(ctx,'channel.stage.'+run.stage)}</span>`;
const counters=(ctx)=>{const runs=ctx.data.channelRuns;return [['active',runs.filter(active).length],['attention',runs.filter(attention).length],['delivered',runs.filter(run=>run.stage==='delivered').length]];};
export function renderChannelHome(ctx) {
  ensureChannelData(ctx.data);
  return `<section class="wx-channel-home"><div>${ctx.icon('chat',20)}<div><strong>${tr(ctx,'channel.title')}</strong><p>${tr(ctx,'channel.homeHint')}</p></div></div><div class="wx-channel-home-counts">${counters(ctx).map(([key,count])=>`<span><strong>${count}</strong>${tr(ctx,'channel.count.'+key)}</span>`).join('')}</div>${button(ctx,'nav','channel.openWorkbench','data-page="inbox"')}</section>`;
}
function runActions(run,ctx) {
  const id=ctx.escape(run.id);
  return `${active(run)?button(ctx,'channel-cancel-run','channel.cancelRun',`data-id="${id}"`):''}${['failed','cancelled','interrupted'].includes(run.executionStatus)?button(ctx,'channel-retry-execution','channel.retryExecution',`data-id="${id}"`,true):''}${run.executionStatus==='done'&&['failed','cancelled','interrupted'].includes(run.deliveryStatus)?button(ctx,'channel-retry-delivery','channel.retryDelivery',`data-id="${id}"`,true):''}`;
}
export function renderInbox(ctx) {
  ensureChannelData(ctx.data);
  const filter=ctx.state.channelFilter||'all',runs=ctx.data.channelRuns.filter(run=>filter==='all'||filter==='active'&&active(run)||filter==='attention'&&attention(run)||filter==='delivered'&&run.stage==='delivered');
  const ready=eligibleBindings(ctx.data).length;
  return `<section class="wx-channel-page"><header class="wx-channel-heading"><div><h1>${tr(ctx,'channel.title')}</h1><p>${tr(ctx,'channel.subtitle')}</p></div>${button(ctx,'channel-compose','channel.simulate','',true)}</header><div class="wx-channel-notice">${ctx.icon('help',17)}<p>${tr(ctx,'channel.notice')}</p></div><div class="wx-channel-stats">${counters(ctx).map(([key,count])=>`<div><span>${tr(ctx,'channel.count.'+key)}</span><strong>${count}</strong></div>`).join('')}<div><span>${tr(ctx,'channel.readyBindings')}</span><strong>${ready}</strong></div></div><div class="wx-channel-toolbar"><div class="tabs" role="tablist" aria-label="${tr(ctx,'channel.filterLabel')}">${['all','active','attention','delivered'].map(key=>`<button type="button" role="tab" aria-selected="${filter===key}" class="tab-btn ${filter===key?'active':''}" data-action="channel-filter" data-filter="${key}">${tr(ctx,'channel.filter.'+key)}</button>`).join('')}</div><a href="#ecosystem" data-action="nav" data-page="ecosystem">${tr(ctx,'channel.manageBindings')}${ctx.icon('arrow',13)}</a></div>${runs.length?`<div class="wx-channel-list">${runs.map(run=>`<article class="wx-channel-row"><div class="wx-channel-row-top"><span class="wx-channel-platform is-${ctx.escape(run.platform)}">${ctx.icon(platformBy(run.platform)?.icon||'chat',20)}</span><div><button type="button" class="wx-channel-task-link" data-action="channel-open-task" data-id="${ctx.escape(run.id)}">${ctx.escape(run.source.message)}</button><p>${platform(run,ctx)} · ${ctx.escape(run.source.conversation)} · ${ctx.escape(run.source.sender)}</p></div>${status(run,ctx)}</div><div class="wx-channel-row-bottom"><span>${tr(ctx,'channel.assigned',{name:run.agentName})}</span><span>${tr(ctx,'channel.executionLabel')} ${tr(ctx,'channel.execution.'+run.executionStatus)}</span><span>${tr(ctx,'channel.deliveryLabel')} ${tr(ctx,'channel.delivery.'+run.deliveryStatus)}</span><div>${runActions(run,ctx)}${button(ctx,'channel-open-task','channel.viewTask',`data-id="${ctx.escape(run.id)}"`)}</div></div></article>`).join('')}</div>`:`<div class="wx-channel-empty">${ctx.icon('chat',30)}<h2>${tr(ctx,ctx.data.channelRuns.length?'channel.noMatches':'channel.emptyTitle')}</h2><p>${tr(ctx,ready?'channel.emptyReady':'channel.emptySetup')}</p>${ready?button(ctx,'channel-compose','channel.simulate','',true):button(ctx,'nav','channel.manageBindings','data-page="ecosystem"')}</div>`}</section>`;
}
export function renderChannelTaskBadge(task,ctx) {
  if(task.kind!=='channel')return '';
  const run=ctx.data.channelRuns?.find(item=>item.id===task.channelRunId);
  return run?`<span class="wx-channel-task-badge">${platform(run,ctx)} · ${tr(ctx,'channel.stage.'+run.stage)}</span>`:'';
}
export function renderChannelTask(task,ctx) {
  const run=ctx.data.channelRuns?.find(item=>item.id===task.channelRunId);
  if(!run)return `<div class="wx-channel-detail"><p>${tr(ctx,'channel.missingRun')}</p>${button(ctx,'nav','channel.openWorkbench','data-page="inbox"')}</div>`;
  const phase=run.stage==='received'?0:run.executionStatus!=='done'?1:run.stage==='result'?2:3;
  const source=run.source;
  return `<section class="wx-channel-detail"><div class="wx-channel-detail-top"><span class="wx-channel-local">${tr(ctx,'channel.demo')}</span>${status(run,ctx)}<button type="button" class="text-btn" data-action="nav" data-page="inbox">${tr(ctx,'channel.openWorkbench')}${ctx.icon('arrow',13)}</button></div><h2>${tr(ctx,'channel.detailTitle')}</h2><p class="wx-channel-detail-intro">${tr(ctx,'channel.detailHint')}</p><ol class="wx-channel-pipeline">${['received','running','result','delivered'].map((key,index)=>`<li class="${index<phase||run.stage==='delivered'?'is-done':index===phase?'is-current':''}"><span>${index+1}</span><strong>${tr(ctx,'channel.phase.'+key)}</strong></li>`).join('')}</ol><div class="wx-channel-source"><div><span>${tr(ctx,'channel.source')}</span><strong>${platform(run,ctx)} · ${ctx.escape(run.bindingName)}</strong></div><div><span>${tr(ctx,'channel.conversation')}</span><strong>${ctx.escape(source.conversation)} · ${tr(ctx,'channel.kind.'+source.kind)}</strong></div><div><span>${tr(ctx,'channel.sender')}</span><strong>${ctx.escape(source.sender)}</strong></div><div><span>${tr(ctx,'channel.partner')}</span><strong>${ctx.escape(run.agentName)}</strong></div></div><div class="wx-channel-message"><span>${tr(ctx,'channel.incoming')}</span><p>${ctx.escape(source.message)}</p></div><div class="wx-channel-run-summary"><span>${tr(ctx,'channel.executionLabel')}<strong>${tr(ctx,'channel.execution.'+run.executionStatus)}</strong></span><span>${tr(ctx,'channel.deliveryLabel')}<strong>${tr(ctx,'channel.delivery.'+run.deliveryStatus)}</strong></span><span>${tr(ctx,'channel.attempts',{execution:run.executionAttempts,delivery:run.deliveryAttempts})}</span></div>${run.errorKey?`<div class="wx-channel-error" role="status">${tr(ctx,run.errorKey)}</div>`:''}<div class="wx-channel-detail-actions">${runActions(run,ctx)}${run.errorKey==='channel.blocked'?button(ctx,'nav','channel.checkBinding','data-page="ecosystem"')+(channelBindingReady(ctx.data.ecosystemBindings.find(item=>item.id===run.bindingId),ctx.data)?button(ctx,'channel-compose','channel.newMessage',`data-binding="${ctx.escape(run.bindingId)}"`):''):''}${button(ctx,'channel-replay','channel.replay',`data-id="${ctx.escape(run.id)}"`)}</div>${run.resultText?`<section class="wx-channel-result"><div><h3>${tr(ctx,'channel.resultTitle')}</h3>${button(ctx,'open-file','channel.openResult',`data-id="${ctx.escape(run.fileId)}"`)}</div><p>${ctx.escape(run.resultText)}</p></section>`:''}<section class="wx-channel-return"><div><h3>${tr(ctx,'channel.returnTitle')}</h3><span>${platform(run,ctx)} · ${ctx.escape(source.conversation)}</span></div>${run.reply?`<div class="wx-channel-reply"><span>${tr(ctx,'channel.replyFrom',{name:run.agentName})}</span><p>${ctx.escape(run.reply.text)}</p><small>${tr(ctx,'channel.replyDelivered',{time:clock(run.reply.at)})}</small></div>`:`<p class="wx-channel-return-pending">${tr(ctx,run.executionStatus!=='done'?'channel.awaitResult':'channel.awaitDelivery')}</p>`}<p class="wx-channel-return-note">${tr(ctx,'channel.returnHint')}</p></section><details class="wx-channel-history" open><summary>${tr(ctx,'channel.history')}<small>${tr(ctx,'channel.replayCount',{count:run.replayCount||0})}</small></summary><ol>${run.history.map(item=>`<li><time>${ctx.escape(clock(item.at))}</time><span>${tr(ctx,item.key)}</span></li>`).join('')}</ol><code>${tr(ctx,'channel.eventId')} ${ctx.escape(run.eventId)}</code></details></section>`;
}
export function closeChannelDraft(ctx){ctx.state.channelDraft=null;}
export function captureChannelDraft(ctx) {
  const draft=ctx.state.channelDraft,form=document.querySelector('#channel-message-form');if(!draft||!form)return false;
  const values=new FormData(form);
  for(const field of ['bindingId','sender','conversation','message','kind','projectId','scenario'])draft[field]=String(values.get(field)||'');
  draft.mentioned=values.get('mentioned')!==null;
  return true;
}
export function handleChannelChange(el,ctx) {
  if(!ctx.state.channelDraft||!el?.closest?.('#channel-message-form'))return false;
  captureChannelDraft(ctx);
  if(el.name==='bindingId'||el.name==='kind') {
    const binding=ctx.data.ecosystemBindings.find(item=>item.id===ctx.state.channelDraft.bindingId);
    if(binding?.method==='wecom-app')ctx.state.channelDraft.kind='direct';
    rerenderChannelDraft(ctx);
  }
  return true;
}
export function rerenderChannelDraft(ctx) {
  const draft=ctx.state.channelDraft;if(!draft)return;
  const bindings=eligibleBindings(ctx.data),binding=bindings.find(item=>item.id===draft.bindingId),groupAllowed=binding?.method!=='wecom-app';
  const field=(id,max)=>`<label class="form-field"><span>${tr(ctx,'channel.'+id)}</span><input name="${id}" maxlength="${max}" value="${ctx.escape(draft[id])}" required autocomplete="off"></label>`;
  const body=`<div class="wx-channel-modal-intro"><p>${tr(ctx,'channel.composeHint')}</p><div class="wx-channel-languages">${[['zh-CN','中文'],['en','English']].map(([locale,label])=>`<button type="button" data-action="set-language" data-locale="${locale}" aria-pressed="${getLocale()===locale}">${label}</button>`).join('')}</div></div>${!bindings.length?`<div class="wx-channel-error">${tr(ctx,'channel.emptySetup')}</div>`:''}<form id="channel-message-form" novalidate><label class="form-field"><span>${tr(ctx,'channel.binding')}</span><select name="bindingId" required><option value="">${tr(ctx,'channel.chooseBinding')}</option>${bindings.map(item=>`<option value="${ctx.escape(item.id)}" ${draft.bindingId===item.id?'selected':''}>${tr(ctx,platformBy(item.platform).name)} · ${ctx.escape(item.name)} · ${ctx.escape(ctx.data.agents.find(agent=>agent.id===item.assignedAgent)?.name||'')}</option>`).join('')}</select></label><div class="wx-channel-form-grid"><label class="form-field"><span>${tr(ctx,'channel.kind')}</span><select name="kind"><option value="direct" ${draft.kind==='direct'?'selected':''}>${tr(ctx,'channel.kind.direct')}</option>${groupAllowed?`<option value="group" ${draft.kind==='group'?'selected':''}>${tr(ctx,'channel.kind.group')}</option>`:''}</select></label>${field('sender',60)}</div>${field('conversation',100)}${draft.kind==='group'?`<label class="wx-channel-mention"><input type="checkbox" name="mentioned" ${draft.mentioned?'checked':''}>${tr(ctx,'channel.mentioned')}</label>`:''}<p class="wx-channel-form-note">${tr(ctx,groupAllowed?'channel.triggerRule':'channel.directOnly')}</p><label class="form-field"><span>${tr(ctx,'channel.message')}</span><textarea name="message" required maxlength="2000" rows="4" placeholder="${tr(ctx,'channel.messagePlaceholder')}">${ctx.escape(draft.message)}</textarea></label><div class="wx-channel-form-grid"><label class="form-field"><span>${tr(ctx,'channel.project')}</span><select name="projectId"><option value="">${tr(ctx,'channel.noProject')}</option>${ctx.data.projects.map(project=>`<option value="${ctx.escape(project.id)}" ${draft.projectId===project.id?'selected':''}>${ctx.escape(project.name)}</option>`).join('')}</select></label><label class="form-field"><span>${tr(ctx,'channel.scenario')}</span><select name="scenario">${['success','execution_error','delivery_error'].map(scenario=>`<option value="${scenario}" ${draft.scenario===scenario?'selected':''}>${tr(ctx,'channel.scenario.'+scenario)}</option>`).join('')}</select></label></div>${draft.error?`<p class="wx-channel-error" role="alert">${tr(ctx,draft.error)}</p>`:''}<p class="wx-channel-form-note">${tr(ctx,'channel.submitHint')}</p></form>`;
  ctx.modal(say(ctx,'channel.simulate'),body,`<div class="wx-channel-modal-footer">${button(ctx,'channel-cancel-compose','channel.cancel')}<div>${button(ctx,'channel-fill-sample','channel.fillSample')}${button(ctx,'channel-submit','channel.receive',bindings.length?'':'disabled',true)}</div></div>`,'wx-channel-modal');
}
export function handleChannelAction(action,el,ctx) {
  if(!action.startsWith('channel-'))return false;
  ensureChannelData(ctx.data);
  const id=el.dataset.id,run=ctx.data.channelRuns.find(item=>item.id===id);
  if(action==='channel-compose') {
    ctx.closeOverlay();const bindings=eligibleBindings(ctx.data);const binding=el.dataset.binding?bindings.find(item=>item.id===el.dataset.binding):bindings[0];
    ctx.state.channelDraft={bindingId:binding?.id||'',sender:'',conversation:'',message:'',kind:'direct',mentioned:true,projectId:'',scenario:'success',error:el.dataset.binding&&!binding?'channel.bindingUnavailable':''};rerenderChannelDraft(ctx);
  } else if(action==='channel-cancel-compose'){closeChannelDraft(ctx);ctx.closeOverlay();}
  else if(action==='channel-submit'||action==='channel-fill-sample') {
    if(!ctx.state.channelDraft)return true;captureChannelDraft(ctx);const draft=ctx.state.channelDraft;draft.error='';
    if(action==='channel-fill-sample'){draft.sender=say(ctx,'channel.sampleSender');draft.conversation=say(ctx,'channel.sampleConversation');draft.message=say(ctx,'channel.sampleMessage');draft.mentioned=true;rerenderChannelDraft(ctx);}
    else {const result=receiveChannelMessage(ctx,draft);if(result.error){draft.error=result.error;rerenderChannelDraft(ctx);}else{closeChannelDraft(ctx);ctx.closeOverlay();ctx.navigate('task',result.run.taskId);ctx.toast(say(ctx,'channel.accepted'));}}
  } else if(action==='channel-filter'){if(['all','active','attention','delivered'].includes(el.dataset.filter)){ctx.state.channelFilter=el.dataset.filter;ctx.render();}}
  else if(action==='channel-open-task'){if(run)ctx.navigate('task',run.taskId);}
  else if(action==='channel-retry-execution')retryChannelExecution(ctx,id);
  else if(action==='channel-retry-delivery')retryChannelDelivery(ctx,id);
  else if(action==='channel-cancel-run')cancelChannelRun(ctx,id);
  else if(action==='channel-replay'&&run) {const result=receiveChannelMessage(ctx,{...run.source,bindingId:run.bindingId,eventId:run.eventId,projectId:run.projectId,scenario:run.scenario});ctx.toast(say(ctx,result.error||'channel.duplicate'));}
  else return false;
  return true;
}
