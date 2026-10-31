// Channel eligibility rules from the prototype's channel-model.js (pure part).
/* eslint-disable @typescript-eslint/no-explicit-any */
import { bindingIsReady, methodBy } from './ecosystem-model.js';
import { connectionSignature, initialConnectionDraft, sanitizeConnection } from './connection-model.js';

export function channelBindingReady(binding: any, data: any) {
  const connected = binding?.connection?.verified === true // real API: credentials stored by the broker
    || (binding?.connection?.test?.simulated === true && binding.connection.test.outcome === 'success');
  return !!binding && bindingIsReady(binding, data) && binding.enabled !== false && methodBy(binding.method)?.kind === 'dialogue' &&
    binding.connection?.signature === connectionSignature(binding) && connected;
}

export function channelBindingIdentity(binding: any) {
  const clean = sanitizeConnection(binding, initialConnectionDraft(binding));
  return JSON.stringify([connectionSignature(binding), clean.parameters, clean.test?.at || null]);
}

export const eligibleBindings = (data: any): any[] =>
  (data.ecosystemBindings || data.bindings || []).filter((binding: any) => channelBindingReady(binding, data));

export const runIsActive = (run: { stage: string }) => ['received', 'running', 'result', 'sending'].includes(run.stage);
export const runNeedsAttention = (run: { stage: string }) => ['execution_failed', 'delivery_failed', 'cancelled', 'interrupted'].includes(run.stage);

/** Copy key for a run's stage/execution/delivery value: values only the real API produces live under `web.`. */
const REAL_ONLY: Record<string, string[]> = {
  stage: ['unlinked', 'ignored', 'linked', 'rejected'],
  execution: ['none', 'needs_auth'],
  delivery: ['none', 'queued', 'unknown', 'blocked'],
};
export const channelKey = (kind: 'stage' | 'execution' | 'delivery', value: string) =>
  (REAL_ONLY[kind].includes(value) ? 'web.channel.' : 'channel.') + kind + '.' + value;
