import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { initialData, suggestions } from '../dist/data.js';
import { icon, avatar, logo } from '../dist/icons.js';

const values = new Map();
const storage = { getItem:key=>values.get(key)??null, setItem:(key,value)=>values.set(key,String(value)) };
globalThis.localStorage = storage;
const i18n = await import('../dist/i18n.js');
const { renderSecondary } = await import('../dist/secondary.js');
const ecosystem = await import('../dist/ecosystem.js');
const team = await import('../dist/team.js');
const connection = await import('../dist/connection.js');
const connectionModel = await import('../dist/connection-model.js');
const channel = await import('../dist/channel.js');
const channelModel = await import('../dist/channel-model.js');
let serial = 0;

// Execute the actual UI renderers and handlers with browser I/O replaced at the boundary.
function appHarness() {
  const nodes = new Map(['#app','#overlay-root','#toast-root','meta[name="description"]'].map(key=>[key,{innerHTML:'',content:'',replaceChildren(node){this.child=node;}}]));
  const handlers = new Map();
  const document = {
    title:'',documentElement:{lang:''},body:{style:{}},activeElement:null,
    querySelector:selector=>nodes.get(selector)||null,
    querySelectorAll:()=>[],
    createElement:()=>({innerHTML:'',className:'',remove(){}}),
    addEventListener:(type,fn)=>handlers.set(type,fn)
  };
  const context = vm.createContext({
    ...i18n,...ecosystem,...team,...connection,...channelModel,...channel,renderSecondary,initialData,suggestions,icon,avatar,logo,document,
    localStorage:storage,structuredClone,console,innerWidth:1280,
    window:{scrollY:0,scrollTo(){},matchMedia:()=>({addEventListener(){}}),addEventListener(){}},
    location:{hash:''},history:{pushState(){}},
    setTimeout:()=>0,clearTimeout(){},Map,FormData,Blob,URL
  });
  const code=readFileSync(new URL('../dist/app.js',import.meta.url),'utf8').replace(/^import[^\n]+\n/gm,'');
  vm.runInContext(code,context);
  return {context,document,nodes,handlers,run:script=>vm.runInContext(script,context),html:()=>nodes.get('#app').innerHTML};
}

test('Chinese is the default, unknown stored locales fall back, supported choices survive reload',async()=>{
  values.clear();
  let fresh=await import(`../dist/i18n.js?case=${++serial}`);
  assert.equal(fresh.getLocale(),'zh-CN');
  values.set('workx-locale','fr');
  fresh=await import(`../dist/i18n.js?case=${++serial}`);
  assert.equal(fresh.getLocale(),'zh-CN');
  assert.equal(fresh.setLocale('en'),true);
  assert.equal(values.get('workx-locale'),'en');
  const reloaded=await import(`../dist/i18n.js?case=${++serial}`);
  assert.equal(reloaded.getLocale(),'en');
  assert.equal(reloaded.setLocale('fr'),false);
  assert.equal(reloaded.getLocale(),'en');
  reloaded.setLocale('zh-CN');
});

test('Blocked storage still supports a session language choice',async()=>{
  globalThis.localStorage={getItem(){throw Error('blocked')},setItem(){throw Error('blocked')}};
  const fresh=await import(`../dist/i18n.js?case=${++serial}`);
  assert.equal(fresh.getLocale(),'zh-CN');
  fresh.setLocale('en');
  assert.equal(fresh.t('Home'),'Home');
  globalThis.localStorage=storage;
});

test('Both catalogs are complete and substitutions preserve arbitrary user content',()=>{
  for(const [key,pair] of Object.entries(i18n.messages)) {
    assert.equal(pair.length,2,key);
    for(const text of pair)assert.equal(typeof text,'string',key);
    const params=text=>[...text.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort();
    assert.deepEqual(params(pair[0]),params(pair[1]),key);
  }
  for(const file of ['app.js','secondary.js']) {
    const source=readFileSync(new URL('../dist/'+file,import.meta.url),'utf8');
    for(const match of source.matchAll(/\b(?:tr|actionText|t)\(\s*(['"])([^'"\n]+)\1/g)) {
      if(!['suggestion.','workspace.'].includes(match[2]))assert.ok(i18n.messages[match[2]],`${file}: ${match[2]}`);
    }
  }
  for(const file of ['ecosystem.js','connection.js','connection-model.js','channel.js','channel-model.js']) {
    const source=readFileSync(new URL('../dist/'+file,import.meta.url),'utf8');
    for(const match of source.matchAll(/['"]((?:eco|scene|conn|channel)\.[A-Za-z0-9_.]+)['"]/g)) {
      const concatenated=/^\s*\+/.test(source.slice(match.index+match[0].length));
      if(!match[1].endsWith('.')&&!concatenated)assert.ok(i18n.messages[match[1]],`${file}: ${match[1]}`);
    }
  }
  i18n.setLocale('en');
  const prompt='中文 English <script> & {name}';
  assert.equal(i18n.t('chat.received',{prompt}),'Your request: '+prompt);
  i18n.setLocale('zh-CN');
  assert.equal(i18n.formatSchedule('Every Friday at 17:00'),'每周五 17:00');
  assert.equal(i18n.formatRelative('Oct 29'),'10月29日');
});

test('Every route renders in both languages; title and html language agree',()=>{
  const app=appHarness();
  for(const locale of ['zh-CN','en']) {
    i18n.setLocale(locale);
    for(const page of ['home','new','detail','task','automations','projects','project','library','hub','code','ecosystem','scenarios','team','inbox']) {
      app.run(`state.page=${JSON.stringify(page)};state.task='t2';state.project='p1';render()`);
      const html=app.html();
      assert.ok(html.includes(locale==='zh-CN'?'切换语言':'Change language'),page);
      assert.ok(!/undefined|null|\[object Object\]/.test(html),page);
      assert.equal(app.document.documentElement.lang,locale);
      assert.ok(app.document.title.endsWith(' · WorkX'));
    }
    app.run("state.page='detail'");
    for(const tab of ['Instructions','Capabilities','Work Context','Ecosystem','Manage']) {
      app.run(`state.detailTab=${JSON.stringify(tab)};render()`);
      assert.ok(!app.html().includes('undefined'));
    }
  }
  i18n.setLocale('zh-CN');app.run("state.page='home';render()");
  assert.equal(app.document.title,'首页 · WorkX');
  assert.match(app.html(),/>首页<|>首页<\/span>/);
});

test('Language switching preserves task/code drafts, selected project, data, and canonical options',async()=>{
  i18n.setLocale('zh-CN');
  const existing=structuredClone(initialData);existing.tasks[0].name='Home 中文 <测试>';
  values.set('workmates-prototype-v1',JSON.stringify(existing));
  const before=values.get('workmates-prototype-v1');
  const app=appHarness();
  app.handlers.get('input')({target:{id:'task-prompt',value:'Keep this 中文 task',matches:()=>false}});
  app.handlers.get('input')({target:{id:'code-prompt',value:'Build <Dashboard> 中文',matches:()=>false}});
  app.handlers.get('change')({target:{id:'code-project',value:'p2'}});
  app.run("state.page='code';state.selectedProject='p1';state.capabilities=['Deep Research'];render()");
  await app.run("action({dataset:{action:'set-language',locale:'en'}},{})");
  assert.equal(i18n.getLocale(),'en');
  assert.equal(values.get('workx-locale'),'en');
  assert.match(app.html(),/Build &lt;Dashboard&gt; 中文/);
  assert.match(app.html(),/<option value="p2" selected>/);
  assert.equal(app.run('state.draft'),'Keep this 中文 task');
  assert.equal(app.run('state.selectedProject'),'p1');
  assert.equal(app.run('state.capabilities[0]'),'Deep Research');
  assert.equal(app.run('data.tasks[0].name'),'Home 中文 <测试>');
  assert.equal(values.get('workmates-prototype-v1'),before);
  await app.run("action({dataset:{action:'set-language',locale:'zh-CN'}},{})");
  app.run("state.page='new';render()");
  assert.match(app.html(),/Keep this 中文 task/);
  assert.match(app.html(),/data-value="Deep Research"/);
  assert.match(app.html(),/>深度调研<\/button>/);
});

test('Forms retain canonical values while labels, placeholders, and responses switch',()=>{
  const app=appHarness();
  for(const locale of ['zh-CN','en']) {
    i18n.setLocale(locale);
    app.run('createAgent()');
    let html=app.nodes.get('#overlay-root').innerHTML;
    assert.match(html,/<option value="Personal" selected>/);
    assert.ok(html.includes(locale==='zh-CN'?'给你的伙伴取个名字':'Give your workmate a name'));
    app.run('createAutomation()');
    html=app.nodes.get('#overlay-root').innerHTML;
    assert.match(html,/<option value="Every Friday">/);
    assert.ok(html.includes(locale==='zh-CN'?'每周五':'Every Friday'));
    app.run("state.page='task';state.task='t2';render()");
    assert.ok(app.html().includes(locale==='zh-CN'?'任务已完成':'Task completed'));
    app.run('showFile("f1")');
    assert.ok(app.nodes.get('#overlay-root').innerHTML.includes(locale==='zh-CN'?'项目目标':'Project goal'));
  }
});

test('Language switching keeps an open ecosystem wizard and its unsaved capability choices',async()=>{
  i18n.setLocale('zh-CN');
  values.set('workmates-prototype-v1',JSON.stringify(initialData));
  const before=values.get('workmates-prototype-v1');
  const app=appHarness();
  app.run("state.page='ecosystem';state.ecosystemWizard={step:4,editingId:null,error:'',draft:{platform:'feishu',method:'feishu-app-bot',assignedAgent:'a1',name:'Before typing',capabilities:['message-receive','message-reply'],enabled:true}};rerenderEcosystemWizard(workspaceContext())");
  const form={fields:{name:'跨平台 <Agent>',capabilities:['document-read']}};
  app.nodes.set('#eco-wizard-form',form);
  const previousDocument=globalThis.document,previousFormData=globalThis.FormData;
  globalThis.document=app.document;
  globalThis.FormData=class {
    constructor(node){this.fields=node.fields;}
    get(name){const value=this.fields[name];return Array.isArray(value)?value[0]:value??null;}
    getAll(name){const value=this.fields[name];return Array.isArray(value)?value:value==null?[]:[value];}
  };
  try {
    await app.run("action({dataset:{action:'set-language',locale:'en'}},{})");
    const html=app.nodes.get('#overlay-root').innerHTML;
    assert.match(html,/id="eco-wizard-form" data-step="4"/);
    assert.match(html,/跨平台 &lt;Agent&gt;/);
    assert.ok(html.includes(i18n.t('eco.stepCapabilities')));
    assert.equal(app.run('state.ecosystemWizard.step'),4);
    assert.equal(app.run('state.ecosystemWizard.draft.name'),'跨平台 <Agent>');
    assert.deepEqual(Array.from(app.run('state.ecosystemWizard.draft.capabilities')),['message-receive','message-reply','document-read']);
    assert.equal(values.get('workmates-prototype-v1'),before,'Locale changes never save an unfinished binding');
    app.nodes.delete('#eco-wizard-form');
    await app.run("action({dataset:{action:'close'}},{})");
    await app.run("action({dataset:{action:'set-language',locale:'zh-CN'}},{})");
    assert.equal(app.nodes.get('#overlay-root').innerHTML,'','A closed wizard is not revived by later locale changes');
  } finally {
    globalThis.document=previousDocument;
    globalThis.FormData=previousFormData;
    i18n.setLocale('zh-CN');
  }
});

test('Connection setup switches language in place and Escape discards its sensitive draft',async()=>{
  i18n.setLocale('zh-CN');
  values.set('workmates-prototype-v1',JSON.stringify(initialData));
  const before=values.get('workmates-prototype-v1'),app=appHarness();
  app.run("data.ecosystemBindings=[{id:'locale-binding',platform:'feishu',method:'feishu-app-bot',assignedAgent:'a1',name:'跨平台配置',capabilities:['message-receive','message-reply'],enabled:true,configured:true}]");
  await app.run("action({dataset:{action:'conn-open',id:'locale-binding'}},{})");
  app.nodes.set('#connection-form',{fields:{appId:'cli_demo_locale',appSecret:'SESSION_ONLY_<value>',transport:'websocket'}});
  const previousDocument=globalThis.document,previousFormData=globalThis.FormData;
  globalThis.document=app.document;
  globalThis.FormData=class {
    constructor(node){this.fields=node.fields;}
    get(name){const value=this.fields[name];return Array.isArray(value)?value[0]:value??null;}
    getAll(name){const value=this.fields[name];return Array.isArray(value)?value:value==null?[]:[value];}
  };
  try {
    await app.run("action({dataset:{action:'set-language',locale:'en'}},{})");
    assert.equal(app.run('state.connection.stage'),'params');
    assert.equal(app.run('state.connection.draft.params.appSecret'),'SESSION_ONLY_<value>');
    assert.ok(app.nodes.get('#overlay-root').innerHTML.includes(i18n.t('conn.title')));
    assert.match(app.nodes.get('#overlay-root').innerHTML,/type="password" value="SESSION_ONLY_&lt;value&gt;"/);
    assert.equal(values.get('workmates-prototype-v1'),before);
    const abandoned=app.run('state.connection');
    app.handlers.get('keydown')({key:'Escape'});
    assert.equal(app.run('state.connection'),null);
    assert.equal(Object.keys(abandoned.draft.params).length,0);
    assert.equal(app.nodes.get('#overlay-root').innerHTML,'');
    app.nodes.delete('#connection-form');
    await app.run("action({dataset:{action:'set-language',locale:'zh-CN'}},{})");
    assert.equal(app.nodes.get('#overlay-root').innerHTML,'');
    assert.equal(values.get('workmates-prototype-v1'),before);
  } finally {
    globalThis.document=previousDocument;globalThis.FormData=previousFormData;i18n.setLocale('zh-CN');
  }
});

test('Incoming message draft keeps platform, source and project during language switching',async()=>{
  i18n.setLocale('zh-CN');
  const existing=structuredClone(initialData);
  const binding={id:'inbound-language',platform:'feishu',method:'feishu-app-bot',assignedAgent:'a1',name:'语言测试',capabilities:['message-receive','message-reply'],configured:true,enabled:true};
  binding.connection={signature:connectionModel.connectionSignature(binding),parameters:{appId:'cli_demo'},confirmed:[],test:{simulated:true,outcome:'success',status:'success',at:1}};
  existing.ecosystemBindings=[binding];existing.ecosystemSchemaVersion=2;
  values.set('workmates-prototype-v1',JSON.stringify(existing));
  const before=values.get('workmates-prototype-v1'),app=appHarness();
  await app.run("action({dataset:{action:'channel-compose',binding:'inbound-language'}},{})");
  app.nodes.set('#channel-message-form',{fields:{bindingId:binding.id,sender:'林 <测试>',conversation:'项目讨论群',message:'整理本次需求 <保留>',kind:'group',mentioned:'on',projectId:'p1',scenario:'delivery_error'}});
  const previousDocument=globalThis.document,previousFormData=globalThis.FormData;
  globalThis.document=app.document;
  globalThis.FormData=class {
    constructor(node){this.fields=node.fields;}
    get(name){const value=this.fields[name];return Array.isArray(value)?value[0]:value??null;}
    getAll(name){const value=this.fields[name];return Array.isArray(value)?value:value==null?[]:[value];}
  };
  try {
    await app.run("action({dataset:{action:'set-language',locale:'en'}},{})");
    assert.equal(app.run('state.channelDraft.bindingId'),binding.id);
    assert.equal(app.run('state.channelDraft.message'),'整理本次需求 <保留>');
    assert.equal(app.run('state.channelDraft.mentioned'),true);
    assert.equal(app.run('state.channelDraft.projectId'),'p1');
    assert.equal(app.run('state.channelDraft.scenario'),'delivery_error');
    assert.match(app.nodes.get('#overlay-root').innerHTML,/整理本次需求 &lt;保留&gt;/);
    assert.ok(app.nodes.get('#overlay-root').innerHTML.includes(i18n.t('channel.simulate')));
    assert.equal(app.run('data.channelRuns.length'),0);
    assert.equal(values.get('workmates-prototype-v1'),before);
    app.handlers.get('keydown')({key:'Escape'});
    assert.equal(app.run('state.channelDraft'),null);
    assert.equal(app.nodes.get('#overlay-root').innerHTML,'');
    assert.equal(values.get('workmates-prototype-v1'),before);
  } finally {
    globalThis.document=previousDocument;globalThis.FormData=previousFormData;i18n.setLocale('zh-CN');
  }
});
