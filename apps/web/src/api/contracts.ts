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
}

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
