// Platform catalog from the prototype's ecosystem-model.js (extended in the channels module).
export const PLATFORMS = [
  { id: 'feishu', name: 'eco.feishu', type: 'eco.feishuType', description: 'eco.feishuDescription', icon: 'globe' },
  { id: 'wecom', name: 'eco.wecom', type: 'eco.wecomType', description: 'eco.wecomDescription', icon: 'chat' },
];
export const platformBy = (id?: string) => PLATFORMS.find(item => item.id === id);

export const runIsActive = (stage: string) => ['received', 'running', 'result', 'sending'].includes(stage);
export const runNeedsAttention = (stage: string) => ['execution_failed', 'delivery_failed', 'cancelled', 'interrupted'].includes(stage);
