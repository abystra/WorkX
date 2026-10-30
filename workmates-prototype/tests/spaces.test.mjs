import test from 'node:test';
import assert from 'node:assert/strict';
import { initialData } from '../dist/data.js';
import { createSpacesRoot, createOrganization, switchSpace, normalizeSpace, inviteMembers, transitionInvitation, saveConnectionMetadata, updateResourceSharing, resourceCollections } from '../dist/spaces-model.js';
const setup=()=>createSpacesRoot(null,structuredClone(initialData));

test('Legacy work migrates only to the organization; personal workspace is unique and empty',()=>{
  const legacy=structuredClone(initialData);legacy.projects[0].name='Preserve <work>';legacy.ecosystemBindings=[{id:'legacy-binding',name:'Legacy'}];legacy.ecosystemSchemaVersion=2;
  const root=createSpacesRoot(null,legacy),org=root.spaces.find(s=>s.type==='organization'),personal=root.spaces.find(s=>s.type==='personal');
  assert.equal(org.data.projects[0].name,'Preserve <work>');assert.equal(org.data.tasks.length,legacy.tasks.length);
  assert.equal(org.data.ecosystemBindings[0].id,'legacy-binding');assert.equal(personal.data.ecosystemBindings.length,0);
  for(const c of ['tasks','projects','library','automations','connections','invitations'])assert.equal(personal.data[c].length,0,c);
  assert.equal(personal.data.teamMembers.length,1);assert.equal(personal.data.teamMembers[0].role,'owner');
  const snapshot=JSON.stringify(root);assert.equal(JSON.stringify(createSpacesRoot(root,null)),snapshot);
  assert.equal(root.spaces.filter(s=>s.type==='personal').length,1);assert.equal(legacy.tasks[0].tenantId,undefined,'Input is not mutated');
});
test('Organization creation rejects empty/duplicate names and never migrates resources or credentials',()=>{
  const root=setup(),personal=switchSpace(root,'personal-alex');
  saveConnectionMetadata(personal,{name:'Mine',provider:'mcp',authMode:'oauth',ownerScope:'member'});
  assert.equal(createOrganization(root,' ').error,'spaces.invalidName');assert.equal(createOrganization(root,'workx').error,'spaces.duplicateName');
  const result=createOrganization(root,'Design <Team>');assert.equal(result.space.type,'organization');assert.equal(result.space.data.teamMembers.length,1);
  assert.equal(result.space.data.connections.length,0);assert.equal(personal.connections.length,1);assert.equal(result.space.data.projects.length,0);
  assert.notEqual(result.space.data.agents,personal.agents);assert.equal(switchSpace(root,'missing'),null);assert.equal(root.activeSpaceId,'personal-alex');
});
test('All resources, bindings, invitations and connections carry their owning tenant through hydration',()=>{
  const root=setup();for(const s of root.spaces){normalizeSpace(s);for(const c of resourceCollections)for(const item of s.data[c])assert.equal(item.tenantId,s.id);}
  const reloaded=createSpacesRoot(JSON.parse(JSON.stringify(root)),null);assert.equal(reloaded.activeSpaceId,root.activeSpaceId);
  const personal=switchSpace(reloaded,'personal-alex');assert.equal(personal.spaceType,'personal');assert.equal(personal.enterprise.id,'personal-alex');
});
test('Invitations validate atomically, deduplicate normalized addresses and grant membership only on acceptance',()=>{
  const data=setup().spaces.find(s=>s.type==='organization').data;
  assert.equal(inviteMembers(data,{emails:'valid@example.com, bad',role:'member'},100).error,'spaces.invalidEmail');assert.equal(data.invitations.length,0);
  assert.equal(inviteMembers(data,{emails:'one@@example.com',role:'member'},100).error,'spaces.invalidEmail');
  const result=inviteMembers(data,{emails:'ONE@example.com, one@example.com; two@example.com',role:'admin'},100);
  assert.equal(result.invitations.length,2);assert.equal(data.teamMembers.length,3);
  assert.equal(inviteMembers(data,{emails:'one@example.com',role:'member'},100).error,'spaces.duplicateInvitation');
  const accepted=transitionInvitation(data,result.invitations[0].id,'accept',200);assert.equal(accepted.member.email,'one@example.com');assert.equal(accepted.member.role,'admin');assert.equal(accepted.member.tenantId,data.tenantId);
  assert.equal(data.teamMembers.length,4);assert.equal(transitionInvitation(data,result.invitations[0].id,'accept',201).error,'spaces.invitationClosed');
  transitionInvitation(data,result.invitations[1].id,'cancel',200);assert.equal(transitionInvitation(data,result.invitations[1].id,'accept',201).error,'spaces.invitationClosed');
});
test('Expired invitations and personal/non-admin member invitations cannot create memberships',()=>{
  const root=setup(),data=root.spaces.find(s=>s.type==='organization').data;
  const invitation=inviteMembers(data,{emails:'expired@example.com',role:'member'},0).invitations[0];
  assert.equal(transitionInvitation(data,invitation.id,'accept',8*86400000).error,'spaces.invitationClosed');assert.equal(invitation.status,'expired');
  const personal=switchSpace(root,'personal-alex');assert.equal(inviteMembers(personal,{emails:'no@example.com',role:'member'}).error,'spaces.noPermission');
  data.teamMembers[0].role='member';assert.equal(inviteMembers(data,{emails:'no@example.com',role:'member'}).error,'spaces.noPermission');
});
test('Connection metadata is tenant scoped and allowlisted, with no raw secret or authentication claim',()=>{
  const root=setup(),personal=switchSpace(root,'personal-alex');
  const fields={name:'My MCP',provider:'mcp',authMode:'oauth',ownerScope:'member',agentIds:['a1','a2'],token:'NEVER_SAVE',env:'NEVER_SAVE',secret:'NEVER_SAVE'};
  const result=saveConnectionMetadata(personal,fields);assert.equal(result.connection.status,'needs_auth');assert.equal(result.connection.tenantId,'personal-alex');assert.equal(result.connection.ownerId,'m1');
  assert.ok(!JSON.stringify(root).includes('NEVER_SAVE'));assert.equal(saveConnectionMetadata(personal,{...fields,ownerScope:'space'}).error,'spaces.noPermission');
  assert.equal(saveConnectionMetadata(personal,{...fields,agentIds:['foreign']}).error,'spaces.invalidConnection');
  const org=switchSpace(root,'wx-demo');assert.equal(org.connections.length,0);const shared=saveConnectionMetadata(org,{...fields,ownerScope:'space'}).connection;assert.equal(shared.ownerId,'wx-demo');
  assert.equal(personal.connections.length,1);assert.equal(org.connections.length,1);assert.notEqual(org.connections,personal.connections);
});
test('Resource sharing stays within its tenant, checks member/project references, and ignores department inheritance',()=>{
  const root=setup(),data=root.spaces.find(s=>s.type==='organization').data,resource=data.library[0];
  const original=structuredClone(resource);assert.equal(updateResourceSharing(data,'library',resource.id,{visibility:'selected',memberIds:['foreign']}).error,'spaces.invalidSharing');assert.deepEqual(resource,original);
  assert.equal(updateResourceSharing(data,'library',resource.id,{visibility:'project',projectId:'foreign'}).error,'spaces.invalidSharing');
  updateResourceSharing(data,'library',resource.id,{visibility:'selected',memberIds:['m2']});assert.equal(resource.visibility,'selected');assert.deepEqual(resource.sharedMemberIds,['m2']);
  data.departments.push({id:'d1',name:'Design'});data.teamMembers[1].departmentId='d1';assert.deepEqual(resource.sharedMemberIds,['m2']);
  updateResourceSharing(data,'library',resource.id,{visibility:'project',projectId:'p1'});assert.equal(resource.sharingProjectId,'p1');assert.deepEqual(resource.sharedMemberIds,[]);
  const personal=switchSpace(root,'personal-alex');personal.library.push({id:'f1',name:'Private',ownerId:'m1'});normalizeSpace(root.spaces[0]);
  updateResourceSharing(personal,'library','f1',{visibility:'space'});assert.equal(personal.library[0].visibility,'private');assert.equal(resource.visibility,'project');
});

test('Changing the task assignee does not transfer resource ownership or sharing authority',()=>{
  const root=setup(),space=root.spaces.find(s=>s.type==='organization'),task=space.data.tasks[0];
  assert.equal(task.resourceOwnerId,'m1');task.ownerId='m2';normalizeSpace(space);
  assert.equal(task.ownerId,'m2');assert.equal(task.resourceOwnerId,'m1');
  const result=updateResourceSharing(space.data,'tasks',task.id,{visibility:'selected',memberIds:['m3']});
  assert.equal(result.resource.resourceOwnerId,'m1');assert.equal(task.ownerId,'m2');assert.deepEqual(task.sharedMemberIds,['m3']);
});
