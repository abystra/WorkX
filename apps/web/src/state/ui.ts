import { create } from 'zustand';

/** Per-workspace drafts. Kept in memory only (prototype SA-06: drafts survive a switch, not a refresh). */
export interface Drafts {
  draft: string;
  attachment: string;
  selectedProject: string;
  agent: string;
  model: string;
  capabilities: string[];
  codeDraft: string;
  codeProject: string;
}

export const emptyDrafts = (): Drafts => ({ draft: '', attachment: '', selectedProject: '', agent: '', model: 'Auto', capabilities: [], codeDraft: '', codeProject: '' });

/** View state that the prototype kept in its `state` object. Server data lives in TanStack Query. */
export interface UiState {
  collapsed: boolean;
  mobileOpen: boolean;
  listTab: string;
  filter: string;
  query: string;
  libraryFilter: string;
  hubFilter: string;
  secondaryQuery: string;
  detailTab: string;
  projectTab: string;
  resourceTab: string;
  channelFilter: string;
  recommendation: number;
  drafts: Record<string, Drafts>;
  set: (patch: Partial<Omit<UiState, 'set' | 'setDrafts'>>) => void;
  setDrafts: (tenantId: string, patch: Partial<Drafts>) => void;
}

export const useUi = create<UiState>(set => ({
  collapsed: false,
  mobileOpen: false,
  listTab: 'tasks',
  filter: 'all',
  query: '',
  libraryFilter: 'all',
  hubFilter: 'all',
  secondaryQuery: '',
  detailTab: 'Instructions',
  projectTab: 'tasks',
  resourceTab: 'projects',
  channelFilter: 'all',
  recommendation: 0,
  drafts: {},
  set: patch => set(patch),
  setDrafts: (tenantId, patch) => set(s => ({ drafts: { ...s.drafts, [tenantId]: { ...(s.drafts[tenantId] || emptyDrafts()), ...patch } } })),
}));

export const useDrafts = (tenantId: string) => useUi(s => s.drafts[tenantId]) || emptyDrafts();
