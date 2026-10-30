import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { initialData, suggestions } from '../dist/data.js';
import { icon, avatar, logo } from '../dist/icons.js';
import * as ecosystem from '../dist/ecosystem.js';
import * as connection from '../dist/connection.js';
import * as channel from '../dist/channel.js';
import * as channelModel from '../dist/channel-model.js';
import * as team from '../dist/team.js';
import * as i18n from '../dist/i18n.js';
import { renderSecondary } from '../dist/secondary.js';

const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

// The real renderers and action handlers run unchanged. Only browser I/O is replaced.
class FormValues {
  constructor(form) { this.values = form.values; }
  get(name) { const value = this.values[name]; return Array.isArray(value) ? value[0] ?? null : value ?? null; }
  getAll(name) { const value = this.values[name]; return value == null ? [] : Array.isArray(value) ? value : [value]; }
  has(name) { return name in this.values; }
  *entries() { for (const key of Object.keys(this.values)) for (const value of this.getAll(key)) yield [key,value]; }
  [Symbol.iterator]() { return this.entries(); }
}

function browserBoundary(saved) {
  const values = new Map(saved ? [['workmates-prototype-v1',JSON.stringify(saved)]] : []);
  const storage = { getItem:key=>values.get(key)??null, setItem:(key,value)=>values.set(key,String(value)) };
  const nodes = new Map(['#app','#overlay-root','#toast-root','meta[name="description"]'].map(key=>[key,{
    innerHTML:'',content:'',replaceChildren(node){this.child=node;},focus(){},setAttribute(){},
    classList:{toggle(){},add(){},remove(){}}
  }]));
  const handlers = new Map();
  const document = {
    title:'',documentElement:{lang:''},body:{style:{}},activeElement:null,
    querySelector:selector=>nodes.get(selector)||null,
    querySelectorAll:selector=>nodes.get(selector)||[],
    createElement:()=>({innerHTML:'',className:'',remove(){},click(){}}),
    addEventListener:(type,fn)=>handlers.set(type,fn)
  };
  globalThis.document = document;
  globalThis.localStorage = storage;
  globalThis.FormData = FormValues;
  const form = (selector,fields,options={}) => {
    const elements = Object.fromEntries(Object.entries(fields).map(([name,value])=>[name,{value,focus(){},setCustomValidity(){},reportValidity(){return options.valid!==false;}}]));
    elements.namedItem=name=>elements[name];
    const node = { values:fields,elements,dataset:options.dataset||{},reportValidity:()=>options.valid!==false,
      querySelectorAll(query) { const name = /name=["']?([\w-]+)/.exec(query)?.[1]; return (Array.isArray(fields[name])?fields[name]:[]).map(value=>({value,checked:true})); }
    };
    nodes.set(selector,node);
    return node;
  };
  const field = (selector,value,extra={}) => { const node={value,focus(){},setCustomValidity(){},...extra};nodes.set(selector,node);return node; };
  return {values,storage,nodes,handlers,document,form,field};
}

function moduleHarness(source=initialData) {
  const boundary=browserBoundary();
  const data=structuredClone(source);
  ecosystem.ensureEcosystemData(data);
  team.ensureTeamData(data);
  const state={teamTab:'members',projectTab:'tasks',page:'team',project:'p1',agent:'a1'};
  const effects={saved:0,renders:0,closed:0,toasts:[],modal:null,navigation:null};
  const ctx={data,state,escape,icon,avatar,t:i18n.t,
    modal:(title,body,footer='')=>effects.modal={title,body,footer},
    closeOverlay:()=>effects.closed++,
    persist:()=>{effects.saved++;boundary.storage.setItem('workmates-prototype-v1',JSON.stringify(data));},
    render:()=>effects.renders++,
    navigate:(page,id)=>effects.navigation={page,id},
    toast:message=>effects.toasts.push(message),
    button:(action,label,ic='',extra='',className='btn')=>`<button class="${className}" data-action="${action}" ${extra}>${ic?icon(ic,16):''}${label}</button>`
  };
  const action=(kind,name,dataset={})=>kind==='ecosystem'
    ? ecosystem.handleEcosystemAction(name,{dataset:{action:name,...dataset}},ctx)
    : team.handleTeamAction(name,{dataset:{action:name,...dataset}},ctx);
  return {...boundary,data,state,effects,ctx,action};
}

function appHarness({saved,hash=''}={}) {
  const boundary=browserBoundary(saved);
  const timers=[];
  const context=vm.createContext({
    ...i18n,...ecosystem,...connection,...channel,...channelModel,...team,renderSecondary,initialData,suggestions,icon,avatar,logo,
    document:boundary.document,localStorage:boundary.storage,structuredClone,console,innerWidth:1280,
    window:{scrollY:0,scrollTo(){},matchMedia:()=>({addEventListener(){}}),addEventListener(){}},
    location:{hash},history:{pushState(){}},setTimeout:(callback,delay)=>{timers.push({callback,delay});return timers.length;},clearTimeout(){},Map,FormData:FormValues,Blob,URL
  });
  const code=readFileSync(new URL('../dist/app.js',import.meta.url),'utf8').replace(/^import[^\n]+\n/gm,'');
  vm.runInContext(code,context);
  return {...boundary,context,timers,run:script=>vm.runInContext(script,context),html:()=>boundary.nodes.get('#app').innerHTML};
}

test('A project task adds its selected agent and moves to review while the project stays open',()=>{
  const app=appHarness();
  i18n.setLocale('zh-CN');
  app.run("state.selectedProject='p1';state.agent='a2';startTask('新的团队交付任务')");
  const taskId=app.run('state.task');
  assert.equal(app.run('data.tasks[0].project'),'p1');
  assert.equal(app.run('data.projects[0].agentIds.includes("a2")'),true);
  assert.equal(app.run('data.tasks[0].status'),'running');
  app.run("navigate('project','p1')");
  assert.match(app.html(),/新的团队交付任务/);
  const completion=app.timers.find(timer=>timer.delay===1600);
  assert.ok(completion);
  completion.callback();
  assert.equal(app.run('state.page'),'project');
  assert.equal(app.run('taskBy('+JSON.stringify(taskId)+').status'),'done');
  const reviewColumn=app.html().split('wx-project-column is-review')[1]?.split('wx-project-column is-accepted')[0];
  assert.match(reviewColumn,/新的团队交付任务/);
  const saved=JSON.parse(app.values.get('workmates-prototype-v1'));
  assert.equal(saved.tasks[0].status,'done');
  assert.ok(saved.projects[0].agentIds.includes('a2'));
});

test('Collaboration data upgrades preserve existing work and do not invent business scenarios',()=>{
  const data=structuredClone(initialData);
  data.projects[0].name='Existing <Project>';
  data.projects[0].sharedContext='Saved context 中文';
  data.projects[0].memberIds=[];
  data.projects[0].agentIds=['a4'];
  data.ecosystemConnections={wecom:{name:'Existing connector',configured:true,enabled:false,assignedAgent:'a4',mode:'wecom-bot'}};
  data.scenarioDrafts=[];
  const beforeTasks=JSON.stringify(data.tasks);
  const beforeConnections=JSON.stringify(data.ecosystemConnections);
  ecosystem.ensureEcosystemData(data);
  team.ensureTeamData(data);
  assert.equal(JSON.stringify(data.tasks),beforeTasks);
  assert.equal(JSON.stringify(data.ecosystemConnections),beforeConnections);
  assert.equal(data.projects[0].sharedContext,'Saved context 中文');
  assert.deepEqual(data.projects[0].memberIds,[]);
  assert.deepEqual(data.projects[0].agentIds,['a4']);
  assert.deepEqual(data.scenarioDrafts,[]);
  const once=JSON.stringify(data);
  ecosystem.ensureEcosystemData(data);
  team.ensureTeamData(data);
  assert.equal(JSON.stringify(data),once,'Migration is repeatable without replacing saved data');
});

test('New workspace routes and project tabs render through the app in both languages',()=>{
  for(const locale of ['zh-CN','en']) {
    const app=appHarness({hash:'#ecosystem'});
    i18n.setLocale(locale);
    for(const page of ['home','ecosystem','scenarios','team','project','inbox']) {
      app.run(`state.page=${JSON.stringify(page)};state.project='p1';render()`);
      const html=app.html();
      assert.ok(!/undefined|null|\[object Object\]/.test(html),`${locale}: ${page}`);
      for(const route of ['ecosystem','scenarios','team'])assert.ok(html.includes(`data-page="${route}"`),`${page}: ${route} navigation`);
      assert.equal(app.document.documentElement.lang,locale);
      assert.ok(app.document.title.endsWith(' · WorkX'));
    }
    app.run("state.page='ecosystem';render()");
    assert.match(app.html(),locale==='zh-CN'?/飞书/:/Feishu/);
    assert.match(app.html(),locale==='zh-CN'?/企业微信/:/WeCom/);
    assert.match(app.html(),locale==='zh-CN'?/本地原型/:/local prototype/i);
    app.run("state.page='detail';state.detailTab='Ecosystem';state.agent='a1';render()");
    assert.ok(!app.html().includes('Feishu Settings'));
    assert.ok(!app.html().includes('飞书设置'));
    assert.ok(app.html().includes('data-page="ecosystem"'));
    for(const projectTab of ['tasks','context','members']) {
      app.run(`state.page='project';state.project='p1';state.projectTab=${JSON.stringify(projectTab)};render()`);
      assert.ok(!/undefined|null|\[object Object\]/.test(app.html()),projectTab);
    }
    for(const teamTab of ['members','agents','activity']) {
      app.run(`state.page='team';state.teamTab=${JSON.stringify(teamTab)};render()`);
      assert.ok(!/undefined|null|\[object Object\]/.test(app.html()),teamTab);
    }
  }
  i18n.setLocale('zh-CN');
});

test('Legacy Feishu demo configuration migrates into ecosystem without replacing WeCom or user work',()=>{
  const saved=structuredClone(initialData);
  saved.agents[0].demoConnected=true;
  saved.tasks[0].name='Keep task <中文>';
  saved.ecosystemConnections={wecom:{name:'My bot',configured:true,enabled:false,assignedAgent:'a4',mode:'wecom-bot'}};
  saved.scenarioDrafts=[];
  const app=appHarness({saved,hash:'#ecosystem'});
  assert.equal(app.run('state.page'),'ecosystem');
  assert.equal(app.run('data.tasks[0].name'),'Keep task <中文>');
  assert.equal(app.run('data.ecosystemBindings.find(binding=>binding.platform==="feishu").configured'),true);
  assert.equal(app.run('data.ecosystemBindings.find(binding=>binding.platform==="wecom").name'),'My bot');
  assert.equal(app.run('data.ecosystemBindings.find(binding=>binding.platform==="wecom").enabled'),false);
  assert.equal(app.run('data.ecosystemBindings.find(binding=>binding.platform==="wecom").assignedAgent'),'a4');
  assert.equal(app.run('data.ecosystemSchemaVersion'),2);
  assert.equal(app.run('data.scenarioDrafts.length'),0);
  assert.equal(app.values.get('workmates-prototype-v1'),JSON.stringify(saved),'Opening the new UI does not rewrite saved records');
});

test('Ecosystem configuration, pause, resume, and preview stay local and preserve chosen agents',()=>{
  const h=moduleHarness();
  const beforeTasks=JSON.stringify(h.data.tasks);
  const originalFetch=globalThis.fetch;
  let externalCalls=0;
  globalThis.fetch=()=>{externalCalls++;throw new Error('Unexpected external request');};
  try {
    assert.deepEqual(h.data.ecosystemBindings,[]);
    assert.equal(h.action('ecosystem','eco-add',{platform:'wecom'}),true);
    assert.match(h.effects.modal.body,/eco-wizard-form/);
    assert.doesNotMatch(h.effects.modal.body,/type="password"|name="(?:token|secret|webhook)"/i);
    h.action('ecosystem','eco-method',{value:'wecom-ai-bot'});
    h.form('#eco-wizard-form',{transport:'websocket'},{dataset:{step:'2'}});
    h.action('ecosystem','eco-next');
    h.form('#eco-wizard-form',{assignedAgent:'a4'},{dataset:{step:'3'}});
    h.action('ecosystem','eco-next');
    h.form('#eco-wizard-form',{name:'   ',capabilities:['message-receive','message-reply']},{dataset:{step:'4'}});
    h.action('ecosystem','eco-save');
    assert.equal(h.effects.saved,0,'Whitespace-only names are rejected');
    h.form('#eco-wizard-form',{name:'  Bot <demo>  ',capabilities:['message-receive','message-reply']},{dataset:{step:'4'}});
    h.action('ecosystem','eco-save');
    const binding=h.data.ecosystemBindings[0];
    assert.equal(binding.name,'Bot <demo>');
    assert.equal(binding.method,'wecom-ai-bot');
    assert.equal(binding.assignedAgent,'a4');
    assert.equal(binding.enabled,true);
    h.action('ecosystem','eco-toggle',{id:binding.id});
    assert.equal(binding.enabled,false);
    assert.equal(binding.assignedAgent,'a4');
    h.action('ecosystem','eco-preview',{id:binding.id});
    assert.doesNotMatch(h.effects.modal?.footer||'',/eco-try-task/,'Paused connections have no task action');
    h.action('ecosystem','eco-try-task',{id:binding.id});
    assert.equal(h.effects.navigation,null);
    h.action('ecosystem','eco-toggle',{id:binding.id});
    h.action('ecosystem','eco-preview',{id:binding.id});
    assert.match(h.effects.modal.body,/Bot &lt;demo&gt;/);
    h.action('ecosystem','eco-try-task',{id:binding.id});
    assert.deepEqual(h.effects.navigation,{page:'new',id:'a4'});
    assert.equal(JSON.stringify(h.data.tasks),beforeTasks,'Preview does not create or send a task');
    const saved=JSON.parse(h.values.get('workmates-prototype-v1'));
    assert.equal(saved.ecosystemBindings[0].enabled,true);
    assert.equal(externalCalls,0);
    assert.match(ecosystem.renderEcosystem(h.ctx),/Bot &lt;demo&gt;/);
  } finally {globalThis.fetch=originalFetch;}
});

test('Scenario drafts can be created, edited, cancelled, and removed without becoming runnable tasks',()=>{
  const h=moduleHarness();
  const beforeTasks=JSON.stringify(h.data.tasks);
  assert.equal(h.data.scenarioDrafts.length,0);
  const fields={name:'Needs <review>',problem:'Clarify 中文 workflow',role:'Product owner',input:'Input & sources',output:'A reviewed plan',ecosystems:['feishu','wecom','unknown']};
  h.form('#scenario-form',fields);
  assert.equal(h.action('ecosystem','scenario-save'),true);
  assert.equal(h.data.scenarioDrafts.length,1);
  const draft=h.data.scenarioDrafts[0];
  assert.equal(draft.status,'draft');
  assert.deepEqual(draft.ecosystems,['feishu','wecom']);
  assert.match(ecosystem.renderScenarios(h.ctx),/Needs &lt;review&gt;/);
  assert.equal(JSON.stringify(h.data.tasks),beforeTasks);
  assert.equal(h.action('ecosystem','scenario-run',{id:draft.id}),false,'Drafts have no executable workflow');
  h.form('#scenario-form',{...fields,name:'Edited draft',ecosystems:['wecom']},{dataset:{id:draft.id}});
  h.action('ecosystem','scenario-save');
  assert.equal(h.data.scenarioDrafts.length,1);
  assert.equal(h.data.scenarioDrafts[0].name,'Edited draft');
  assert.deepEqual(h.data.scenarioDrafts[0].ecosystems,['wecom']);
  const persisted=JSON.parse(h.values.get('workmates-prototype-v1'));
  assert.equal(persisted.scenarioDrafts[0].id,draft.id);
  h.action('ecosystem','scenario-delete',{id:draft.id});
  assert.equal(h.data.scenarioDrafts.length,1,'Opening removal confirmation does not delete a draft');
  assert.match(h.effects.modal.footer,/scenario-edit/);
  h.action('ecosystem','scenario-edit',{id:draft.id});
  assert.equal(h.data.scenarioDrafts.length,1,'Cancel returns to the editable draft');
  h.action('ecosystem','scenario-delete-confirm',{id:draft.id});
  assert.equal(h.data.scenarioDrafts.length,0);
  assert.equal(JSON.parse(h.values.get('workmates-prototype-v1')).scenarioDrafts.length,0);
  assert.equal(JSON.stringify(h.data.tasks),beforeTasks);
});

test('Project collaboration saves shared context, roster, and accountable people plus supporting agents',()=>{
  const h=moduleHarness();
  const project=h.data.projects.find(project=>project.id==='p1');
  h.form('#team-context-form',{context:'  Goal <b>one</b>\nShared source & context  '});
  assert.equal(h.action('team','team-save-context',{id:project.id}),true);
  assert.equal(project.sharedContext,'Goal <b>one</b>\nShared source & context');
  h.state.projectTab='context';
  assert.match(team.renderProjectWorkspace(project,h.ctx),/Goal &lt;b&gt;one&lt;\/b&gt;/);
  assert.equal(h.data.teamActivity[0].type,'contextChanged');
  const originalRoster=[...project.memberIds];
  h.form('#team-roster-form',{members:[],agents:['a1']});
  h.action('team','team-save-roster',{id:project.id});
  assert.deepEqual(project.memberIds,originalRoster,'An invalid empty roster is not saved');
  h.form('#team-roster-form',{members:['m2','missing'],agents:['a1','a2','missing']});
  h.action('team','team-save-roster',{id:project.id});
  assert.deepEqual(project.memberIds,['m2']);
  assert.deepEqual(project.agentIds,['a1','a2']);
  h.form('#team-assignment-form',{owner:'m2',agents:['a1','a2','a3','missing']});
  h.action('team','team-save-assignment',{id:'t1'});
  const task=h.data.tasks.find(task=>task.id==='t1');
  assert.equal(task.ownerId,'m2');
  assert.deepEqual(task.supportingAgentIds,['a2'],'Only project agents other than the primary agent can support the task');
  assert.equal(task.agent,'a1');
  assert.equal(task.status,'done');
  const saved=JSON.parse(h.values.get('workmates-prototype-v1'));
  assert.equal(saved.projects.find(project=>project.id==='p1').sharedContext,project.sharedContext);
  assert.equal(saved.tasks.find(task=>task.id==='t1').ownerId,'m2');
  h.state.projectTab='tasks';
  assert.match(team.renderProjectWorkspace(project,h.ctx),/Lin/);
  assert.equal(h.data.teamActivity[0].type,'assigned');
});

test('Human confirmation moves completed outcomes between review and accepted without changing execution status',()=>{
  const h=moduleHarness();
  const task=h.data.tasks.find(task=>task.id==='t1');
  const project=h.data.projects.find(project=>project.id===task.project);
  const running=h.data.tasks.find(task=>task.id==='t2');
  running.status='running';
  h.action('team','team-accept-task',{id:running.id});
  assert.equal(running.reviewState,undefined);
  assert.equal(h.effects.saved,0,'Running work cannot be accepted');
  h.action('team','team-accept-task',{id:task.id});
  assert.equal(task.reviewState,'accepted');
  assert.equal(task.status,'done');
  assert.equal(h.data.teamActivity[0].type,'accepted');
  const acceptedColumn=/class="wx-project-column is-accepted"[\s\S]*?<\/section>/.exec(team.renderProjectWorkspace(project,h.ctx))?.[0];
  assert.ok(acceptedColumn?.includes(escape(task.name)));
  const saves=h.effects.saved;
  h.action('team','team-accept-task',{id:task.id});
  assert.equal(h.effects.saved,saves,'Repeated confirmation is idempotent');
  h.action('team','team-reopen-task',{id:task.id});
  assert.equal(task.reviewState,'review');
  assert.equal(task.status,'done');
  const reviewColumn=/class="wx-project-column is-review"[\s\S]*?<\/section>/.exec(team.renderProjectWorkspace(project,h.ctx))?.[0];
  assert.ok(reviewColumn?.includes(escape(task.name)));
  assert.equal(h.data.teamActivity[0].type,'reopened');
});

test('Team resources and local member roles update without sending invitations or changing the owner',()=>{
  const h=moduleHarness();
  const owner=h.data.teamMembers.find(member=>member.role==='owner');
  h.form('#team-role-form',{role:'member'});
  h.action('team','team-save-role',{id:owner.id});
  assert.equal(owner.role,'owner');
  assert.equal(h.effects.saved,0);
  h.form('#team-member-form',{name:'  New <member>  ',role:'owner'});
  h.action('team','team-save-member');
  const member=h.data.teamMembers.at(-1);
  assert.equal(member.name,'New <member>');
  assert.equal(member.role,'member','Member creation cannot silently assign an owner role');
  assert.match(team.renderTeam(h.ctx),/New &lt;member&gt;/);
  h.form('#team-role-form',{role:'admin'});
  h.action('team','team-save-role',{id:member.id});
  assert.equal(member.role,'admin');
  h.form('#team-agents-form',{agents:['a4','missing']});
  h.action('team','team-save-agents');
  assert.deepEqual(h.data.teamAgentIds,['a4']);
  h.state.teamTab='agents';
  assert.match(team.renderTeam(h.ctx),/data-id="a4"/);
  h.state.teamTab='activity';
  for(const locale of ['zh-CN','en']) {
    i18n.setLocale(locale);
    const html=team.renderTeam(h.ctx);
    assert.match(html,/New &lt;member&gt;/);
    assert.ok(!html.includes('team.activity.'),'Recorded actions have translated descriptions');
  }
  i18n.setLocale('zh-CN');
});

test('App action dispatch reaches ecosystem and project handlers and persists their changes',async()=>{
  const app=appHarness();
  await app.run("action({dataset:{action:'eco-add',platform:'feishu'}},{})");
  await app.run("action({dataset:{action:'eco-method',value:'feishu-app-bot'}},{})");
  app.form('#eco-wizard-form',{}, {dataset:{step:'2'}});
  await app.run("action({dataset:{action:'eco-next'}},{})");
  app.form('#eco-wizard-form',{assignedAgent:'a2'},{dataset:{step:'3'}});
  await app.run("action({dataset:{action:'eco-next'}},{})");
  app.form('#eco-wizard-form',{name:'App-level connector',capabilities:['message-receive','message-reply']},{dataset:{step:'4'}});
  await app.run("action({dataset:{action:'eco-save'}},{})");
  assert.equal(app.run('data.ecosystemBindings[0].assignedAgent'),'a2');
  app.form('#team-context-form',{context:'Team context through app action'});
  await app.run("action({dataset:{action:'team-save-context',id:'p1'}},{})");
  assert.equal(app.run("data.projects.find(p=>p.id==='p1').sharedContext"),'Team context through app action');
  const persisted=JSON.parse(app.values.get('workmates-prototype-v1'));
  assert.equal(persisted.ecosystemBindings[0].name,'App-level connector');
  assert.equal(persisted.projects.find(project=>project.id==='p1').sharedContext,'Team context through app action');
});

test('Channel task states render their own progress and failures without a completed template or unrelated file',()=>{
  const app=appHarness();
  const base={id:'channel-state-run',eventId:'event-state',bindingId:'binding-state',bindingName:'Feishu support',bindingSignature:'fixture',platform:'feishu',method:'feishu-app-bot',agentId:'a1',agentName:'我的智能伙伴',source:{sender:'Lin',conversation:'Project room',message:'事件状态核验',kind:'direct',mentioned:false},taskId:'channel-state-task',projectId:'p1',scenario:'success',stage:'received',executionStatus:'queued',deliveryStatus:'pending',executionAttempts:0,deliveryAttempts:0,history:[],createdAt:1,resultText:'',errorKey:'',fileId:null};
  app.context.channelFixture=base;
  app.run("data.channelRuns=[structuredClone(channelFixture)];data.tasks.unshift({id:'channel-state-task',name:'事件状态核验',prompt:'事件状态核验',agent:'a1',project:'p1',date:'Today',kind:'channel',channelRunId:'channel-state-run',status:'running'});state.page='task';state.task='channel-state-task'");
  for(const locale of ['zh-CN','en']) {
    i18n.setLocale(locale);
    for(const stage of ['received','running','execution_failed','interrupted','cancelled']) {
      app.run(`data.channelRuns[0].stage=${JSON.stringify(stage)};data.channelRuns[0].executionStatus=${JSON.stringify(stage==='received'?'queued':stage==='execution_failed'?'failed':stage)};data.tasks[0].status=${JSON.stringify(['received','running'].includes(stage)?'running':'failed')};render()`);
      const html=app.html();
      assert.ok(!html.includes(i18n.t('chat.completed')),`${locale}/${stage}: no ordinary completed response`);
      assert.ok(!html.includes('data-action="open-file" data-id="f1"'),`${locale}/${stage}: no unrelated default artifact`);
      assert.match(html,/Project room/);
      assert.ok(!html.includes('id="task-prompt"'),'A follow-up cannot bypass the channel source and route');
      assert.ok(!/undefined|\[object Object\]/.test(html));
    }
  }
  app.run("state.page='project';state.project='p1';state.projectTab='tasks';data.tasks[0].status='failed';render()");
  assert.ok(app.html().includes(i18n.t('project.needsAttention'))||/需处理|Needs attention|is-attention/.test(app.html()),'Failed channel work has an attention state in the project');
  i18n.setLocale('zh-CN');
});

test('Application startup recovers pending channel runs without the ordinary running-to-done migration',()=>{
  const saved=structuredClone(initialData);
  saved.channelRuns=[{id:'recover-run',eventId:'recover-event',bindingId:'b1',bindingName:'Saved channel',bindingSignature:'fixture',platform:'feishu',method:'feishu-app-bot',agentId:'a1',agentName:'我的智能伙伴',source:{sender:'Lin',conversation:'Saved room',message:'Refresh pending work',kind:'direct',mentioned:false},taskId:'recover-task',projectId:'',scenario:'success',stage:'running',executionStatus:'running',deliveryStatus:'pending',executionAttempts:1,deliveryAttempts:0,history:[],createdAt:1,resultText:'',errorKey:'',fileId:null}];
  saved.tasks.unshift({id:'recover-task',name:'Refresh pending work',prompt:'Refresh pending work',agent:'a1',project:'',date:'Today',kind:'channel',channelRunId:'recover-run',status:'running'});
  const app=appHarness({saved,hash:'#task/recover-task'});
  assert.equal(app.run('taskBy("recover-task").status'),'failed');
  assert.equal(app.run('data.channelRuns[0].executionStatus'),'interrupted');
  assert.notEqual(app.run('data.channelRuns[0].deliveryStatus'),'delivered');
  assert.ok(!app.html().includes(i18n.t('chat.completed')));
});
