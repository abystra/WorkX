// Copy for states and screens the prototype never needed (docs/architecture/15-UI-FIDELITY.md §4.3).
// Keys use the `web.` prefix so they never collide with converted prototype keys.
export const COPY_ADDITIONS: Record<string, { en: string; 'zh-CN': string }> = {
  'web.loading': { en: 'Loading…', 'zh-CN': '正在加载…' },
  'web.loadErrorTitle': { en: 'WorkX could not load this page', 'zh-CN': 'WorkX 暂时无法加载此页面' },
  'web.loadErrorBody': { en: 'Check your connection and try again. If this keeps happening, the service may be unavailable.', 'zh-CN': '请检查网络后重试；如果持续出现，可能是服务暂时不可用。' },
  'web.retry': { en: 'Try again', 'zh-CN': '重试' },
  'web.notFoundTitle': { en: 'This page is not available', 'zh-CN': '无法访问此页面' },
  'web.notFoundBody': { en: 'It may have been removed, or you may not have access in this workspace.', 'zh-CN': '内容可能已删除，或你在当前空间没有访问权限。' },
  'web.backHome': { en: 'Back to workbench', 'zh-CN': '返回工作台' },
  'web.modelCaption': { en: 'Model', 'zh-CN': '模型' },
  'web.chatFootnote': { en: 'Workmates can make mistakes. Review results before sharing them.', 'zh-CN': '智能伙伴可能出错，分享成果前请先确认内容。' },
  'web.requestFailed': { en: 'That did not work. Try again.', 'zh-CN': '操作未完成，请重试。' },
};
