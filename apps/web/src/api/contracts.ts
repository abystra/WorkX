// View-model contracts the web app consumes. Paths follow docs/architecture/11-DATA-API-EVENTS.md
// (`/api/v1/me`, `/api/v1/tenants/{tenant_id}/...`). Field names are the UI's camelCase view models;
// when the FastAPI backend exists, its generated OpenAPI types replace this file and the HTTP transport
// maps snake_case responses (see apps/web/docs/BACKEND-INTEGRATION.md).

export type TenantType = 'personal' | 'organization';
export type Role = 'owner' | 'admin' | 'member';
export type Visibility = 'private' | 'selected' | 'project' | 'space';

export interface User {
  id: string;
  name: string;
  email: string;
  notifications: boolean;
}

export interface Me {
  user: User;
  lastTenantId: string;
}

export interface TenantSummary {
  id: string;
  /** The signed-in user's own membership in this workspace. */
  membershipId: string;
  slug: string;
  type: TenantType;
  name: string;
  role: Role;
}

export interface TenantDetail extends TenantSummary {
  settings: { hideQuick: boolean; proactive: boolean; notificationsRead: boolean };
}

export interface Resource {
  id: string;
  tenantId?: string;
  resourceOwnerId?: string;
  visibility?: Visibility;
  sharedMemberIds?: string[];
  sharingProjectId?: string;
}

export interface Agent extends Resource {
  name: string;
  description: string;
  tag: string;
  avatar: number;
  tasks: number;
  skills: number;
  instructions?: string;
  context?: string;
  extraSkills?: string[];
  /** Knowledge sources the workmate may search and cite (agent_versions.knowledge_source_ids). */
  knowledgeSourceIds?: string[];
}

/**
 * A Library file made searchable for workmates (docs/architecture/07-KNOWLEDGE.md). `processing` covers
 * upload checks, parsing, chunking and embedding; `ready` means a published revision exists.
 */
export type KnowledgeStatus = 'processing' | 'ready' | 'failed';
export interface KnowledgeSource {
  id: string;
  fileId: string;
  name: string;
  status: KnowledgeStatus;
  errorKey?: string;
  updatedAt: number;
}

export type TaskStatus = 'queued' | 'running' | 'done' | 'failed' | 'interrupted' | 'cancelled';

export interface TaskReply { prompt: string }

export interface Task extends Resource {
  name: string;
  date: string;
  agent: string;
  status: TaskStatus;
  project?: string;
  unread?: boolean;
  pinned?: boolean;
  archived?: boolean;
  kind?: 'work' | 'code' | 'channel';
  prompt?: string;
  file?: string;
  attachment?: string;
  model?: string;
  capabilities?: string[];
  replies?: TaskReply[];
  ownerId?: string;
  supportingAgentIds?: string[];
  reviewState?: 'review' | 'accepted';
  channelRunId?: string;
  /** 'simulated' when produced by the development adapter's template runner. */
  answerKind?: 'simulated' | 'markdown';
  answer?: string;
  /** Real API: full runtime state (Part 4) and reason; `status` above is the coarser UI view. */
  apiStatus?: string;
  statusReason?: string | null;
}

/** Real-API conversation (http mode). */
export interface TaskMessageView { id: string; role: 'user' | 'assistant' | 'system'; content: string; fileId?: string; createdAt: string }
export interface TaskDetail extends Task { apiStatus: string; statusReason?: string | null; messages: TaskMessageView[] }
export interface TaskEventView { seq: number; type: string; payload: Record<string, unknown>; createdAt: string }
export interface ApprovalView { id: string; tool: string; summary: string; status: 'pending' | 'approved' | 'rejected' | 'expired'; expiresAt: string }

export interface Project extends Resource {
  name: string;
  description: string;
  tasks: number;
  updated: string;
  color?: string;
  memberIds: string[];
  agentIds: string[];
  sharedContext: string;
  project?: string;
}

export interface Artifact extends Resource {
  name: string;
  type: 'doc' | 'slides' | 'sheet';
  updated: string;
  content?: string;
  project?: string;
}

export interface Automation extends Resource {
  name: string;
  description: string;
  schedule: string;
  enabled: boolean;
}

export interface Member {
  id: string;
  name: string;
  email?: string;
  role: Role;
  status: 'active' | 'disabled';
  departmentId?: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: 'member' | 'admin';
  status: 'pending' | 'accepted' | 'cancelled' | 'expired';
  createdAt: number;
  expiresAt: number;
}

export interface Connection {
  id: string;
  name: string;
  provider: 'feishu' | 'wecom' | 'mcp' | 'skill' | 'api';
  authMode: 'none' | 'static' | 'oauth' | 'exchange' | 'envfile';
  ownerScope: 'member' | 'space';
  ownerId: string;
  agentIds: string[];
  status: 'no_auth' | 'needs_auth' | 'active';
  enabled: boolean;
  usageClass: 'tool';
  /** Real API only: catalog connector behind this connection, and its display name. */
  connectorId?: string;
  connectorName?: string;
}

/** Real API only: a catalog connector and its installation in this workspace (Part 6 §2). */
export interface Connector {
  id: string;
  name: string;
  cls: string;
  auth: 'none' | 'api_key' | 'oauth';
  identity: 'user' | 'app';
  tools: string[];
  installed: boolean;
  enabled: boolean;
}

export interface ActivityEvent {
  id: string;
  at: string;
  type?: string;
  spaceEvent?: string;
  [key: string]: unknown;
}

export interface ChannelSource { sender: string; conversation: string; kind: 'direct' | 'group'; message: string; mention?: boolean }

export interface ChannelRun {
  id: string;
  taskId: string;
  bindingId: string;
  bindingName: string;
  platform: string;
  agentId: string;
  agentName: string;
  source: ChannelSource;
  stage: string;
  executionStatus: string;
  deliveryStatus: string;
  executionAttempts: number;
  deliveryAttempts: number;
  errorKey?: string;
  resultText?: string;
  fileId?: string;
  reply?: { text: string; at: number };
  history: { key: string; at: number }[];
  eventId: string;
  replayCount?: number;
  [key: string]: unknown;
}

export interface EcosystemBinding {
  id: string;
  name: string;
  platform: string;
  method: string;
  agentId: string;
  capabilities: string[];
  enabled?: boolean;
  connection?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ScenarioDraft { id: string; name: string; problem: string; [key: string]: unknown }

export type CollectionName = 'agents' | 'tasks' | 'projects' | 'artifacts' | 'automations' | 'scenarios';

export interface ApiError { code: string; message: string; status: number }

/** Event envelope (Part 11 §4). Tenant-level stream used for lists, toasts and task views. */
/** Event types the UI reacts to on the tenant stream; anything else still triggers a refresh via onmessage. */
export const TENANT_EVENT_TYPES = [
  'task.queued', 'task.running', 'task.updated', 'task.succeeded', 'task.failed', 'task.cancelled', 'task.interrupted',
  'agent.created', 'agent.updated', 'agent.deleted', 'project.created', 'project.updated', 'file.created',
  'resource.sharing_changed', 'channel.run.updated', 'knowledge.source.updated', 'tenant.updated', 'membership.updated',
] as const;

export interface WorkxEvent {
  event_id: string;
  type: string;
  tenant_id: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface RuntimeInfo {
  /** 'http' talks to the FastAPI control plane; 'development' is the in-browser adapter. */
  mode: 'http' | 'development';
  /** True when task execution, channels and connection tests are simulated. */
  simulated: boolean;
}

/** Model options come from the control plane (decision D-01: Claude model tiers only). */
export interface ModelOption { id: string; label: string }
