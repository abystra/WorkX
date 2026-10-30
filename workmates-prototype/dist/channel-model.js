import { bindingIsReady, methodBy } from './ecosystem-model.js';
import { connectionSignature, initialConnectionDraft, sanitizeConnection } from './connection-model.js';
import { t } from './i18n.js';

const active = new Map();
const uid = prefix => prefix+'-'+Date.now()+'-'+Math.random().toString(36).slice(2,9);
const say=(ctx,key,params)=>(ctx.t||t)(key,params);
export function ensureChannelData(data) { if(!Array.isArray(data.channelRuns))data.channelRuns=[]; }
export function channelBindingReady(binding,data) {
  return !!binding && bindingIsReady(binding,data) && binding.enabled!==false && methodBy(binding.method)?.kind==='dialogue' && binding.connection?.signature===connectionSignature(binding) && binding.connection?.test?.simulated===true && binding.connection.test.outcome==='success';
}
export function channelBindingIdentity(binding) {
  const clean=sanitizeConnection(binding,initialConnectionDraft(binding));
  return JSON.stringify([connectionSignature(binding),clean.parameters,clean.test?.at||null]);
}
export const eligibleBindings=data=>(data.ecosystemBindings||[]).filter(binding=>channelBindingReady(binding,data));
const getTask=(ctx,run)=>ctx.data.tasks.find(task=>task.id===run.taskId);
const currentBinding=(ctx,run)=>ctx.data.ecosystemBindings.find(binding=>binding.id===run.bindingId);
function record(run,key){run.history.push({key,at:Date.now()});}
function update(ctx,run){ctx.persist();ctx.render();}
function stop(run){const pending=active.get(run);if(pending)clearTimeout(pending.timer);active.delete(run);}
function schedule(ctx,run,delay,fn) {
  stop(run);const token={};
  token.timer=setTimeout(()=>{if(active.get(run)!==token||!ctx.data.channelRuns.includes(run))return;active.delete(run);fn();},delay);
  active.set(run,token);
}
function canContinue(ctx,run) {
  const binding=currentBinding(ctx,run);
  return channelBindingReady(binding,ctx.data) && channelBindingIdentity(binding)===run.bindingSignature && !!ctx.data.agents.find(agent=>agent.id===run.agentId) && !!getTask(ctx,run);
}
function blocked(ctx,run,delivery=false) {
  stop(run);run.errorKey='channel.blocked';run.stage=delivery?'delivery_failed':'execution_failed';
  if(delivery)run.deliveryStatus='failed';
  else {run.executionStatus='failed';const task=getTask(ctx,run);if(task)task.status='failed';}
  record(run,'channel.event.blocked');update(ctx,run);
}
function beginDelivery(ctx,run,fail=false) {
  if(!canContinue(ctx,run)){blocked(ctx,run,true);return;}
  run.stage='sending';run.deliveryStatus='sending';run.deliveryAttempts++;run.errorKey='';record(run,'channel.event.sending');update(ctx,run);
  schedule(ctx,run,800,()=>{
    if(!canContinue(ctx,run)){blocked(ctx,run,true);return;}
    run.stage=fail?'delivery_failed':'delivered';run.deliveryStatus=fail?'failed':'delivered';run.errorKey=fail?'channel.deliveryError':'';
    if(!fail)run.reply={text:run.resultText,conversation:run.source.conversation,kind:run.source.kind,platform:run.platform,sender:run.source.sender,at:Date.now(),simulated:true};
    record(run,fail?'channel.event.deliveryFailed':'channel.event.delivered');update(ctx,run);
  });
}
function beginExecution(ctx,run,fail=false,deliveryFail=false) {
  if(!canContinue(ctx,run)){blocked(ctx,run);return;}
  run.stage='running';run.executionStatus='running';run.errorKey='';run.executionAttempts++;const task=getTask(ctx,run);task.status='running';record(run,'channel.event.running');update(ctx,run);
  schedule(ctx,run,1400,()=>{
    if(!canContinue(ctx,run)){blocked(ctx,run);return;}
    if(fail){run.stage='execution_failed';run.executionStatus='failed';run.errorKey='channel.executionError';task.status='failed';record(run,'channel.event.executionFailed');update(ctx,run);return;}
    run.executionStatus='done';run.stage='result';task.status='done';task.reviewState='review';task.unread=ctx.state.page!=='task'||ctx.state.task!==task.id;
    run.resultText=say(ctx,'channel.generatedResult',{agent:run.agentName,message:run.source.message});
    if(!run.fileId){run.fileId=uid('channel-file');ctx.data.library.unshift({id:run.fileId,name:task.name+' · '+say(ctx,'channel.deliverable'),type:'doc',updated:'Just now',content:run.resultText});}
    task.file=run.fileId;record(run,'channel.event.result');update(ctx,run);
    schedule(ctx,run,500,()=>beginDelivery(ctx,run,deliveryFail));
  });
}
export function receiveChannelMessage(ctx,input) {
  ensureChannelData(ctx.data);
  const binding=ctx.data.ecosystemBindings.find(item=>item.id===input.bindingId);
  if(!channelBindingReady(binding,ctx.data))return {error:'channel.bindingUnavailable'};
  if(!['direct','group'].includes(input.kind))return {error:'channel.invalidKind'};
  const source={sender:String(input.sender||'').trim(),conversation:String(input.conversation||'').trim(),message:String(input.message||'').trim(),kind:input.kind==='group'?'group':'direct',mentioned:input.mentioned===true};
  if(!source.sender||source.sender.length>60||!source.conversation||source.conversation.length>100||!source.message||source.message.length>2000)return {error:'channel.requiredMessage'};
  if(source.kind==='group'&&(binding.method==='wecom-app'||!source.mentioned))return {error:binding.method==='wecom-app'?'channel.directOnly':'channel.mentionRequired'};
  if(input.projectId&&!ctx.data.projects.some(project=>project.id===input.projectId))return {error:'channel.invalidProject'};
  const eventId=String(input.eventId||uid('event'));
  const existing=ctx.data.channelRuns.find(run=>run.bindingId===binding.id&&run.eventId===eventId);
  if(existing){existing.replayCount=(existing.replayCount||0)+1;record(existing,'channel.event.duplicate');update(ctx,existing);return {run:existing,duplicate:true};}
  const agent=ctx.data.agents.find(item=>item.id===binding.assignedAgent),id=uid('channel'),taskId=uid('channel-task');
  const run={id,eventId,bindingId:binding.id,bindingName:binding.name,bindingSignature:channelBindingIdentity(binding),platform:binding.platform,method:binding.method,agentId:agent.id,agentName:agent.name,source,taskId,projectId:input.projectId||'',scenario:['execution_error','delivery_error'].includes(input.scenario)?input.scenario:'success',stage:'received',executionStatus:'queued',deliveryStatus:'pending',executionAttempts:0,deliveryAttempts:0,history:[],createdAt:Date.now(),resultText:'',errorKey:'',fileId:null};
  const task={id:taskId,name:source.message.length>40?source.message.slice(0,40)+'…':source.message,prompt:source.message,date:new Date().toLocaleString('en-US',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}),agent:agent.id,status:'running',project:run.projectId,kind:'channel',channelRunId:id,unread:true};
  ctx.data.channelRuns.unshift(run);ctx.data.tasks.unshift(task);agent.tasks=(Number(agent.tasks)||0)+1;
  const project=ctx.data.projects.find(item=>item.id===run.projectId);if(project){project.tasks=(Number(project.tasks)||0)+1;if(!Array.isArray(project.agentIds))project.agentIds=[];if(!project.agentIds.includes(agent.id))project.agentIds.push(agent.id);}
  record(run,'channel.event.received');update(ctx,run);
  schedule(ctx,run,500,()=>beginExecution(ctx,run,run.scenario==='execution_error',run.scenario==='delivery_error'));
  return {run,duplicate:false};
}
export function retryChannelExecution(ctx,id) {
  const run=ctx.data.channelRuns.find(item=>item.id===id);
  if(!run||!['failed','cancelled','interrupted'].includes(run.executionStatus))return false;
  if(!canContinue(ctx,run)){blocked(ctx,run);return false;}
  record(run,'channel.event.executionRetry');run.deliveryStatus='pending';beginExecution(ctx,run);return true;
}
export function retryChannelDelivery(ctx,id) {
  const run=ctx.data.channelRuns.find(item=>item.id===id);
  if(!run||run.executionStatus!=='done'||!['failed','cancelled','interrupted'].includes(run.deliveryStatus)||!run.fileId)return false;
  if(!canContinue(ctx,run)){blocked(ctx,run,true);return false;}
  record(run,'channel.event.deliveryRetry');beginDelivery(ctx,run);return true;
}
export function cancelChannelRun(ctx,id) {
  const run=ctx.data.channelRuns.find(item=>item.id===id);
  if(!run||!['received','running','result','sending'].includes(run.stage))return false;
  stop(run);run.stage='cancelled';run.errorKey='channel.cancelledHint';
  if(run.executionStatus!=='done'){run.executionStatus='cancelled';const task=getTask(ctx,run);if(task)task.status='failed';}
  run.deliveryStatus='cancelled';record(run,'channel.event.cancelled');update(ctx,run);return true;
}
export function recoverChannelRuns(data) {
  ensureChannelData(data);let changed=false;
  for(const run of data.channelRuns) {
    if(!['received','running','result','sending'].includes(run.stage))continue;
    stop(run);run.stage='interrupted';run.errorKey='channel.interruptedHint';run.history=Array.isArray(run.history)?run.history:[];
    if(run.executionStatus!=='done'){run.executionStatus='interrupted';const task=data.tasks.find(item=>item.id===run.taskId);if(task)task.status='failed';}
    else run.deliveryStatus='interrupted';
    record(run,'channel.event.interrupted');changed=true;
  }
  for(const task of data.tasks){if(task.kind==='channel'&&task.status==='running'&&!data.channelRuns.some(run=>run.taskId===task.id)){task.status='failed';changed=true;}}
  return changed;
}
