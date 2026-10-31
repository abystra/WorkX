// Ported verbatim from workmates-prototype/dist/connection-model.js (pure; never authenticates).
import { methodBy } from './ecosystem-model.js';

// The prototype validates shapes and records setup intent; it never authenticates.
export const CONNECTION_DOCS = {
  feishuBot:'https://open.feishu.cn/document/client-docs/bot-v3/bot-overview',
  feishuEvents:'https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide/event-subscriptions',
  feishuWebhook:'https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot?lang=zh-CN',
  feishuApi:'https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/authentication-management/access-token/tenant_access_token',
  wecomAi:'https://cloud.tencent.com/document/product/1759/121473',
  wecomApp:'https://cloud.tencent.com/document/product/1759/119175',
  wecomWebhook:'https://cloud.tencent.com/document/product/248/50413'
};
const field=(id,required=true,sensitive=false,options)=>({id,label:'conn.field.'+id,hint:'conn.hint.'+id,required,sensitive,type:options?'select':'text',...(options?{options}:{} )});
const step=(id,url)=>({id,title:'conn.auth.'+id,body:'conn.auth.'+id+'Body',url});
const transports=[{value:'websocket',label:'conn.websocket'},{value:'callback',label:'conn.callback'}];
const signing=[{value:'none',label:'conn.signNone'},{value:'signature',label:'conn.signEnabled'}];
const trim=value=>typeof value==='string'?value.trim():'';
export function connectionSignature(binding) {
  return JSON.stringify([binding.platform,binding.method,binding.transport||'',binding.assignedAgent,[...(binding.capabilities||[])].sort()]);
}
export function connectionSpec(binding,params={}) {
  const docs=CONNECTION_DOCS, method=methodBy(binding.method);
  let fields=[],steps=[],docsUrl='',callback=false;
  const resources=(binding.capabilities||[]).some(id=>!['message-receive','message-reply','notification-send'].includes(id));
  if(binding.method==='feishu-app-bot') {
    docsUrl=docs.feishuBot;
    fields=[field('appId'),field('appSecret',true,true),field('transport',true,false,transports)];
    callback=params.transport==='callback';
    if(callback)fields.push(field('verificationToken',true,true),field('encryptKey',false,true));
    steps=[step('feishuBot',docsUrl),step('feishuScopes',docsUrl),step(callback?'feishuCallback':'feishuEvents',docs.feishuEvents),...(resources?[step('resources',docs.feishuApi)]:[]),step('feishuRelease',docsUrl)];
  } else if(binding.method==='feishu-api') {
    docsUrl=docs.feishuApi;fields=[field('appId'),field('appSecret',true,true)];
    steps=[step('feishuApp',docsUrl),step('feishuScopes',docsUrl),step('resources',docsUrl),step('feishuRelease',docs.feishuBot)];
  } else if(binding.method==='feishu-webhook') {
    docsUrl=docs.feishuWebhook;fields=[field('webhookUrl',true,true),field('signing',true,false,signing)];
    if(params.signing==='signature')fields.push(field('signingSecret',true,true));
    steps=[step('groupBot',docsUrl),step('feishuSecurity',docsUrl),step('notificationOnly',docsUrl)];
  } else if(binding.method==='wecom-ai-bot') {
    docsUrl=docs.wecomAi;
    callback=binding.transport==='callback';
    fields=callback?[field('botId',false),field('token',true,true),field('encodingAESKey',true,true)]:[field('botId'),field('botSecret',true,true)];
    steps=[step('wecomAi',docsUrl),step(callback?'wecomCallback':'wecomSocket',docsUrl),step('wecomVisibility',docsUrl),...(resources?[step('wecomTools',docsUrl)]:[])];
  } else if(binding.method==='wecom-app') {
    docsUrl=docs.wecomApp;callback=true;
    fields=[field('corpId'),field('agentId'),field('appSecret',true,true),field('token',true,true),field('encodingAESKey',true,true)];
    steps=[step('wecomApp',docsUrl),step('wecomCallback',docsUrl),step('wecomIp',docsUrl),step('wecomVisibility',docsUrl),...(resources?[step('wecomTools',docsUrl)]:[])];
  } else if(binding.method==='wecom-webhook') {
    docsUrl=docs.wecomWebhook;fields=[field('webhookUrl',true,true)];
    steps=[step('groupBot',docsUrl),step('wecomGroup',docsUrl),step('notificationOnly',docsUrl)];
  }
  return {fields,steps,docsUrl,...(callback?{callbackUrl:'https://workx.example.invalid/callback/'+encodeURIComponent(binding.platform)+'/'+encodeURIComponent(binding.id)}:{}),testStages:['parameters','credentials','permissions',method?.kind==='tools'?'tools':'channel']};
}
function defaultParameters(binding) {return binding.method==='feishu-app-bot'?{transport:'websocket'}:binding.method==='feishu-webhook'?{signing:'none'}:{};}
export function demoConnectionParams(binding,params={}) {
  const choices={...defaultParameters(binding),...params};
  const examples={appId:'cli_demo_workx',appSecret:'DEMO_ONLY_APP_SECRET',transport:choices.transport,verificationToken:'DemoVerifyToken',encryptKey:'DEMO_ONLY_ENCRYPT_KEY',signing:choices.signing,signingSecret:'DEMO_ONLY_SIGNING_SECRET',botId:'aib_demo_workx',botSecret:'DEMO_ONLY_BOT_SECRET',corpId:'ww_demo_workx',agentId:'1000002',token:'DemoToken123',encodingAESKey:'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopq',webhookUrl:binding.platform==='feishu'?'https://open.feishu.cn/open-apis/bot/v2/hook/DEMO-ONLY-NOT-A-REAL-KEY':'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=DEMO-ONLY-NOT-A-REAL-KEY'};
  return Object.fromEntries(connectionSpec(binding,choices).fields.map(item=>[item.id,examples[item.id]||'']));
}
export function validateConnection(binding,draft) {
  if(!methodBy(binding.method)||methodBy(binding.method).platform!==binding.platform)return [{field:'',key:'conn.invalidBinding'}];
  if(binding.method==='wecom-ai-bot'&&!['websocket','callback'].includes(binding.transport))return [{field:'',key:'conn.invalidTransport'}];
  const params=draft.params||{},errors=[];
  for(const item of connectionSpec(binding,params).fields) {
    const value=trim(params[item.id]);
    if(!value){if(item.required)errors.push({field:item.id,key:'conn.requiredField'});continue;}
    if(value.length>2048){errors.push({field:item.id,key:'conn.invalidFormat'});continue;}
    if(item.options&&!item.options.some(option=>option.value===value))errors.push({field:item.id,key:'conn.invalidChoice'});
    else if(item.id==='agentId'&&!/^\d+$/.test(value))errors.push({field:item.id,key:'conn.invalidAgentId'});
    else if(item.id==='encodingAESKey'&&!/^[A-Za-z0-9]{43}$/.test(value))errors.push({field:item.id,key:'conn.invalidAes'});
    else if(['appId','botId','corpId'].includes(item.id)&&!/^[-A-Za-z0-9_]+$/.test(value))errors.push({field:item.id,key:'conn.invalidIdentifier'});
    else if(item.id==='webhookUrl') {
      let valid=false;
      try {const url=new URL(value);valid=url.protocol==='https:'&&!url.username&&!url.password&&!url.port&&!url.hash&&(binding.platform==='feishu'?url.hostname==='open.feishu.cn'&&/^\/open-apis\/bot\/v2\/hook\/[^/]+$/.test(url.pathname):url.hostname==='qyapi.weixin.qq.com'&&url.pathname==='/cgi-bin/webhook/send'&&!!url.searchParams.get('key'));}catch{}
      if(!valid)errors.push({field:item.id,key:binding.platform==='feishu'?'conn.invalidFeishuWebhook':'conn.invalidWecomWebhook'});
    }
  }
  return errors;
}
// Persist only method-specific non-secret fields. Never retain a credential,
// webhook URL, arbitrary error text or values injected from an imported draft.
export function sanitizeConnection(binding,draft,testResult=draft.test) {
  const params={...defaultParameters(binding),...(draft.params||{})},spec=connectionSpec(binding,params);
  const parameters={};
  for(const item of spec.fields.filter(item=>!item.sensitive)) {
    const value=trim(params[item.id]);
    if(!value||value.length>200)continue;
    if(item.options&&!item.options.some(option=>option.value===value))continue;
    if(!item.options&&!/^[-A-Za-z0-9_]+$/.test(value))continue;
    parameters[item.id]=value;
  }
  const confirmed=spec.steps.map(item=>item.id).filter(id=>Array.isArray(draft.confirmed)&&draft.confirmed.includes(id));
  const outcomes=['success','credential_error','permission_error','timeout'];
  const test=testResult?.simulated===true&&outcomes.includes(testResult.outcome)&&Number.isFinite(testResult.at)?{status:testResult.outcome==='success'?'success':'error',outcome:testResult.outcome,at:testResult.at,simulated:true}:null;
  return {version:1,signature:connectionSignature(binding),parameters,confirmed,test};
}
export function initialConnectionDraft(binding) {
  const saved=binding.connection;
  if(!saved||saved.signature!==connectionSignature(binding))return {params:defaultParameters(binding),confirmed:[],test:null};
  const clean=sanitizeConnection(binding,{params:saved.parameters,confirmed:saved.confirmed,test:saved.test});
  return {params:{...defaultParameters(binding),...clean.parameters},confirmed:clean.confirmed,test:clean.test};
}
export function reconcileConnection(previous,next) {
  if(previous?.connection&&connectionSignature(previous)===connectionSignature(next)) {
    const draft=initialConnectionDraft(previous);
    next.connection=sanitizeConnection(next,draft,draft.test);
  } else delete next.connection;
  return next;
}
