import { initialData } from './data.js';
import { ensureTeamData } from './team.js';
import { ensureEcosystemData } from './ecosystem-model.js';
import { ensureChannelData } from './channel-model.js';

export const SPACES_STORAGE_KEY = 'workx-spaces-v1';
export const resourceCollections = ['projects','tasks','library','agents','automations'];
const uid = prefix => prefix + Date.now().toString(36) + Math.random().toString(36).slice(2,8);
const clone = value => structuredClone(value);
export const spaceBy = (root,id=root.activeSpaceId) => root.spaces.find(space=>space.id===id);
export const spaceName = (space,personalLabel) => space.type==='personal' ? personalLabel : space.name;
export const canManageSpace = data => data.spaceType==='organization' && data.teamMembers?.some(m=>m.id==='m1'&&m.status==='active'&&['owner','admin'].includes(m.role));

function emptyData(name,type) {
  return {agents:clone(initialData.agents).map(a=>({...a,tasks:0,tag:type==='personal'?'Personal':a.tag})),tasks:[],projects:[],library:[],automations:[],teamMembers:[{id:'m1',userId:'u-alex',name:'Alex',email:'alex@example.com',role:'owner',status:'active',departmentId:''}],teamAgentIds:[],teamActivity:[],departments:[],enterprise:{name},hideQuick:false,proactive:false,ecosystemBindings:[],ecosystemSchemaVersion:2,channelRuns:[],scenarioDrafts:[],invitations:[],connections:[]};
}
export function normalizeSpace(space) {
  const data=space.data;
  data.tenantId=space.id;data.spaceType=space.type;
  data.enterprise={...data.enterprise,id:space.id,name:space.name};
  ensureTeamData(data);ensureEcosystemData(data);ensureChannelData(data);
  data.invitations ||= [];data.connections ||= [];
  if(space.type==='personal') {
    data.teamMembers=data.teamMembers.filter(m=>m.id==='m1');
    data.teamMembers[0] ||= {id:'m1',name:'Alex',role:'owner',status:'active',departmentId:''};
    data.teamMembers[0].role='owner';data.teamMembers[0].status='active';
    data.invitations=[];data.departments=[];
  }
  for(const collection of [...resourceCollections,'teamMembers','ecosystemBindings','channelRuns','scenarioDrafts','connections','invitations','teamActivity','departments']) {
    for(const record of data[collection]||[]) {
      record.tenantId=space.id;
      if(resourceCollections.includes(collection)) {
        record.resourceOwnerId ||= 'm1';
        record.visibility ||= space.type==='personal'?'private':collection==='projects'||record.project?'project':collection==='agents'&&data.teamAgentIds.includes(record.id)?'space':'private';
        if(space.type==='personal'){record.visibility='private';record.sharedMemberIds=[];}
      }
    }
  }
  // Legacy display fields become member metadata, never real authentication identities.
  for(const member of data.teamMembers){member.email ||= member.id==='m1'?'alex@example.com':'';}
  return data;
}
export function createSpacesRoot(saved,legacy) {
  if(saved?.schemaVersion===1&&Array.isArray(saved.spaces)&&saved.spaces.some(s=>s.id==='personal-alex'&&s.type==='personal')&&saved.spaces.every(s=>s.id&&s.data&&Array.isArray(s.data.agents)&&Array.isArray(s.data.tasks))) {
    const root=saved;root.user ||= {id:'u-alex',name:'Alex',email:'alex@example.com',notifications:true};
    if(!spaceBy(root))root.activeSpaceId='personal-alex';
    root.spaces.forEach(normalizeSpace);return root;
  }
  const data=legacy&&Array.isArray(legacy.agents)&&Array.isArray(legacy.tasks)?{...clone(initialData),...clone(legacy)}:clone(initialData);
  const organization={id:data.enterprise?.id||'wx-demo',type:'organization',name:data.enterprise?.name||'WorkX',data};
  // The personal space starts empty. Existing records remain exclusively in the legacy organization.
  const personal={id:'personal-alex',type:'personal',name:'Alex',data:emptyData('Alex','personal')};
  const root={schemaVersion:1,user:{id:'u-alex',name:'Alex',email:'alex@example.com',notifications:true},activeSpaceId:organization.id,spaces:[personal,organization]};
  root.spaces.forEach(normalizeSpace);return root;
}
export function createOrganization(root,name) {
  name=String(name||'').trim();
  if(!name||name.length>80)return {error:'spaces.invalidName'};
  if(root.spaces.some(s=>s.type==='organization'&&s.name.toLocaleLowerCase()===name.toLocaleLowerCase()))return {error:'spaces.duplicateName'};
  const space={id:uid('org-'),type:'organization',name,data:emptyData(name,'organization')};
  normalizeSpace(space);space.data.teamMembers[0].name=root.user.name;root.spaces.push(space);
  return {space};
}
export function switchSpace(root,id) {
  const space=spaceBy(root,id);if(!space)return null;
  root.activeSpaceId=id;return normalizeSpace(space);
}
export function inviteMembers(data,input,now=Date.now()) {
  if(!canManageSpace(data))return {error:'spaces.noPermission'};
  const emails=[...new Set(String(input.emails||'').split(/[\s,;，；]+/).filter(Boolean).map(email=>email.toLowerCase()))];
  if(!emails.length||emails.length>20||emails.some(email=>email.length>254||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)))return {error:'spaces.invalidEmail'};
  if(!['member','admin'].includes(input.role))return {error:'spaces.invalidRole'};
  expireInvitations(data,now);
  if(emails.some(email=>data.teamMembers.some(m=>m.email?.toLowerCase()===email)||data.invitations.some(i=>i.email===email&&i.status==='pending')))return {error:'spaces.duplicateInvitation'};
  const invitations=emails.map(email=>({id:uid('inv-'),tenantId:data.tenantId,email,role:input.role,status:'pending',createdAt:now,expiresAt:now+7*86400000}));
  data.invitations.push(...invitations);return {invitations};
}
export function expireInvitations(data,now=Date.now()) {for(const invitation of data.invitations||[])if(invitation.status==='pending'&&invitation.expiresAt<=now)invitation.status='expired';}
export function transitionInvitation(data,id,action,now=Date.now()) {
  if(!canManageSpace(data))return {error:'spaces.noPermission'};
  expireInvitations(data,now);const invitation=data.invitations.find(i=>i.id===id);
  if(!invitation||invitation.status!=='pending')return {error:'spaces.invitationClosed'};
  if(action==='cancel'){invitation.status='cancelled';return {invitation};}
  if(action!=='accept')return {error:'spaces.invitationClosed'};
  if(data.teamMembers.some(m=>m.email?.toLowerCase()===invitation.email))return {error:'spaces.duplicateInvitation'};
  const member={id:uid('m-'),tenantId:data.tenantId,email:invitation.email,name:invitation.email.split('@')[0],role:invitation.role,status:'active',departmentId:''};
  data.teamMembers.push(member);invitation.status='accepted';return {member};
}
export function saveConnectionMetadata(data,input) {
  const name=String(input.name||'').trim();
  if(!name||name.length>80||!['feishu','wecom','mcp','skill','api'].includes(input.provider)||!['none','static','oauth','exchange','envfile'].includes(input.authMode))return {error:'spaces.invalidConnection'};
  if(!['member','space'].includes(input.ownerScope)||(input.ownerScope==='space'&&!canManageSpace(data)))return {error:'spaces.noPermission'};
  const agentIds=[...new Set(input.agentIds||[])];
  if(agentIds.some(id=>!data.agents.some(a=>a.id===id)))return {error:'spaces.invalidConnection'};
  // Explicit allowlist: never persist secrets, env contents, authorization links or tokens.
  const connection={id:uid('con-'),tenantId:data.tenantId,name,provider:input.provider,authMode:input.authMode,ownerScope:input.ownerScope,ownerId:input.ownerScope==='member'?'m1':data.tenantId,agentIds,status:input.authMode==='none'?'no_auth':'needs_auth',enabled:true,usageClass:'tool'};
  data.connections.push(connection);return {connection};
}
export function updateResourceSharing(data,collection,id,input) {
  const resource=resourceCollections.includes(collection)&&data[collection].find(r=>r.id===id);
  if(!resource||resource.resourceOwnerId!=='m1')return {error:'spaces.noPermission'};
  const visibility=data.spaceType==='personal'?'private':input.visibility;
  if(!['private','selected','project','space'].includes(visibility))return {error:'spaces.invalidSharing'};
  const members=[...new Set(input.memberIds||[])];
  if(visibility==='selected'&&(!members.length||members.some(id=>!data.teamMembers.some(m=>m.id===id&&m.status==='active'))))return {error:'spaces.invalidSharing'};
  const projectId=collection==='projects'?resource.id:resource.project||input.projectId;
  if(visibility==='project'&&!data.projects.some(p=>p.id===projectId))return {error:'spaces.invalidSharing'};
  Object.assign(resource,{visibility,sharedMemberIds:visibility==='selected'?members:[],sharingProjectId:visibility==='project'?projectId:''});
  return {resource};
}
