// Approved production wording (decision 31, Q-17; docs/architecture/15-UI-FIDELITY.md D-02).
// Replaces prototype copy that describes browser-only storage or the prototype itself. Wording stays
// in the same place and close to the original length. Copy that describes simulated execution is NOT
// overridden here: it is only rendered while the development adapter is active (see `useSimulation`).
export const COPY_OVERRIDES: Record<string, { en: string; 'zh-CN': string }> = {
  'About this prototype': { en: 'About WorkX', 'zh-CN': '关于 WorkX' },
  '保存在此浏览器中，随时可以编辑。': { en: 'Saved to this workspace. You can edit it anytime.', 'zh-CN': '保存在当前空间中，随时可以编辑。' },
  'WorkX 产品交互原型，提供智能伙伴协作与任务管理体验。': { en: 'WorkX brings workmates, tasks, projects, and results together for individuals and teams.', 'zh-CN': 'WorkX 让个人与团队与智能伙伴协作，统一管理任务、项目与成果。' },
  '使用通用演示数据；全部操作保存在当前浏览器，不连接真实飞书服务或 AI 模型。此为独立设计原型。': { en: 'Data belongs to the current workspace. Connections to Feishu, WeCom, and AI execution depend on your workspace configuration.', 'zh-CN': '数据归属当前空间；飞书、企业微信与 AI 执行能力取决于空间的连接配置。' },
  'spaces.local': { en: 'Data, members, and connections belong to this workspace. Secrets are stored encrypted and never shown again.', 'zh-CN': '数据、成员与连接归属当前空间；密钥加密保存，保存后不再显示。' },
  'spaces.accountHint': { en: 'Your email is used for sign-in and invitations. Contact support to change it.', 'zh-CN': '邮箱用于登录与接收邀请，如需更改请联系支持。' },
  'saas.boundary': { en: 'Workspace roles manage the organization. Access to content is granted per resource.', 'zh-CN': '空间角色负责组织管理；内容访问按资源单独授权。' },
  'saas.memberNote': { en: 'Deactivating a member ends their sessions and stops tasks they started.', 'zh-CN': '停用成员会结束其登录会话，并停止其发起的任务。' },
};
