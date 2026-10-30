import test from 'node:test';
import assert from 'node:assert/strict';
import { ensureTeamData, renderTeam, handleTeamAction } from '../dist/team.js';
import { isDescendant } from '../dist/saas.js';
import { initialData } from '../dist/data.js';
import { t, setLocale, messages } from '../dist/i18n.js';
const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function harness() {
  const data=structuredClone(initialData);ensureTeamData(data);
  const forms=new Map(), effects={saves:0,toasts:[],modal:null};
  globalThis.document={querySelector:key=>forms.get(key)};
  globalThis.FormData=class {constructor(form){this.values=form.values;}get(key){return this.values[key]??null;}};
  const ctx={data,state:{teamTab:'organization'},escape,icon:()=>'',avatar:()=>'',persist:()=>effects.saves++,closeOverlay(){},render(){},toast:m=>effects.toasts.push(m),modal:(title,body,footer)=>effects.modal={title,body,footer}};
  return {data,ctx,effects,form:(key,values)=>forms.set(key,{values,reportValidity:()=>true}),action:(name,id)=>handleTeamAction(name,{dataset:{id}},ctx)};
}
test('SaaS initialization preserves legacy members and business data and is idempotent',()=>{
  const h=harness(),snapshot=structuredClone(h.data);ensureTeamData(h.data);
  assert.deepEqual(h.data,snapshot);assert.equal(h.data.enterprise.id,'wx-demo');
  assert.ok(h.data.teamMembers.every(m=>m.status==='active'&&m.departmentId===''));
  assert.deepEqual(h.data.tasks,initialData.tasks);
});
test('Department hierarchy rejects cycles, duplicate siblings, and deleting occupied nodes',()=>{
  const h=harness();h.data.departments=[{id:'a',name:'A',parentId:''},{id:'b',name:'B',parentId:'a'}];
  assert.ok(isDescendant(h.data,'b','a'));
  h.form('#saas-department-form',{name:'A',parentId:'b'});h.action('saas-save-department','a');assert.equal(h.effects.saves,0);
  h.form('#saas-department-form',{name:'a',parentId:''});h.action('saas-save-department');assert.equal(h.effects.saves,0);
  h.action('saas-delete-department','a');assert.equal(h.data.departments.length,2);
  h.data.teamMembers[1].departmentId='b';h.action('saas-delete-department','b');assert.equal(h.data.departments.length,2);
  h.data.teamMembers[1].departmentId='';h.action('saas-delete-department','b');assert.equal(h.data.departments.length,1);
  h.form('#saas-department-form',{name:'C',parentId:'a'});h.action('saas-save-department');assert.equal(h.data.departments.at(-1).name,'C');
});
test('Member administration validates department, protects owner and persists normal member changes',()=>{
  const h=harness();h.data.departments=[{id:'a',name:'A',parentId:''}];
  h.form('#saas-member-form',{name:'Lin',departmentId:'missing',role:'admin',status:'disabled'});h.action('saas-save-member','m2');assert.equal(h.effects.saves,0);
  h.form('#saas-member-form',{name:'Lin',departmentId:'a',role:'member',status:'disabled'});h.action('saas-save-member','m2');
  assert.equal(h.data.teamMembers[1].departmentId,'a');assert.equal(h.data.teamMembers[1].status,'disabled');
  h.form('#saas-member-form',{name:'Alex',departmentId:'a',role:'member',status:'disabled'});h.action('saas-save-member','m1');
  assert.equal(h.data.teamMembers[0].role,'owner');assert.equal(h.data.teamMembers[0].status,'active');
  h.data=JSON.parse(JSON.stringify(h.data));ensureTeamData(h.data);assert.equal(h.data.teamMembers[1].status,'disabled');
});
test('Enterprise name and bilingual organization/role screens escape user content and disclose prototype scope',()=>{
  const h=harness();h.form('#saas-tenant-form',{name:'<script>evil</script>'});h.action('saas-save-tenant');
  for(const locale of ['zh-CN','en']){
    setLocale(locale);
    for(const tab of ['members','organization','roles']){
      h.ctx.state.teamTab=tab;const html=renderTeam(h.ctx);
      assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);
      assert.ok(html.includes(t('saas.boundary')));assert.doesNotMatch(html,/saas\.[a-zA-Z]/);
    }
  }
  for(const [key,values] of Object.entries(messages).filter(([key])=>key.startsWith('saas.')))assert.ok(values.length===2&&values.every(Boolean),key);
  setLocale('zh-CN');
});
