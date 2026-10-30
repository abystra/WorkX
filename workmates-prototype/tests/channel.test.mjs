import test from 'node:test';
import assert from 'node:assert/strict';
import { initialData } from '../dist/data.js';
import { icon, avatar } from '../dist/icons.js';
import * as i18n from '../dist/i18n.js';
import * as channel from '../dist/channel.js';
import * as model from '../dist/channel-model.js';
import { connectionSignature } from '../dist/connection-model.js';
import { ensureTeamData } from '../dist/team.js';

const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const decode=value=>String(value).replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
class FormValues {
  constructor(form){this.values=form.values;}
  get(name){const value=this.values[name];return Array.isArray(value)?value[0]??null:value??null;}
  getAll(name){const value=this.values[name];return value==null?[]:Array.isArray(value)?value:[value];}
  has(name){return name in this.values;}
}
function fixture(method='feishu-app-bot',extra={}) {
  const binding={id:'binding-'+method,platform:method.startsWith('feishu')?'feishu':'wecom',method,name:'Configured '+method,assignedAgent:'a1',enabled:true,configured:true,capabilities:method.endsWith('webhook')?['notification-send']:method==='feishu-api'?['document-read']:['message-receive','message-reply'],...(method==='wecom-ai-bot'?{transport:'websocket'}:{}),...extra};
  binding.connection={version:1,signature:connectionSignature(binding),parameters:{},confirmed:[],test:{status:'success',outcome:'success',at:1,simulated:true}};
  return binding;
}
function harness(bindings=[fixture()]) {
  const original={document:globalThis.document,FormData:globalThis.FormData,localStorage:globalThis.localStorage,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout,fetch:globalThis.fetch};
  const data=structuredClone(initialData),state={page:'inbox',channelDraft:null},nodes=new Map(),timers=[],storage=new Map();
  data.ecosystemBindings=structuredClone(bindings);data.ecosystemSchemaVersion=2;ensureTeamData(data);model.ensureChannelData(data);
  const effects={saved:0,renders:0,modal:null,toasts:[],navigation:null,network:0};
  const form=fields=>{const node={values:fields,dataset:{},reportValidity:()=>true,elements:{namedItem:()=>({focus(){},setCustomValidity(){}})}};nodes.set('#channel-message-form',node);return node;};
  const mount=body=>{
    nodes.delete('#channel-message-form');
    if(!body.includes('id="channel-message-form"'))return;
    const fields={};
    for(const tag of body.match(/<input\b[^>]*>/g)||[]) {
      const name=/\bname="([^"]+)"/.exec(tag)?.[1];if(!name||/\bdisabled\b/.test(tag))continue;
      const value=decode(/\bvalue="([^"]*)"/.exec(tag)?.[1]||'');
      if(/type="(?:checkbox|radio)"/.test(tag)){if(/\bchecked\b/.test(tag))fields[name]=value||'on';}
      else fields[name]=value;
    }
    for(const select of body.matchAll(/<select\b[^>]*name="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
      const options=[...select[2].matchAll(/<option\b([^>]*)>[\s\S]*?<\/option>/g)];
      const selected=options.find(option=>/\bselected\b/.test(option[1]))||options[0];
      fields[select[1]]=decode(/\bvalue="([^"]*)"/.exec(selected?.[1]||'')?.[1]||'');
    }
    for(const textarea of body.matchAll(/<textarea\b[^>]*name="([^"]+)"[^>]*>([\s\S]*?)<\/textarea>/g))fields[textarea[1]]=decode(textarea[2]);
    form(fields);
  };
  globalThis.document={querySelector:selector=>nodes.get(selector)||null,querySelectorAll:()=>[]};
  globalThis.FormData=FormValues;
  globalThis.localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,String(value))};
  globalThis.setTimeout=(callback,delay)=>{const timer={callback,delay,id:timers.length+1,cancelled:false,ran:false};timers.push(timer);return timer.id;};
  globalThis.clearTimeout=id=>{const timer=timers.find(timer=>timer.id===id);if(timer)timer.cancelled=true;};
  globalThis.fetch=()=>{effects.network++;throw Error('Channel demo must not send a real message or request');};
  const ctx={data,state,escape,icon,avatar,t:i18n.t,
    modal:(title,body,footer='')=>{effects.modal={title,body,footer};mount(body);},
    closeOverlay:()=>{effects.modal=null;nodes.delete('#channel-message-form');},
    persist:()=>{effects.saved++;storage.set('workmates-prototype-v1',JSON.stringify(data));},
    render:()=>effects.renders++,toast:message=>effects.toasts.push(message),navigate:(page,id)=>effects.navigation={page,id},
    button:(action,label,ic='',extra='',className='btn')=>`<button class="${className}" data-action="${action}" ${extra}>${label}</button>`
  };
  const input=updates=>({bindingId:data.ecosystemBindings[0].id,eventId:'event-'+Math.random(),sender:'Lin',conversation:'Project planning',message:'整理本周项目进展，给出下一步行动',kind:'direct',mentioned:false,projectId:'p1',scenario:'success',...updates});
  const receive=updates=>model.receiveChannelMessage(ctx,input(updates));
  const action=(name,dataset={})=>channel.handleChannelAction(name,{dataset:{action:name,...dataset}},ctx);
  const tick=()=>{const timer=timers.find(timer=>!timer.ran&&!timer.cancelled);if(!timer)return false;timer.ran=true;timer.callback();return true;};
  const flush=()=>{for(let count=0;count<100&&tick();count++);assert.ok(!timers.some(timer=>!timer.ran&&!timer.cancelled),'Channel timers terminate');};
  const html=()=>[effects.modal?.title,effects.modal?.body,effects.modal?.footer].filter(Boolean).join('');
  const fields=()=>nodes.get('#channel-message-form')?.values||{};
  const change=updates=>form({...fields(),...updates});
  const task=run=>data.tasks.find(task=>task.channelRunId===run.id);
  const restore=()=>{for(const [key,value] of Object.entries(original))globalThis[key]=value;i18n.setLocale('zh-CN');};
  return {data,state,ctx,nodes,timers,storage,effects,form,input,receive,action,tick,flush,html,fields,change,task,restore};
}

test('Only active, currently configured dialogue bindings can receive simulated messages',()=>{
  const bindings=['feishu-app-bot','wecom-ai-bot','wecom-app','feishu-webhook','wecom-webhook','feishu-api'].map(method=>fixture(method));
  const h=harness(bindings);
  try {
    assert.deepEqual(model.eligibleBindings(h.data).map(binding=>binding.method),['feishu-app-bot','wecom-ai-bot','wecom-app']);
    for(const binding of h.data.ecosystemBindings.slice(3))assert.ok(h.receive({bindingId:binding.id}).error);
    const ready=h.data.ecosystemBindings[0];
    for(const change of [{enabled:false},{connection:null},{assignedAgent:'removed-agent'},{connection:{...ready.connection,signature:'outdated'}},{connection:{...ready.connection,test:{simulated:true,status:'error',outcome:'timeout'}}}]) {
      const original=structuredClone(ready);Object.assign(ready,change);
      assert.ok(h.receive().error,'An unavailable channel cannot create a task');Object.assign(ready,original);
    }
    assert.equal(h.data.channelRuns.length,0);assert.equal(h.effects.network,0);
  } finally {h.restore();}
});

test('Inbound validation rejects empty content, invalid projects, missing mentions and unsupported group entry',()=>{
  const h=harness([fixture(),fixture('wecom-app')]);
  try {
    const before=h.data.tasks.length;
    for(const change of [{message:' '},{sender:' '},{conversation:' '},{projectId:'missing-project'},{kind:'group',mentioned:false},{kind:'not-a-kind'},{bindingId:'binding-wecom-app',kind:'group',mentioned:true}])assert.ok(h.receive(change).error,JSON.stringify(change));
    assert.equal(h.data.tasks.length,before);assert.equal(h.data.channelRuns.length,0);
    assert.ok(h.receive({kind:'group',mentioned:true}).run,'Mentioned bot messages are accepted');h.flush();
  } finally {h.restore();}
});

test('An incoming message creates one assigned project task, shows progress, then produces and returns its result',()=>{
  const h=harness();
  try {
    const taskCount=h.data.tasks.length,fileCount=h.data.library.length,agentCount=h.data.agents[0].tasks;
    const {run,error}=h.receive();assert.equal(error,undefined);assert.ok(run);
    const task=h.task(run);assert.ok(task);assert.equal(task.kind,'channel');assert.equal(task.agent,'a1');assert.equal(task.project,'p1');assert.equal(task.status,'running');
    assert.equal(h.data.tasks.length,taskCount+1);assert.equal(h.data.library.length,fileCount,'No artifact exists before execution');
    assert.equal(h.data.agents[0].tasks,agentCount+1);
    assert.match(channel.renderChannelTask(task,h.ctx),/整理本周项目进展/);
    assert.ok(h.tick());assert.equal(task.status,'running','Execution is observable before completion');
    h.flush();assert.equal(run.executionStatus,'done');assert.equal(run.deliveryStatus,'delivered');assert.equal(task.status,'done');
    assert.equal(run.reply.conversation,run.source.conversation);assert.equal(run.reply.platform,run.platform);assert.equal(run.reply.text,run.resultText);assert.equal(run.reply.simulated,true);
    assert.ok(task.file);assert.equal(h.data.library.filter(file=>file.id===task.file).length,1);assert.equal(h.data.library.length,fileCount+1);
    assert.match(channel.renderInbox(h.ctx),/整理本周项目进展/);assert.equal(h.effects.network,0);
  } finally {h.restore();}
});

test('Repeated platform events do not duplicate tasks, but the same event ID in another binding is independent',()=>{
  const h=harness([fixture(),fixture('wecom-ai-bot')]);
  try {
    const first=h.receive({eventId:'same-event'}),again=h.receive({eventId:'same-event'});
    assert.equal(again.duplicate,true);assert.equal(again.run.id,first.run.id);
    h.action('channel-replay',{id:first.run.id});assert.equal(h.data.channelRuns.length,1);
    const other=h.receive({bindingId:'binding-wecom-ai-bot',eventId:'same-event',conversation:'WeCom discussion'});
    assert.notEqual(other.run.id,first.run.id);assert.equal(h.data.channelRuns.length,2);
    assert.equal(h.task(first.run).agent,h.task(other.run).agent,'One partner can serve both platforms');
    h.flush();
    const firstHtml=channel.renderChannelTask(h.task(first.run),h.ctx),otherHtml=channel.renderChannelTask(h.task(other.run),h.ctx);
    assert.match(firstHtml,/Project planning/);assert.doesNotMatch(firstHtml,/WeCom discussion/);assert.match(otherHtml,/WeCom discussion/);
    assert.equal(h.data.tasks.filter(task=>task.kind==='channel').length,2);assert.equal(h.effects.network,0);
  } finally {h.restore();}
});

test('An execution failure can retry the same task without creating duplicate artifacts or partner usage',()=>{
  const h=harness();
  try {
    const {run}=h.receive({scenario:'execution_error'}),task=h.task(run),id=task.id,count=h.data.tasks.length,files=h.data.library.length,usage=h.data.agents[0].tasks;
    h.flush();assert.equal(run.executionStatus,'failed');assert.equal(task.status,'failed');assert.equal(h.data.library.length,files);assert.notEqual(run.deliveryStatus,'delivered');
    h.action('channel-retry-execution',{id:run.id});assert.equal(task.status,'running');h.flush();
    assert.equal(run.executionStatus,'done');assert.equal(run.deliveryStatus,'delivered');assert.equal(h.task(run).id,id);assert.equal(h.data.tasks.length,count);assert.equal(h.data.library.length,files+1);assert.equal(h.data.agents[0].tasks,usage);
  } finally {h.restore();}
});

test('A delivery failure retries only the return step and retains the completed task and artifact',()=>{
  const h=harness();
  try {
    const {run}=h.receive({scenario:'delivery_error'}),task=h.task(run);h.flush();
    assert.equal(run.executionStatus,'done');assert.equal(run.deliveryStatus,'failed');assert.equal(task.status,'done');
    const snapshot={id:task.id,file:task.file,files:h.data.library.length,tasks:h.data.tasks.length,usage:h.data.agents[0].tasks};
    h.action('channel-retry-delivery',{id:run.id});assert.equal(run.deliveryStatus,'sending');h.flush();
    assert.equal(run.deliveryStatus,'delivered');assert.deepEqual({id:task.id,file:task.file,files:h.data.library.length,tasks:h.data.tasks.length,usage:h.data.agents[0].tasks},snapshot);
  } finally {h.restore();}
});

test('Pausing, deleting or reassigning a binding blocks late work from returning to a changed destination',()=>{
  for(const change of ['pause','delete','reassign']) {
    const h=harness();
    try {
      const {run}=h.receive(),binding=h.data.ecosystemBindings[0];
      if(change==='pause')binding.enabled=false;
      else if(change==='delete')h.data.ecosystemBindings=[];
      else binding.assignedAgent='a2';
      h.flush();assert.notEqual(run.deliveryStatus,'delivered',change);
      assert.notEqual(h.task(run).agent,'a2','The task keeps its original partner');
      assert.equal(h.effects.network,0);
    } finally {h.restore();}
  }
});

test('Cancelling active work prevents late callbacks from completing or returning it',()=>{
  const h=harness();
  try {
    const {run}=h.receive(),task=h.task(run);const callbacks=h.timers.map(timer=>timer.callback);
    h.action('channel-cancel-run',{id:run.id});assert.equal(task.status,'failed');assert.equal(run.executionStatus,'cancelled');
    for(const callback of callbacks)callback();h.flush();
    assert.notEqual(run.deliveryStatus,'delivered');assert.equal(task.file,undefined);
  } finally {h.restore();}
});

test('Reload interrupts unfinished execution or delivery instead of inventing a successful return',()=>{
  for(const phase of ['execution','delivery']) {
    const h=harness();
    try {
      const {run}=h.receive();
      if(phase==='delivery')for(let count=0;count<20&&run.deliveryStatus!=='sending';count++)assert.ok(h.tick());
      const saved=structuredClone(h.data),copied=saved.channelRuns.find(item=>item.id===run.id),task=saved.tasks.find(item=>item.channelRunId===run.id);
      model.recoverChannelRuns(saved);
      assert.notEqual(copied.deliveryStatus,'delivered');
      if(phase==='execution'){assert.equal(copied.executionStatus,'interrupted');assert.equal(task.status,'failed');}
      else {assert.equal(copied.deliveryStatus,'interrupted');assert.equal(task.status,'done');assert.ok(task.file);}
      const once=JSON.stringify(saved);model.recoverChannelRuns(saved);assert.equal(JSON.stringify(saved),once,'Recovery is idempotent');
      h.action('channel-cancel-run',{id:run.id});
    } finally {h.restore();}
  }
});

test('The compose dialog cancels without a task, preserves draft fields across redraws and submits through the real action',()=>{
  const h=harness();
  try {
    const count=h.data.tasks.length;
    h.action('channel-compose',{binding:h.data.ecosystemBindings[0].id});
    assert.match(h.html(),/channel-message-form/);
    h.change({sender:'Chen',conversation:'Design sync',message:'Review the updated design 中文',kind:'direct',projectId:'p2',scenario:'success'});
    channel.captureChannelDraft(h.ctx);channel.rerenderChannelDraft(h.ctx);
    assert.match(h.html(),/Review the updated design 中文/);
    h.action('channel-cancel-compose');assert.equal(h.data.tasks.length,count);
    h.action('channel-compose',{binding:h.data.ecosystemBindings[0].id});
    h.change({sender:'Chen',conversation:'Design sync',message:'Review the updated design 中文',kind:'direct',projectId:'p2',scenario:'success'});
    h.action('channel-submit');h.action('channel-submit');assert.equal(h.data.tasks.length,count+1);h.flush();
    assert.equal(h.data.channelRuns[0].deliveryStatus,'delivered');
  } finally {h.restore();}
});

test('Both languages escape incoming content in inbox, task, badge and reply views without contacting platforms',()=>{
  const h=harness();
  try {
    const {run}=h.receive({sender:'Lin <script>alert(1)</script>',conversation:'Room <img src=x onerror=1>',message:'Review <svg/onload=alert(1)> & "quoted"'});h.flush();
    for(const locale of ['zh-CN','en']) {
      i18n.setLocale(locale);
      const html=[channel.renderInbox(h.ctx),channel.renderChannelHome(h.ctx),channel.renderChannelTask(h.task(run),h.ctx),channel.renderChannelTaskBadge(h.task(run),h.ctx)].join('');
      assert.doesNotMatch(html,/<script>|<img src=x|<svg\/onload|undefined|\[object Object\]|channel\.[A-Za-z]|chan\.[A-Za-z]/);
      assert.match(html,/&lt;script&gt;/);assert.ok(!JSON.stringify(h.data.channelRuns).includes('DEMO_ONLY_APP_SECRET'));
    }
    assert.equal(h.effects.network,0);
  } finally {h.restore();}
});

test('Changing saved robot parameters or its test revision blocks result delivery without rerunning completed work',()=>{
  for(const change of ['parameters','test-revision']) {
    const h=harness();
    try {
      const {run}=h.receive(),task=h.task(run);
      for(let count=0;count<20&&run.deliveryStatus!=='sending';count++)assert.ok(h.tick());
      assert.equal(task.status,'done');const file=task.file;
      const binding=h.data.ecosystemBindings[0];
      if(change==='parameters')binding.connection.parameters={appId:'cli_another_robot',transport:'websocket'};
      else binding.connection.test.at=Date.now()+10;
      h.flush();assert.equal(run.deliveryStatus,'failed');assert.equal(task.status,'done');assert.equal(task.file,file);assert.equal(run.reply,undefined);
      h.action('channel-retry-delivery',{id:run.id});h.flush();assert.notEqual(run.deliveryStatus,'delivered','A stale source does not silently redirect through new credentials');
    } finally {h.restore();}
  }
});

test('An unavailable explicit channel never falls back to another bot, and orphaned pending tasks fail safely on reload',()=>{
  const h=harness([fixture(),fixture('wecom-ai-bot')]);
  try {
    h.data.ecosystemBindings[0].enabled=false;
    h.action('channel-compose',{binding:h.data.ecosystemBindings[0].id});
    assert.equal(h.state.channelDraft.bindingId,'','A stale launch target does not silently select the other platform');
    h.change({sender:'Lin',conversation:'Original target',message:'Never reroute this message',kind:'direct',projectId:'',scenario:'success'});
    h.action('channel-submit');assert.equal(h.data.channelRuns.length,0);
    channel.closeChannelDraft(h.ctx);h.ctx.closeOverlay();
    h.data.tasks.unshift({id:'orphan-channel-task',name:'Lost event',kind:'channel',channelRunId:'missing-run',status:'running',agent:'a1'});
    model.recoverChannelRuns(h.data);
    assert.equal(h.data.tasks[0].status,'failed');assert.equal(h.data.tasks[0].file,undefined);
  } finally {h.restore();}
});
