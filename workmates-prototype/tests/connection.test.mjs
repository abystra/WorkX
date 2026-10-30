import test from 'node:test';
import assert from 'node:assert/strict';
import { initialData } from '../dist/data.js';
import { icon, avatar } from '../dist/icons.js';
import * as i18n from '../dist/i18n.js';
import * as ecosystem from '../dist/ecosystem.js';
import * as connection from '../dist/connection.js';
import * as model from '../dist/connection-model.js';

const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const decode=value=>String(value).replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
class FormValues {
  constructor(form){this.values=form.values;}
  get(name){const value=this.values[name];return Array.isArray(value)?value[0]??null:value??null;}
  getAll(name){const value=this.values[name];return value==null?[]:Array.isArray(value)?value:[value];}
  has(name){return name in this.values;}
  *entries(){for(const name of Object.keys(this.values))for(const value of this.getAll(name))yield[name,value];}
  [Symbol.iterator](){return this.entries();}
}

function fixture(method='feishu-app-bot',extras={}) {
  return {id:'binding-'+method,platform:method.startsWith('feishu')?'feishu':'wecom',method,name:'Team connection',assignedAgent:'a1',enabled:true,configured:true,capabilities:method.endsWith('webhook')?['notification-send']:method==='feishu-api'?['document-read']:['message-receive','message-reply'],...(method==='wecom-ai-bot'?{transport:'websocket'}:{}),...extras};
}

// Only browser I/O and the clock are replaced. The actual UI/model code handles
// every parameter, authorization decision, test transition and saved record.
function harness(bindings=[fixture()]) {
  const original={document:globalThis.document,FormData:globalThis.FormData,localStorage:globalThis.localStorage,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout,fetch:globalThis.fetch};
  const data=structuredClone(initialData),state={page:'ecosystem',connection:null},nodes=new Map(),storage=new Map(),timers=[];
  data.ecosystemBindings=structuredClone(bindings);data.ecosystemSchemaVersion=2;
  const effects={saved:0,renders:0,closed:0,modal:null,toasts:[],network:0};
  const form=(fields={})=>{
    const elements=Object.fromEntries(Object.entries(fields).map(([name,value])=>[name,{value,focus(){},setCustomValidity(){},reportValidity:()=>true}]));
    elements.namedItem=name=>elements[name]||null;
    const node={values:fields,elements,dataset:{},reportValidity:()=>true,
      querySelector(selector){const name=/name=["']([^"']+)/.exec(selector)?.[1];return elements[name]||null;},
      querySelectorAll(selector){const name=/name=["']([^"']+)/.exec(selector)?.[1];const value=fields[name];return (Array.isArray(value)?value:[]).map(value=>({value,checked:true}));}
    };
    nodes.set('#connection-form',node);return node;
  };
  const mount=body=>{
    nodes.delete('#connection-form');
    if(!body.includes('id="connection-form"'))return;
    const fields={};
    for(const tag of body.match(/<input\b[^>]*>/g)||[]) {
      const name=/\bname="([^"]+)"/.exec(tag)?.[1];
      if(!name||/\bdisabled\b/.test(tag))continue;
      const value=decode(/\bvalue="([^"]*)"/.exec(tag)?.[1]||'');
      if(/type="(?:checkbox|radio)"/.test(tag)){if(/\bchecked\b/.test(tag))(fields[name]??=[]).push(value||'on');}
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
  globalThis.fetch=()=>{effects.network++;throw new Error('A connection prototype must not contact a real endpoint');};
  const ctx={data,state,escape,icon,avatar,t:i18n.t,
    modal:(title,body,footer='')=>{effects.modal={title,body,footer};mount(body);},
    closeOverlay:()=>{effects.closed++;effects.modal=null;nodes.delete('#connection-form');},
    persist:()=>{effects.saved++;storage.set('workmates-prototype-v1',JSON.stringify(data));},
    render:()=>effects.renders++,toast:message=>effects.toasts.push(message),navigate(){},
    button:(action,label,ic='',extra='',className='btn')=>`<button class="${className}" data-action="${action}" ${extra}>${label}</button>`
  };
  const action=(name,dataset={})=>connection.handleConnectionAction(name,{dataset:{action:name,...dataset}},ctx);
  const html=()=>[effects.modal?.title,effects.modal?.body,effects.modal?.footer].filter(Boolean).join('');
  const fields=()=>nodes.get('#connection-form')?.values||{};
  const change=updates=>form({...fields(),...updates});
  const tick=()=>{const timer=timers.find(timer=>!timer.ran&&!timer.cancelled);if(!timer)return false;timer.ran=true;timer.callback();return true;};
  const flush=()=>{for(let count=0;count<50&&tick();count++);assert.ok(!timers.some(timer=>!timer.ran&&!timer.cancelled),'Connection test timers terminate');};
  const restore=()=>{for(const [key,value] of Object.entries(original))globalThis[key]=value;i18n.setLocale('zh-CN');};
  i18n.setLocale('zh-CN');
  return {data,state,ctx,nodes,storage,effects,timers,form,fields,change,action,html,tick,flush,restore};
}

const configurations=[
  {method:'feishu-app-bot'},
  {method:'feishu-app-bot',params:{transport:'callback'}},
  {method:'feishu-webhook'},
  {method:'feishu-webhook',params:{signing:'signature'}},
  {method:'feishu-api'},
  {method:'wecom-ai-bot'},
  {method:'wecom-ai-bot',binding:{transport:'callback'}},
  {method:'wecom-app'},
  {method:'wecom-webhook'}
];

test('Each platform method and transport requires its own valid parameters',()=>{
  for(const config of configurations) {
    const binding=fixture(config.method,config.binding),params=model.demoConnectionParams(binding,config.params),spec=model.connectionSpec(binding,params);
    assert.deepEqual(model.validateConnection(binding,{params}),[],`${config.method}: example fields are valid`);
    for(const field of spec.fields.filter(field=>field.required)) {
      const errors=model.validateConnection(binding,{params:{...params,[field.id]:'  '}});
      assert.ok(errors.some(error=>error.field===field.id),`${config.method}: ${field.id} cannot be omitted`);
    }
    assert.ok(spec.steps.length>=3,`${config.method}: platform-specific setup has an actionable checklist`);
    assert.ok(spec.steps.every(step=>/^https:\/\//.test(step.url)));
  }
  const fields=(method,params={},extra={})=>model.connectionSpec(fixture(method,extra),params).fields.map(field=>field.id);
  assert.ok(fields('feishu-app-bot',{transport:'callback'}).includes('verificationToken'));
  assert.ok(!fields('feishu-app-bot',{transport:'websocket'}).includes('verificationToken'));
  assert.ok(fields('feishu-webhook',{signing:'signature'}).includes('signingSecret'));
  assert.ok(!fields('feishu-webhook',{signing:'none'}).includes('signingSecret'));
  assert.deepEqual(fields('wecom-ai-bot'),['botId','botSecret']);
  assert.ok(!fields('wecom-ai-bot',{}, {transport:'callback'}).includes('botSecret'));
  assert.ok(fields('wecom-app').includes('corpId'));assert.ok(fields('wecom-app').includes('agentId'));
  assert.deepEqual(fields('feishu-api'),['appId','appSecret']);
  assert.equal(model.connectionSpec(fixture('feishu-api')).testStages.at(-1),'tools');
});

test('Validation rejects incorrect webhook hosts and malformed application or callback identifiers',()=>{
  for(const method of ['feishu-webhook','wecom-webhook']) {
    const binding=fixture(method),params=model.demoConnectionParams(binding);
    for(const webhookUrl of ['http://open.feishu.cn/open-apis/bot/v2/hook/key','https://attacker.example/send?key=demo','https://qyapi.weixin.qq.com.evil.example/cgi-bin/webhook/send?key=demo','javascript:alert(1)']) {
      assert.ok(model.validateConnection(binding,{params:{...params,webhookUrl}}).some(error=>error.field==='webhookUrl'));
    }
  }
  const binding=fixture('wecom-app'),params=model.demoConnectionParams(binding);
  assert.ok(model.validateConnection(binding,{params:{...params,agentId:'not-a-number'}}).some(error=>error.field==='agentId'));
  assert.ok(model.validateConnection(binding,{params:{...params,encodingAESKey:'too-short'}}).some(error=>error.field==='encodingAESKey'));
  assert.ok(model.validateConnection(binding,{params:{...params,corpId:'<script>alert(1)</script>'}}).some(error=>error.field==='corpId'));
  assert.ok(model.validateConnection(fixture('wecom-ai-bot',{transport:'undecided'}),{params:{}}).length);
});

test('Saved configuration retains public setup only, never credentials or raw diagnostics',()=>{
  for(const config of configurations) {
    const binding=fixture(config.method,config.binding),params=model.demoConnectionParams(binding,config.params),spec=model.connectionSpec(binding,params);
    const draft={params:{...params,injectedSecret:'NEVER_SAVE_THIS'},confirmed:[...spec.steps.map(step=>step.id),'fake-grant'],test:{status:'success',outcome:'success',at:123456,simulated:true,error:'NEVER_SAVE_THIS'}};
    const saved=model.sanitizeConnection(binding,draft),serialized=JSON.stringify(saved);
    assert.ok(!serialized.includes('NEVER_SAVE_THIS'));
    for(const field of spec.fields.filter(field=>field.sensitive)) {
      assert.ok(!(field.id in saved.parameters),`${config.method}: ${field.id} is not persisted`);
      assert.ok(!serialized.includes(params[field.id]),`${config.method}: secret content never enters storage`);
    }
    assert.ok(!saved.confirmed.includes('fake-grant'));
    assert.equal(saved.test.simulated,true);
    binding.connection=saved;
    const reloaded=model.initialConnectionDraft(binding);
    assert.ok(model.validateConnection(binding,reloaded).length>0,'Reload requires credentials to be entered again');
    for(const field of spec.fields.filter(field=>field.sensitive))assert.ok(!reloaded.params[field.id]);
  }
});

test('Binding edits preserve connection setup only while its integration identity is unchanged',()=>{
  const before=fixture('feishu-app-bot'),params=model.demoConnectionParams(before),steps=model.connectionSpec(before,params).steps.map(step=>step.id);
  before.connection=model.sanitizeConnection(before,{params,confirmed:steps,test:{outcome:'success',at:123456,simulated:true}});
  const renamed=model.reconcileConnection(before,{...before,name:'Renamed channel',enabled:false,capabilities:[...before.capabilities].reverse()});
  assert.deepEqual(renamed.connection,before.connection,'Names, paused state, and capability ordering do not lose setup');
  for(const change of [{assignedAgent:'a2'},{method:'feishu-webhook',capabilities:['notification-send']},{capabilities:[...before.capabilities,'document-read']},{transport:'callback'},{platform:'wecom'}]) {
    const changed=model.reconcileConnection(before,{...before,...change});
    assert.equal(changed.connection,undefined,'Changing integration identity invalidates previous authorization/test metadata');
  }
  assert.ok(before.connection,'Reconciliation does not mutate the previous record');
});

function prepare(h,bindingId=h.data.ecosystemBindings[0].id,choices={}) {
  h.action('conn-open',{id:bindingId});
  h.action('conn-sample');
  if(Object.keys(choices).length) {
    h.change(choices);
    connection.handleConnectionChange({tagName:'SELECT',closest:()=>h.nodes.get('#connection-form')},h.ctx);
    h.action('conn-sample');
  }
  h.action('conn-next');
  assert.equal(h.state.connection.stage,'authorization');
  const confirmed=[...h.html().matchAll(/<input\b[^>]*name="confirmed"[^>]*value="([^"]+)"/g)].map(match=>decode(match[1]));
  assert.ok(confirmed.length>=3,'Authorization steps are rendered as explicit confirmations');
  h.change({confirmed});h.action('conn-next');
  assert.equal(h.state.connection.stage,'test');
}
function simulate(h,outcome='success') {
  h.change({scenario:outcome});h.action('conn-test');
  assert.equal(h.state.connection.running,true);
  assert.match(h.html(),/conn-stop/);
  h.flush();
  assert.equal(h.state.connection.running,false);
  assert.equal(h.state.connection.draft.test.outcome,outcome);
  assert.equal(h.state.connection.draft.test.simulated,true);
}

test('All platform configurations complete the real parameter, authorization and simulated-test UI flow',()=>{
  for(const config of configurations) {
    const h=harness([fixture(config.method,config.binding)]);
    try {
      const originalTasks=JSON.stringify(h.data.tasks);
      prepare(h,undefined,config.params);
      assert.equal(h.effects.saved,0,'The configuration remains a draft until Save');
      simulate(h);
      assert.match(h.html(),/is-success/);
      const params={...h.state.connection.draft.params},binding=h.data.ecosystemBindings[0];
      h.action('conn-save');
      assert.equal(h.state.connection,null);
      assert.equal(h.effects.saved,1);
      const persisted=JSON.parse(h.storage.get('workmates-prototype-v1'));
      assert.equal(persisted.ecosystemBindings[0].connection.test.outcome,'success');
      for(const field of model.connectionSpec(binding,params).fields.filter(field=>field.sensitive)) {
        assert.ok(!h.storage.get('workmates-prototype-v1').includes(params[field.id]),`${config.method}: no credential enters localStorage`);
      }
      assert.equal(JSON.stringify(h.data.tasks),originalTasks,'Connection testing does not create an AI task');
      assert.equal(h.effects.network,0);
      h.action('conn-open',{id:binding.id});
      for(const field of model.connectionSpec(binding,params).fields.filter(field=>field.sensitive))assert.ok(!h.state.connection.draft.params[field.id]);
      h.action('conn-test');
      assert.equal(h.state.connection.running,false,'Reloaded public metadata cannot replace required credentials');
      assert.equal(h.state.connection.stage,'params');
    } finally {h.restore();}
  }
});

test('Missing parameters and authorization steps prevent a simulated test and explain the correction',()=>{
  const h=harness();
  try {
    h.action('conn-open',{id:h.data.ecosystemBindings[0].id});
    h.action('conn-next');
    assert.equal(h.state.connection.stage,'params');
    assert.ok(h.state.connection.errors.some(error=>error.field==='appId'));
    assert.match(h.html(),/aria-invalid="true"/);
    h.action('conn-sample');h.action('conn-next');
    assert.equal(h.state.connection.stage,'authorization');
    h.action('conn-tab',{stage:'test'});h.action('conn-test');
    assert.equal(h.state.connection.stage,'authorization');
    assert.equal(h.state.connection.running,false);
    assert.ok(h.state.connection.error);
    assert.equal(h.effects.saved,0);
    assert.equal(h.timers.length,0,'No network-test animation starts before prerequisites');
  } finally {h.restore();}
});

test('Failed credentials, missing permissions and timeouts show targeted recovery, and retry can succeed',()=>{
  for(const outcome of ['credential_error','permission_error','timeout']) {
    const h=harness();
    try {
      prepare(h);simulate(h,outcome);
      assert.match(h.html(),/is-error/);
      if(outcome==='credential_error') {
        assert.match(h.html(),/conn-fix-params/);h.action('conn-fix-params');assert.equal(h.state.connection.stage,'params');
        h.action('conn-tab',{stage:'test'});
      } else if(outcome==='permission_error') {
        assert.match(h.html(),/conn-fix-auth/);h.action('conn-fix-auth');assert.equal(h.state.connection.stage,'authorization');
        h.action('conn-tab',{stage:'test'});
      }
      h.change({scenario:'success'});h.action('conn-retry');h.flush();
      assert.equal(h.state.connection.draft.test.outcome,'success');
      assert.equal(h.effects.saved,0,'Retry never auto-saves or grants a real permission');
      assert.equal(h.effects.network,0);
    } finally {h.restore();}
  }
});

test('Changing parameters clears prior authorization and test results; secret reveal is explicit and reversible',()=>{
  const h=harness();
  try {
    prepare(h);simulate(h);
    h.action('conn-tab',{stage:'params'});
    const secret=h.fields().appSecret;
    assert.match(h.html().match(/<input[^>]*name="appSecret"[^>]*>/)?.[0]||'',/type="password"/);
    assert.ok(!h.html().replace(/<input[^>]*>/g,'').includes(secret),'Credentials are not echoed in status or instructions');
    h.action('conn-show-secret',{field:'appSecret'});
    assert.match(h.html().match(/<input[^>]*name="appSecret"[^>]*>/)?.[0]||'',/type="text"/);
    h.action('conn-show-secret',{field:'appSecret'});
    assert.match(h.html().match(/<input[^>]*name="appSecret"[^>]*>/)?.[0]||'',/type="password"/);
    h.change({appId:'cli_changed'});
    connection.handleConnectionChange({tagName:'INPUT',closest:()=>h.nodes.get('#connection-form')},h.ctx);
    assert.deepEqual(h.state.connection.draft.confirmed,[]);
    assert.equal(h.state.connection.draft.test,null);
    h.action('conn-next');h.action('conn-next');
    assert.equal(h.state.connection.stage,'authorization','Changed parameters need their setup confirmations again');
    h.action('conn-cancel');assert.equal(h.state.connection,null);assert.equal(h.effects.saved,0);
  } finally {h.restore();}
});

test('Cancelling, closing, replacing, mutating or deleting a connection makes late test callbacks harmless',()=>{
  for(const operation of ['stop','close','replace','mutate','delete']) {
    const h=harness([fixture(),fixture('wecom-ai-bot')]);
    try {
      prepare(h);h.action('conn-test');
      const old=h.state.connection,callback=h.timers.find(timer=>!timer.cancelled&&!timer.ran).callback;
      if(operation==='stop')h.action('conn-stop');
      if(operation==='close')h.action('conn-cancel');
      if(operation==='replace')h.action('conn-open',{id:h.data.ecosystemBindings[1].id});
      if(operation==='mutate')h.data.ecosystemBindings[0].capabilities.push('document-read');
      if(operation==='delete')h.data.ecosystemBindings.splice(0,1);
      callback();h.flush();
      assert.equal(old.draft.test,null,operation+': stale callbacks never create a result');
      assert.equal(h.effects.saved,0,operation+': stale callbacks never persist');
      if(operation==='replace')assert.equal(h.state.connection.bindingId,h.data.ecosystemBindings[1].id);
      if(operation==='close')assert.equal(h.state.connection,null);
      if(operation==='delete'){h.action('conn-cancel');assert.equal(h.state.connection,null,'Cancel still closes a deleted binding');}
      assert.equal(h.effects.network,0);
    } finally {h.restore();}
  }
});

test('A binding configuration is isolated from other platforms, and both languages escape user content',()=>{
  const name='Team <script>alert("x")</script> & "quoted"',h=harness([fixture('feishu-app-bot',{name}),fixture('wecom-ai-bot')]);
  try {
    const other=JSON.stringify(h.data.ecosystemBindings[1]);
    prepare(h);simulate(h);h.action('conn-save');
    assert.equal(JSON.stringify(h.data.ecosystemBindings[1]),other);
    for(const locale of ['zh-CN','en']) {
      i18n.setLocale(locale);h.action('conn-open',{id:h.data.ecosystemBindings[0].id});
      for(const stage of ['params','authorization','test']) {
        h.action('conn-tab',{stage});
        assert.ok(h.html().includes(escape(name)));
        assert.doesNotMatch(h.html(),/<script>|undefined|\[object Object\]|conn\.[A-Za-z]/);
        assert.match(h.html(),/data-action="set-language"/);
      }
      h.action('conn-cancel');
    }
  } finally {h.restore();}
});

test('A completed result cannot be saved after its binding identity changes',()=>{
  const h=harness();
  try {
    prepare(h);simulate(h);
    h.data.ecosystemBindings[0].assignedAgent='a2';
    h.action('conn-save');
    assert.equal(h.effects.saved,0,'The old test is not signed or saved against a changed binding');
    assert.equal(h.data.ecosystemBindings[0].connection,undefined);
    assert.equal(h.state.connection,null,'Stale credentials are cleared when the binding changes');
  } finally {h.restore();}
});

test('Revoking a setup confirmation invalidates success and a running test cannot be saved',()=>{
  const h=harness();
  try {
    prepare(h);h.action('conn-test');h.action('conn-save');
    assert.equal(h.effects.saved,0,'The unfinished running test cannot be saved');
    h.flush();assert.equal(h.state.connection.draft.test.outcome,'success');
    h.action('conn-tab',{stage:'authorization'});
    h.change({confirmed:h.fields().confirmed.slice(1)});
    connection.handleConnectionChange({tagName:'INPUT',closest:()=>h.nodes.get('#connection-form')},h.ctx);
    assert.equal(h.state.connection.draft.test,null);
    h.action('conn-tab',{stage:'test'});h.action('conn-test');
    assert.equal(h.state.connection.stage,'authorization');
    assert.equal(h.state.connection.running,false);
    assert.equal(h.effects.saved,0);
  } finally {h.restore();}
});
