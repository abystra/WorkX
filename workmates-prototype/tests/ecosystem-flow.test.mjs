import test from 'node:test';
import assert from 'node:assert/strict';
import { initialData } from '../dist/data.js';
import { icon, avatar } from '../dist/icons.js';
import * as ecosystem from '../dist/ecosystem.js';
import { connectionSignature } from '../dist/connection-model.js';
import * as i18n from '../dist/i18n.js';

const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const decode = value => value.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');

// These substitutes only cover browser I/O. Every workflow, migration and renderer
// under test is the production function; no API or browser is contacted.
class FormValues {
  constructor(form) { this.values = form.values; }
  get(name) { const value=this.values[name];return Array.isArray(value)?value[0]??null:value??null; }
  getAll(name) { const value=this.values[name];return value==null?[]:Array.isArray(value)?value:[value]; }
  has(name) { return name in this.values; }
  *entries() { for(const name of Object.keys(this.values))for(const value of this.getAll(name))yield[name,value]; }
  [Symbol.iterator]() { return this.entries(); }
}

function harness(source=initialData) {
  const data=structuredClone(source), state={page:'ecosystem',agent:'a1'}, nodes=new Map(), storage=new Map();
  const effects={saved:0,renders:0,closed:0,modal:null,navigation:null,toasts:[]};
  globalThis.FormData=FormValues;
  globalThis.localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,String(value))};
  globalThis.document={querySelector:selector=>nodes.get(selector)||null,querySelectorAll:()=>[]};
  i18n.setLocale('zh-CN');
  ecosystem.ensureEcosystemData(data);
  const form=(fields={},step=state.ecosystemWizard?.step,valid=true)=>{
    const elements=Object.fromEntries(Object.entries(fields).map(([name,value])=>[name,{value,focus(){},setCustomValidity(){},reportValidity:()=>valid}]));
    elements.namedItem=name=>elements[name];
    const node={values:fields,elements,dataset:{step:String(step)},reportValidity:()=>valid,
      querySelectorAll(query){const name=/name=["']?([\w-]+)/.exec(query)?.[1];return (Array.isArray(fields[name])?fields[name]:[]).map(value=>({value,checked:true}));}
    };
    nodes.set('#eco-wizard-form',node);
    return node;
  };
  // Replace a rendered form's DOM defaults, as a real modal replacement does.
  const mountForm=body=>{
    nodes.delete('#eco-wizard-form');
    if(!body.includes('id="eco-wizard-form"'))return;
    const fields={};
    for(const tag of body.match(/<input\b[^>]*>/g)||[]) {
      const name=/\bname="([^"]+)"/.exec(tag)?.[1];
      if(!name||/\bdisabled\b/.test(tag))continue;
      const value=decode(/\bvalue="([^"]*)"/.exec(tag)?.[1]||'');
      if(/type="(?:checkbox|radio)"/.test(tag)) {
        if(!/\bchecked\b/.test(tag))continue;
        (fields[name]??=[]).push(value);
      } else fields[name]=value;
    }
    for(const select of body.matchAll(/<select\b[^>]*name="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
      const options=[...select[2].matchAll(/<option\b([^>]*)>[\s\S]*?<\/option>/g)];
      const selected=options.find(option=>/\bselected\b/.test(option[1]))||options[0];
      fields[select[1]]=decode(/\bvalue="([^"]*)"/.exec(selected?.[1]||'')?.[1]||'');
    }
    form(fields);
  };
  const ctx={data,state,escape,icon,avatar,t:i18n.t,
    modal:(title,body,footer='')=>{effects.modal={title,body,footer};mountForm(body);},
    closeOverlay:()=>{effects.closed++;effects.modal=null;nodes.delete('#eco-wizard-form');},
    persist:()=>{effects.saved++;storage.set('workmates-prototype-v1',JSON.stringify(data));},
    render:()=>effects.renders++,
    navigate:(page,id)=>effects.navigation={page,id},toast:message=>effects.toasts.push(message),
    button:(action,label,ic='',extra='',className='btn')=>`<button class="${className}" data-action="${action}" ${extra}>${label}</button>`
  };
  const action=(name,dataset={})=>ecosystem.handleEcosystemAction(name,{dataset:{action:name,...dataset}},ctx);
  const create=({platform='feishu',method='feishu-app-bot',agent='a1',name='Team assistant',capabilities=['message-receive','message-reply'],transport='websocket'}={})=>{
    const priorIds=new Set(data.ecosystemBindings.map(binding=>binding.id));
    action('eco-add');action('eco-platform',{value:platform});action('eco-next');
    action('eco-method',{value:method});form({transport});action('eco-next');
    form({assignedAgent:agent});action('eco-next');
    form({name,capabilities});action('eco-save');
    const saved=data.ecosystemBindings.find(binding=>!priorIds.has(binding.id));
    assert.ok(saved,'The completed wizard saves a new binding');
    return saved;
  };
  return {data,state,effects,storage,ctx,form,action,create};
}

const modalHtml = h => (h.effects.modal?.body||'')+(h.effects.modal?.footer||'');

test('Four steps validate choices, preserve draft values on Back, and cancel without saving',()=>{
  const h=harness(), before=JSON.stringify(h.data);
  h.action('eco-add');
  assert.equal(h.state.ecosystemWizard.step,1);
  assert.match(modalHtml(h),/eco-next/);
  h.action('eco-save');
  assert.equal(h.data.ecosystemBindings.length,0,'Save cannot skip incomplete stages');
  h.action('eco-next');
  assert.equal(h.state.ecosystemWizard.step,1,'A platform is required before proceeding');
  h.action('eco-platform',{value:'feishu'});h.action('eco-next');
  assert.equal(h.state.ecosystemWizard.step,2);
  h.action('eco-method',{value:'feishu-app-bot'});h.action('eco-next');
  assert.equal(h.state.ecosystemWizard.step,3);
  h.form({assignedAgent:'missing-agent'});h.action('eco-next');
  assert.equal(h.state.ecosystemWizard.step,3,'A removed or unknown agent cannot be bound');
  h.form({assignedAgent:'a2'});h.action('eco-next');
  assert.equal(h.state.ecosystemWizard.step,4);
  assert.match(modalHtml(h),/eco-save/);
  h.form({name:'Draft <retained>',capabilities:['message-receive','message-reply','document-read']});
  h.action('eco-back');
  assert.equal(h.state.ecosystemWizard.step,3);
  assert.equal(h.state.ecosystemWizard.draft.name,'Draft <retained>');
  assert.equal(h.state.ecosystemWizard.draft.assignedAgent,'a2');
  h.action('eco-next');
  assert.equal(h.state.ecosystemWizard.step,4);
  assert.match(modalHtml(h),/Draft &lt;retained&gt;/);
  const closedBeforeCancel=h.effects.closed;
  h.action('eco-cancel');
  assert.ok(!h.state.ecosystemWizard);
  assert.equal(JSON.stringify(h.data),before);
  assert.equal(h.effects.saved,0);
  assert.equal(h.effects.closed,closedBeforeCancel+1);
});

test('One partner can bind both platforms and multiple connections without replacing either',()=>{
  const h=harness(), beforeTasks=JSON.stringify(h.data.tasks);
  const feishu=h.create({name:'Feishu partner',agent:'a3',capabilities:['message-receive','message-reply','document-read']});
  const feishuSnapshot=JSON.stringify(feishu);
  const wecom=h.create({platform:'wecom',method:'wecom-ai-bot',name:'WeCom partner',agent:'a3',transport:'callback'});
  const extra=h.create({name:'Second Feishu channel',agent:'a3'});
  assert.equal(h.data.ecosystemBindings.length,3);
  assert.equal(new Set(h.data.ecosystemBindings.map(binding=>binding.id)).size,3);
  assert.equal(JSON.stringify(feishu),feishuSnapshot,'Configuring WeCom does not rewrite Feishu');
  assert.equal(wecom.platform,'wecom');assert.equal(wecom.transport,'callback');
  assert.equal(extra.platform,'feishu');
  assert.ok(h.data.ecosystemBindings.every(binding=>binding.assignedAgent==='a3'));
  h.action('eco-toggle',{id:wecom.id});
  assert.equal(wecom.enabled,false);assert.equal(feishu.enabled,true);assert.equal(extra.enabled,true);
  const saved=JSON.parse(h.storage.get('workmates-prototype-v1'));
  assert.equal(saved.ecosystemSchemaVersion,2);
  assert.equal(saved.ecosystemBindings.length,3);
  const reloaded=harness(saved);
  assert.deepEqual(reloaded.data.ecosystemBindings,h.data.ecosystemBindings);
  assert.equal(JSON.stringify(h.data.tasks),beforeTasks);
});

test('Changing method clears incompatible capabilities, and saving rejects invalid pairings or missing API scope',()=>{
  const h=harness();
  h.action('eco-add',{platform:'feishu'});
  h.action('eco-method',{value:'feishu-app-bot'});h.action('eco-next');
  h.form({assignedAgent:'a1'});h.action('eco-next');
  h.form({name:'Switching connection',capabilities:['message-receive','message-reply','document-write']});
  h.action('eco-back');h.action('eco-back');
  assert.equal(h.state.ecosystemWizard.step,2);
  h.action('eco-method',{value:'feishu-webhook'});
  assert.ok(!h.state.ecosystemWizard.draft.capabilities.includes('document-write'));
  assert.ok(!h.state.ecosystemWizard.draft.capabilities.includes('message-receive'));
  h.action('eco-next');h.action('eco-next');
  h.form({name:'Notifications',capabilities:['notification-send','document-write','message-receive','invented-scope']});
  h.action('eco-save');
  assert.deepEqual(h.data.ecosystemBindings[0].capabilities,['notification-send']);
  h.action('eco-add',{platform:'feishu'});
  h.action('eco-method',{value:'wecom-ai-bot'});h.action('eco-next');
  assert.equal(h.state.ecosystemWizard.step,2,'A method from another platform is not accepted');
  h.action('eco-method',{value:'feishu-api'});h.action('eco-next');
  h.form({assignedAgent:'a1'});h.action('eco-next');
  h.form({name:'API tools',capabilities:[]});h.action('eco-save');
  assert.equal(h.data.ecosystemBindings.length,1,'A business API connection requires a tool capability');
  assert.equal(h.state.ecosystemWizard.step,4);
  h.form({name:'API tools',capabilities:['document-read','message-reply']});h.action('eco-save');
  assert.deepEqual(h.data.ecosystemBindings.find(binding=>binding.method==='feishu-api').capabilities,['document-read']);
});

test('Editing a paused binding preserves its identity and paused state; cancelling an edit is nonmutating',()=>{
  const h=harness(), binding=h.create({name:'Before edit'});
  binding.connection={version:1,signature:connectionSignature(binding),parameters:{appId:'cli_existing',transport:'websocket'},confirmed:['feishuBot'],test:null};
  const configured=structuredClone(binding.connection);
  h.action('eco-toggle',{id:binding.id});
  const paused=JSON.stringify(h.data.ecosystemBindings);
  h.action('eco-edit',{id:binding.id});
  h.state.ecosystemWizard.draft.name='Uncommitted';
  h.action('eco-cancel');
  assert.equal(JSON.stringify(h.data.ecosystemBindings),paused);
  h.action('eco-edit',{id:binding.id});
  for(let attempts=0;attempts<4&&h.state.ecosystemWizard.step<4;attempts++)h.action('eco-next');
  assert.equal(h.state.ecosystemWizard.step,4,'An existing binding can reach its final edit step');
  h.form({name:'Paused but renamed',capabilities:['message-receive','message-reply']});h.action('eco-save');
  assert.equal(h.data.ecosystemBindings.length,1);
  assert.equal(h.data.ecosystemBindings[0].id,binding.id);
  assert.equal(h.data.ecosystemBindings[0].name,'Paused but renamed');
  assert.equal(h.data.ecosystemBindings[0].enabled,false);
  assert.deepEqual(h.data.ecosystemBindings[0].connection,configured,'Renaming a binding preserves its platform setup');
  h.action('eco-edit',{id:binding.id});
  for(let attempts=0;attempts<4&&h.state.ecosystemWizard.step<4;attempts++)h.action('eco-next');
  h.form({name:'Changed capabilities',capabilities:['message-receive','message-reply','document-read']});h.action('eco-save');
  assert.equal(h.data.ecosystemBindings[0].connection,undefined,'Changing capability requests invalidates the earlier setup checks');
});

test('Legacy bindings retain user names, paused state and undecided choices; migration runs once',()=>{
  const source=structuredClone(initialData);
  source.agents[0].demoConnected=true;
  source.ecosystemConnections={
    feishu:{name:'Old <Feishu>',configured:true,enabled:false,assignedAgent:'a2',mode:'feishu-app'},
    wecom:{name:'My unknown choice',configured:true,enabled:false,assignedAgent:'a4',mode:'undecided'}
  };
  const legacy=JSON.stringify(source.ecosystemConnections), tasks=JSON.stringify(source.tasks);
  const h=harness(source);
  const feishu=h.data.ecosystemBindings.find(binding=>binding.platform==='feishu'&&binding.assignedAgent==='a2');
  const wecom=h.data.ecosystemBindings.find(binding=>binding.platform==='wecom');
  assert.equal(feishu.name,'Old <Feishu>');assert.equal(feishu.method,'feishu-app-bot');assert.equal(feishu.enabled,false);
  assert.equal(wecom.name,'My unknown choice');assert.equal(wecom.method,'undecided');assert.equal(wecom.enabled,false);
  assert.equal(wecom.assignedAgent,'a4');
  assert.equal(JSON.stringify(h.data.ecosystemConnections),legacy);
  assert.equal(JSON.stringify(h.data.tasks),tasks);
  const once=JSON.stringify(h.data);ecosystem.ensureEcosystemData(h.data);
  assert.equal(JSON.stringify(h.data),once);
  assert.equal(h.effects.saved,0,'Opening a workspace does not rewrite local storage');
});

test('Deleting requires confirmation and migrated bindings never reappear after a saved reload',()=>{
  const source=structuredClone(initialData);
  source.agents[0].demoConnected=true;
  source.ecosystemConnections={wecom:{name:'Legacy bot',configured:true,enabled:false,assignedAgent:'a4',mode:'wecom-bot'}};
  const h=harness(source);
  assert.ok(h.data.ecosystemBindings.some(binding=>binding.platform==='feishu'&&binding.assignedAgent==='a1'));
  const count=h.data.ecosystemBindings.length, binding=h.data.ecosystemBindings[0];
  h.action('eco-delete',{id:binding.id});
  assert.equal(h.data.ecosystemBindings.length,count);
  assert.match(modalHtml(h),/eco-delete-confirm/);
  // The confirmation's close/cancel action does not mutate the model.
  const cancel=/data-action="([^"]+)"[^>]*>[\s\S]*?/.exec(h.effects.modal.footer)?.[1];
  if(cancel==='eco-cancel')h.action(cancel);else h.ctx.closeOverlay();
  assert.equal(h.data.ecosystemBindings.length,count);
  for(const item of [...h.data.ecosystemBindings]) {
    h.action('eco-delete',{id:item.id});h.action('eco-delete-confirm',{id:item.id});
  }
  assert.equal(h.data.ecosystemBindings.length,0);
  const saved=JSON.parse(h.storage.get('workmates-prototype-v1'));
  assert.equal(saved.ecosystemSchemaVersion,2);
  assert.ok(saved.ecosystemConnections.wecom,'The old object remains available as historical data');
  const reloaded=harness(saved);ecosystem.ensureEcosystemData(reloaded.data);
  assert.deepEqual(reloaded.data.ecosystemBindings,[],'Neither legacy objects nor demoConnected can resurrect a deleted binding');
});

test('Only a ready conversational binding offers a local task preview, without creating tasks or network traffic',()=>{
  const h=harness(), beforeTasks=JSON.stringify(h.data.tasks), originalFetch=globalThis.fetch;
  let network=0;
  globalThis.fetch=()=>{network++;throw new Error('External request from a local prototype');};
  try {
    const bot=h.create({name:'Conversational bot'});
    h.action('eco-preview',{id:bot.id});assert.match(modalHtml(h),/eco-try-task/);
    h.action('eco-try-task',{id:bot.id});assert.deepEqual(h.effects.navigation,{page:'new',id:'a1'});
    const appBot=h.create({platform:'wecom',method:'wecom-app',agent:'a2',name:'Self-built application'});
    h.action('eco-preview',{id:appBot.id});assert.match(modalHtml(h),/eco-try-task/);
    h.action('eco-try-task',{id:appBot.id});assert.deepEqual(h.effects.navigation,{page:'new',id:'a2'});
    for(const config of [
      {method:'feishu-webhook',name:'Feishu notification',capabilities:['notification-send']},
      {platform:'wecom',method:'wecom-webhook',name:'WeCom notification',capabilities:['notification-send']},
      {method:'feishu-api',name:'API tools',capabilities:['document-read']}
    ]) {
      const binding=h.create(config);h.effects.navigation=null;
      h.action('eco-preview',{id:binding.id});
      assert.doesNotMatch(modalHtml(h),/eco-try-task/);
      h.action('eco-try-task',{id:binding.id});assert.equal(h.effects.navigation,null);
    }
    h.action('eco-toggle',{id:bot.id});h.effects.navigation=null;
    h.action('eco-preview',{id:bot.id});assert.doesNotMatch(modalHtml(h),/eco-try-task/);
    h.action('eco-try-task',{id:bot.id});assert.equal(h.effects.navigation,null);
    assert.equal(JSON.stringify(h.data.tasks),beforeTasks);assert.equal(network,0);
  } finally {globalThis.fetch=originalFetch;}
});

test('Partner detail filters its bindings, while both languages render escaped user content and complete four-step labels',()=>{
  const h=harness();
  const malicious='Partner <script>alert("x")</script> & "quoted"';
  h.data.agents.find(agent=>agent.id==='a1').name=malicious;
  h.create({name:'A1 Feishu <img src=x onerror=alert(1)>',agent:'a1'});
  h.create({platform:'wecom',method:'wecom-ai-bot',name:'A1 WeCom',agent:'a1'});
  h.create({name:'ONLY A4 PRIVATE CONNECTION',agent:'a4'});
  for(const locale of ['zh-CN','en']) {
    i18n.setLocale(locale);
    const page=ecosystem.renderEcosystem(h.ctx), detail=ecosystem.renderAgentEcosystem('a1',h.ctx);
    assert.match(detail,/A1 Feishu/);assert.match(detail,/A1 WeCom/);
    assert.doesNotMatch(detail,/ONLY A4 PRIVATE CONNECTION/);
    assert.ok(page.includes(escape(malicious)));
    assert.ok(page.includes('&lt;img src=x onerror=alert(1)&gt;'));
    assert.doesNotMatch(page+detail,/<script>|<img src=x|undefined|\[object Object\]|eco\.[A-Za-z]/);
    assert.match(page,locale==='zh-CN'?/飞书/:/Feishu/);
    assert.match(page,locale==='zh-CN'?/企业微信/:/WeCom/);
    h.action('eco-add');
    for(const label of locale==='zh-CN'?['平台','接入方式','关联伙伴','授权能力']:['Platform','Connection method','Linked workmate','Capabilities']) {
      assert.ok(modalHtml(h).toLowerCase().includes(label.toLowerCase()),`${locale}: ${label}`);
    }
    h.action('eco-cancel');
  }
  i18n.setLocale('zh-CN');
});
