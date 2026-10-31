import { create } from 'zustand';

/* eslint-disable @typescript-eslint/no-explicit-any */
export interface WizardState { step: number; editingId: string | null; draft: any; error: string }
export interface ConnectionSession {
  bindingId: string;
  signature: string;
  stage: 'params' | 'authorization' | 'test';
  draft: { params: Record<string, string>; confirmed: string[]; test: any };
  scenario: string;
  visibleSecrets: string[];
  error: string;
  errors: { field: string; key: string }[];
  running: boolean;
  progress: number;
  lastOutcome: string | null;
  runToken: number;
}
export interface ChannelDraft { bindingId: string; sender: string; conversation: string; message: string; kind: string; mentioned: boolean; projectId: string; scenario: string; error: string; rev?: number }

/**
 * Dialog state for the ecosystem wizard, connection setup and simulated message composer
 * (the prototype's state.ecosystemWizard / state.connection / state.channelDraft). Body and footer of
 * each dialog read the same state. Secret parameter values live only here and are cleared on close.
 */
export const useChannelUi = create<{
  wizard: WizardState | null;
  connection: ConnectionSession | null;
  compose: ChannelDraft | null;
  set: (patch: Partial<{ wizard: WizardState | null; connection: ConnectionSession | null; compose: ChannelDraft | null }>) => void;
}>(set => ({ wizard: null, connection: null, compose: null, set }));

export const updateWizard = (patch: Partial<WizardState>) => {
  const { wizard, set } = useChannelUi.getState();
  if (wizard) set({ wizard: { ...wizard, ...patch } });
};
export const updateConnection = (patch: Partial<ConnectionSession>) => {
  const { connection, set } = useChannelUi.getState();
  if (connection) set({ connection: { ...connection, ...patch } });
};
