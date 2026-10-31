// Ported verbatim from workmates-prototype/dist/ecosystem-model.js (pure catalog and validation rules).
// Shared by the UI and the development adapter; the control plane will own these rules.
// Local prototype model. Capability selections are requests, never granted scopes.
export const PLATFORMS = [
  {id: 'feishu', name: 'eco.feishu', type: 'eco.feishuType', description: 'eco.feishuDescription', icon: 'globe'},
  {id: 'wecom', name: 'eco.wecom', type: 'eco.wecomType', description: 'eco.wecomDescription', icon: 'chat'}
];
export const CAPABILITIES = [
  {id: 'message-receive', name: 'eco.capReceive', description: 'eco.capReceiveHint', group: 'messages'},
  {id: 'message-reply', name: 'eco.capReply', description: 'eco.capReplyHint', group: 'messages'},
  {id: 'notification-send', name: 'eco.capNotify', description: 'eco.capNotifyHint', group: 'messages'},
  {id: 'document-read', name: 'eco.capDocRead', description: 'eco.capDocReadHint', group: 'tools'},
  {id: 'document-write', name: 'eco.capDocWrite', description: 'eco.capDocWriteHint', group: 'tools'},
  {id: 'table-read', name: 'eco.capTableRead', description: 'eco.capTableReadHint', group: 'tools'},
  {id: 'table-write', name: 'eco.capTableWrite', description: 'eco.capTableWriteHint', group: 'tools'},
  {id: 'calendar-read', name: 'eco.capCalendar', description: 'eco.capCalendarHint', group: 'tools'},
  {id: 'user-info', name: 'eco.capUserInfo', description: 'eco.capUserInfoHint', group: 'tools'}
];
export const METHODS = [
  {id: 'feishu-app-bot', platform: 'feishu', name: 'eco.methodFeishuBot', description: 'eco.methodFeishuBotHint', kind: 'dialogue', required: ['message-receive','message-reply'], optional: ['document-read','document-write','table-read','table-write','calendar-read']},
  {id: 'feishu-webhook', platform: 'feishu', name: 'eco.methodFeishuWebhook', description: 'eco.methodFeishuWebhookHint', kind: 'notification', required: ['notification-send'], optional: []},
  {id: 'feishu-api', platform: 'feishu', name: 'eco.methodFeishuApi', description: 'eco.methodFeishuApiHint', kind: 'tools', required: [], optional: ['document-read','document-write','table-read','table-write','calendar-read']},
  {id: 'wecom-ai-bot', platform: 'wecom', name: 'eco.methodWecomAi', description: 'eco.methodWecomAiHint', kind: 'dialogue', required: ['message-receive','message-reply'], optional: ['user-info','document-write']},
  {id: 'wecom-app', platform: 'wecom', name: 'eco.methodWecomApp', description: 'eco.methodWecomAppHint', kind: 'dialogue', required: ['message-receive','message-reply'], optional: ['user-info']},
  {id: 'wecom-webhook', platform: 'wecom', name: 'eco.methodWecomWebhook', description: 'eco.methodWecomWebhookHint', kind: 'notification', required: ['notification-send'], optional: []}
];
export const platformBy = id => PLATFORMS.find(item => item.id === id);
export const methodBy = id => METHODS.find(item => item.id === id);
export const capabilityBy = id => CAPABILITIES.find(item => item.id === id);
export function normalizeCapabilities(methodId, selected = []) {
  const method = methodBy(methodId);
  if (!method) return [];
  const allowed = [...method.required, ...method.optional];
  return [...new Set([...method.required, ...(Array.isArray(selected) ? selected : [])])].filter(id => allowed.includes(id));
}
export function bindingIsReady(binding, data) {
  const method = methodBy(binding?.method);
  if (!binding?.configured || !method || method.platform !== binding.platform || !String(binding.name || '').trim() || !data.agents?.some(agent => agent.id === binding.assignedAgent)) return false;
  const caps = binding.capabilities;
  if (!Array.isArray(caps) || !caps.length || new Set(caps).size !== caps.length || caps.some(id => ![...method.required,...method.optional].includes(id)) || method.required.some(id => !caps.includes(id))) return false;
  return method.id !== 'wecom-ai-bot' || ['websocket','callback'].includes(binding.transport);
}
export function ensureEcosystemData(data) {
  if (!Array.isArray(data.scenarioDrafts)) data.scenarioDrafts = [];
  if (!Array.isArray(data.ecosystemBindings)) data.ecosystemBindings = [];
  if (data.ecosystemSchemaVersion === 2) return;
  const legacy = data.ecosystemConnections && typeof data.ecosystemConnections === 'object' && !Array.isArray(data.ecosystemConnections) ? data.ecosystemConnections : {};
  for (const platform of PLATFORMS) {
    const old = legacy[platform.id];
    if (!old || !old.configured) continue;
    const id = 'legacy-' + platform.id;
    if (data.ecosystemBindings.some(item => item.id === id)) continue;
    const method = old.mode === 'feishu-app' && platform.id === 'feishu' ? 'feishu-app-bot' : old.mode === 'wecom-bot' && platform.id === 'wecom' ? 'wecom-ai-bot' : 'undecided';
    data.ecosystemBindings.push({id, platform: platform.id, method, name: old.name || '', assignedAgent: old.assignedAgent || '', capabilities: normalizeCapabilities(method), enabled: old.enabled !== false, configured: true, ...(method === 'wecom-ai-bot' && ['websocket','callback'].includes(old.transport) ? {transport: old.transport} : {})});
  }
  if (!legacy.feishu?.configured) {
    for (const agent of data.agents || []) {
      if (!agent.demoConnected) continue;
      const id = 'legacy-feishu-' + agent.id;
      if (data.ecosystemBindings.some(item => item.id === id || (item.platform === 'feishu' && item.assignedAgent === agent.id))) continue;
      data.ecosystemBindings.push({id, platform: 'feishu', method: 'undecided', name: agent.name || 'Feishu', assignedAgent: agent.id, capabilities: [], enabled: true, configured: true});
    }
  }
  data.ecosystemSchemaVersion = 2;
}
