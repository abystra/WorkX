// Domain rules ported from the prototype's spaces-model.js. In production these live in the FastAPI
// control plane (tenancy, invitations, sharing, connections); keeping them here lets the development
// adapter return the same validation errors (i18n keys) the UI already knows how to show.
import type { Root, Space, SpaceData } from './store';

export const resourceCollections = ['projects', 'tasks', 'library', 'agents', 'automations'] as const;
export const uid = (prefix: string) => prefix + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

export const canManageSpace = (data: SpaceData) =>
  data.spaceType === 'organization' &&
  data.teamMembers?.some((m: any) => m.id === 'm1' && m.status === 'active' && ['owner', 'admin'].includes(m.role));

function emptyData(seedAgents: any[], name: string, type: 'personal' | 'organization'): SpaceData {
  return {
    agents: structuredClone(seedAgents).map((a: any) => ({ ...a, tasks: 0, tag: type === 'personal' ? 'Personal' : a.tag })),
    tasks: [], projects: [], library: [], automations: [],
    teamMembers: [{ id: 'm1', userId: 'u-alex', name: 'Alex', email: 'alex@example.com', role: 'owner', status: 'active', departmentId: '' }],
    teamAgentIds: [], teamActivity: [], departments: [], enterprise: { id: '', name }, hideQuick: false, proactive: false,
    ecosystemBindings: [], ecosystemSchemaVersion: 2, channelRuns: [], scenarioDrafts: [], invitations: [], connections: [],
    tenantId: '', spaceType: type,
  };
}

/** Same normalization the prototype applies on every save. */
export function normalizeSpace(space: Space) {
  const data = space.data;
  data.tenantId = space.id;
  data.spaceType = space.type;
  data.enterprise = { ...data.enterprise, id: space.id, name: space.name };
  for (const key of ['invitations', 'connections', 'departments', 'teamActivity', 'teamAgentIds', 'ecosystemBindings', 'channelRuns', 'scenarioDrafts', 'knowledgeSources']) data[key] ||= [];
  if (space.type === 'personal') {
    data.teamMembers = data.teamMembers.filter((m: any) => m.id === 'm1');
    data.invitations = [];
    data.departments = [];
  }
  for (const collection of resourceCollections) {
    for (const record of data[collection] || []) {
      record.tenantId = space.id;
      record.resourceOwnerId ||= 'm1';
      record.visibility ||= space.type === 'personal' ? 'private' : collection === 'projects' || record.project ? 'project' : 'private';
      if (space.type === 'personal') { record.visibility = 'private'; record.sharedMemberIds = []; }
    }
  }
  for (const project of data.projects) {
    project.memberIds ||= data.teamMembers.slice(0, 1).map((m: any) => m.id);
    project.agentIds ||= data.agents.slice(0, 1).map((a: any) => a.id);
    if (typeof project.sharedContext !== 'string') project.sharedContext = '';
    project.tasks = data.tasks.filter((t: any) => t.project === project.id && !t.archived).length;
  }
}

/** `seedAgents` are the built-in example workmates (from the seed, never the user's edited copies). */
export function createOrganization(root: Root, rawName: unknown, seedAgents: any[]) {
  const name = String(rawName || '').trim();
  if (!name || name.length > 80) return { error: 'spaces.invalidName' };
  if (root.spaces.some(s => s.type === 'organization' && s.name.toLocaleLowerCase() === name.toLocaleLowerCase())) return { error: 'spaces.duplicateName' };
  const space: Space = { id: uid('org-'), type: 'organization', name, data: emptyData(seedAgents, name, 'organization') };
  normalizeSpace(space);
  space.data.teamMembers[0].name = root.user.name;
  space.data.teamActivity.unshift({ id: 'ev-created', at: new Date().toISOString(), spaceEvent: 'created', tenantId: space.id });
  root.spaces.push(space);
  return { space };
}

export function expireInvitations(data: SpaceData, now = Date.now()) {
  for (const invitation of data.invitations || []) if (invitation.status === 'pending' && invitation.expiresAt <= now) invitation.status = 'expired';
}

export function inviteMembers(data: SpaceData, input: { emails?: string; role?: string }, now = Date.now()) {
  if (!canManageSpace(data)) return { error: 'spaces.noPermission' };
  const emails = [...new Set(String(input.emails || '').split(/[\s,;，；]+/).filter(Boolean).map(e => e.toLowerCase()))];
  if (!emails.length || emails.length > 20 || emails.some(e => e.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e))) return { error: 'spaces.invalidEmail' };
  if (!['member', 'admin'].includes(String(input.role))) return { error: 'spaces.invalidRole' };
  expireInvitations(data, now);
  if (emails.some(email => data.teamMembers.some((m: any) => m.email?.toLowerCase() === email) || data.invitations.some((i: any) => i.email === email && i.status === 'pending'))) return { error: 'spaces.duplicateInvitation' };
  const invitations = emails.map(email => ({ id: uid('inv-'), tenantId: data.tenantId, email, role: input.role, status: 'pending', createdAt: now, expiresAt: now + 7 * 86400000 }));
  data.invitations.push(...invitations);
  return { invitations };
}

export function transitionInvitation(data: SpaceData, id: string, action: 'accept' | 'cancel', now = Date.now()) {
  if (!canManageSpace(data)) return { error: 'spaces.noPermission' };
  expireInvitations(data, now);
  const invitation = data.invitations.find((i: any) => i.id === id);
  if (!invitation || invitation.status !== 'pending') return { error: 'spaces.invitationClosed' };
  if (action === 'cancel') { invitation.status = 'cancelled'; return { invitation }; }
  if (data.teamMembers.some((m: any) => m.email?.toLowerCase() === invitation.email)) return { error: 'spaces.duplicateInvitation' };
  const member = { id: uid('m-'), tenantId: data.tenantId, email: invitation.email, name: invitation.email.split('@')[0], role: invitation.role, status: 'active', departmentId: '' };
  data.teamMembers.push(member);
  invitation.status = 'accepted';
  return { member };
}

export function saveConnectionMetadata(data: SpaceData, input: any) {
  const name = String(input.name || '').trim();
  if (!name || name.length > 80 || !['feishu', 'wecom', 'mcp', 'skill', 'api'].includes(input.provider) || !['none', 'static', 'oauth', 'exchange', 'envfile'].includes(input.authMode)) return { error: 'spaces.invalidConnection' };
  if (!['member', 'space'].includes(input.ownerScope) || (input.ownerScope === 'space' && !canManageSpace(data))) return { error: 'spaces.noPermission' };
  const agentIds = [...new Set<string>(input.agentIds || [])];
  if (agentIds.some(id => !data.agents.some((a: any) => a.id === id))) return { error: 'spaces.invalidConnection' };
  // Explicit allow-list: never persist secrets, env contents, authorization links or tokens.
  const connection = { id: uid('con-'), tenantId: data.tenantId, name, provider: input.provider, authMode: input.authMode, ownerScope: input.ownerScope, ownerId: input.ownerScope === 'member' ? 'm1' : data.tenantId, agentIds, status: input.authMode === 'none' ? 'no_auth' : 'needs_auth', enabled: true, usageClass: 'tool' };
  data.connections.push(connection);
  return { connection };
}

export function updateResourceSharing(data: SpaceData, collection: string, id: string, input: any) {
  const resource = (resourceCollections as readonly string[]).includes(collection) && data[collection].find((r: any) => r.id === id);
  if (!resource || resource.resourceOwnerId !== 'm1') return { error: 'spaces.noPermission' };
  const visibility = data.spaceType === 'personal' ? 'private' : input.visibility;
  if (!['private', 'selected', 'project', 'space'].includes(visibility)) return { error: 'spaces.invalidSharing' };
  const members = [...new Set<string>(input.memberIds || [])];
  if (visibility === 'selected' && (!members.length || members.some(mid => !data.teamMembers.some((m: any) => m.id === mid && m.status === 'active')))) return { error: 'spaces.invalidSharing' };
  const projectId = collection === 'projects' ? resource.id : resource.project || input.projectId;
  if (visibility === 'project' && !data.projects.some((p: any) => p.id === projectId)) return { error: 'spaces.invalidSharing' };
  Object.assign(resource, { visibility, sharedMemberIds: visibility === 'selected' ? members : [], sharingProjectId: visibility === 'project' ? projectId : '' });
  return { resource };
}

export function recordSpaceEvent(data: SpaceData, type: string) {
  data.teamActivity.unshift({ id: 'ev-' + Date.now() + Math.random(), at: new Date().toISOString(), spaceEvent: type, tenantId: data.tenantId });
  data.teamActivity = data.teamActivity.slice(0, 80);
}

export function recordTeamEvent(data: SpaceData, type: string, fields: Record<string, unknown> = {}) {
  data.teamActivity.unshift({ id: uid('ev'), type, at: new Date().toISOString(), ...fields });
  data.teamActivity = data.teamActivity.slice(0, 80);
}
