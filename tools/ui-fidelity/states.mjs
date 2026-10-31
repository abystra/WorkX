// Catalog of named UI states used as the visual and interaction baseline.
//
// Each state is reproduced from a fresh browser profile (empty localStorage, fixed clock),
// so the prototype's seed data (dist/data.js) is the fixture. The production web app must
// load the equivalent fixture (fixtures/prototype-seed.json) before capture.
//
// Steps reference the prototype's `data-action` hooks. The production app keeps the same
// attribute names on the equivalent controls (see docs/architecture/15-UI-FIDELITY.md §6),
// so one catalog drives both implementations. Per-target differences go in `targetSteps`.
//
// Step forms:
//   ['click', 'a:create-agent']                 -> first visible [data-action="create-agent"]
//   ['click', 'a:space-switch', {id: 'x'}]     -> [data-action="space-switch"][data-id="x"]
//   ['click', 'css:.some-selector']
//   ['fill', 'css:textarea', 'text']
//   ['select', 'css:select[name=x]', 'value']
//   ['checkall', 'css:input[name=confirmed]']      -> check every visible match
//   ['hover', 'css:.task-row']                 -> reveal hover-only controls
//   ['press', 'Escape']
//   ['wait', 300]
//
// `target` is the production route from docs/architecture/15-UI-FIDELITY.md §3; `module` the target module.

export const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  laptop: { width: 1280, height: 800 },
  mobile: { width: 390, height: 844 },
};

const ORG = 'wx-demo';
const PERSONAL = 'personal-alex';
// Channel flow: create a Feishu app-bot binding, pass the simulated connection test, send a sample message.
const addBinding = [
  ['click', 'a:eco-add'], ['click', 'a:eco-platform', { value: 'feishu' }], ['click', 'a:eco-next'],
  ['click', 'a:eco-method', { value: 'feishu-app-bot' }], ['click', 'a:eco-next'],
  ['select', 'css:select[name="assignedAgent"]', 'a1'], ['click', 'a:eco-next'],
  ['fill', 'css:input[name="name"]', 'OpsBot'], ['click', 'a:eco-save'], ['wait', 200],
];
const toAuthorization = [...addBinding, ['click', 'a:conn-sample'], ['click', 'a:conn-next']];
const testPassed = [...toAuthorization, ['checkall', 'css:input[name="confirmed"]'], ['click', 'a:conn-next'], ['click', 'a:conn-test'], ['wait', 1800]];
const compose = [...testPassed, ['click', 'a:conn-save'], ['wait', 3400], ['click', 'a:channel-compose'], ['click', 'a:channel-fill-sample']];
const delivered = [...compose, ['click', 'a:channel-submit'], ['wait', 7000]];

const toPersonal = [['click', 'a:profile'], ['click', 'a:space-switch', { id: PERSONAL }], ['wait', 300]];

export const STATES = [
  // ---- Shell and navigation
  { id: 'home', route: 'home', module: 'home', target: '/t/:slug/home', full: true },
  { id: 'home-quick-hidden', route: 'home', steps: [['click', 'a:hide-quick']], module: 'home', target: '/t/:slug/home' },
  { id: 'home-account-menu', route: 'home', steps: [['click', 'a:profile']], module: 'shell/account-menu', target: 'overlay' },
  { id: 'home-create-menu', route: 'home', steps: [['click', 'a:create-menu']], module: 'shell', target: 'overlay' },
  { id: 'home-language-menu', route: 'home', steps: [['click', 'a:language-menu']], module: 'shell', target: 'overlay' },
  { id: 'home-notifications', route: 'home', steps: [['click', 'a:notifications']], module: 'shell/notifications', target: 'overlay' },
  { id: 'home-global-search', route: 'home', steps: [['click', 'a:global-search'], ['wait', 150]], module: 'shell/search', target: 'overlay' },
  { id: 'home-global-search-noresult', route: 'home', steps: [['click', 'a:global-search'], ['fill', 'css:[role="dialog"] input', 'zzzz-no-match'], ['wait', 200]], module: 'shell/search', target: 'overlay' },
  { id: 'home-task-menu', route: 'home', steps: [['hover', 'css:.task-row'], ['click', 'css:.task-row .task-more']], module: 'tasks', target: 'overlay' },
  { id: 'home-task-filter', route: 'home', steps: [['click', 'a:filter']], module: 'tasks', target: 'overlay' },
  { id: 'home-collapsed-sidebar', route: 'home', steps: [['click', 'a:collapse']], module: 'shell', target: '/t/:slug/home', only: ['desktop'] },
  { id: 'mobile-nav-open', route: 'home', steps: [['click', 'a:expand']], module: 'shell', target: '/t/:slug/home', only: ['mobile'] },
  { id: 'shortcuts', route: 'home', steps: [['click', 'a:sidebar-settings'], ['wait', 100]], module: 'shell', target: 'overlay', optional: true },

  // ---- Workmates (AI partners)
  { id: 'agent-create-dialog', route: 'home', steps: [['click', 'a:create-menu'], ['click', 'css:.menu-item[data-action="create-agent"]']], module: 'agents', target: 'dialog' },
  { id: 'agent-create-validation', route: 'home', steps: [['click', 'a:create-menu'], ['click', 'css:.menu-item[data-action="create-agent"]'], ['click', 'a:save-agent']], module: 'agents', target: 'dialog' },
  { id: 'agent-detail-instructions', route: 'detail/a1', module: 'agents', target: '/t/:slug/detail/:id', full: true },
  { id: 'agent-detail-capabilities', route: 'detail/a1', steps: [['click', 'a:detail-tab', { tab: 'Capabilities' }]], module: 'agents', target: '/t/:slug/detail/:id (Capabilities)' },
  { id: 'agent-detail-context', route: 'detail/a1', steps: [['click', 'a:detail-tab', { tab: 'Work Context' }]], module: 'agents', target: '/t/:slug/detail/:id (Work Context)' },
  { id: 'agent-detail-ecosystem', route: 'detail/a1', steps: [['click', 'a:detail-tab', { tab: 'Ecosystem' }]], module: 'agents', target: '/t/:slug/detail/:id (Ecosystem)' },
  { id: 'agent-detail-manage', route: 'detail/a1', steps: [['click', 'a:detail-tab', { tab: 'Manage' }]], module: 'agents', target: '/t/:slug/detail/:id (Manage)' },
  { id: 'agent-edit-instructions', route: 'detail/a1', steps: [['click', 'a:edit-instructions']], module: 'agents', target: 'dialog' },
  { id: 'hub', route: 'hub', module: 'agents/hub', target: '/t/:slug/hub', full: true },

  // ---- Tasks and conversation
  { id: 'new-task', route: 'new', module: 'tasks/composer', target: '/t/:slug/new', full: true },
  { id: 'new-task-model-menu', route: 'new', steps: [['click', 'a:select-model']], module: 'tasks/composer', target: 'overlay' },
  { id: 'new-task-attach-menu', route: 'new', steps: [['click', 'a:attach-menu']], module: 'tasks/composer', target: 'overlay' },
  { id: 'new-task-project-menu', route: 'new', steps: [['click', 'a:select-project']], module: 'tasks/composer', target: 'overlay' },
  { id: 'new-task-voice', route: 'new', steps: [['click', 'a:voice']], module: 'tasks/composer', target: 'dialog' },
  { id: 'task-running', route: 'new', steps: [['fill', 'css:.composer textarea', 'Summarize this week\'s project updates'], ['click', 'a:send-task'], ['wait', 300]], module: 'tasks/conversation', target: '/t/:slug/task/:id', note: 'running state; simulated in prototype' },
  { id: 'task-done', route: 'new', steps: [['fill', 'css:.composer textarea', 'Summarize this week\'s project updates'], ['click', 'a:send-task'], ['wait', 2200]], module: 'tasks/conversation', target: '/t/:slug/task/:id', full: true },
  { id: 'task-rename', route: 'home', steps: [['hover', 'css:.task-row'], ['click', 'css:.task-row .task-more'], ['click', 'css:.menu-item[data-action="rename-task"]']], module: 'tasks', target: 'dialog' },

  // ---- Projects
  { id: 'projects', route: 'projects', module: 'projects', target: '/t/:slug/projects', full: true },
  { id: 'project-create', route: 'projects', steps: [['click', 'a:create-project']], module: 'projects', target: 'dialog' },
  { id: 'project-create-validation', route: 'projects', steps: [['click', 'a:create-project'], ['click', 'a:save-project']], module: 'projects', target: 'dialog' },
  { id: 'project-board', route: 'projects', steps: [['click', 'a:open-project']], module: 'projects', target: '/t/:slug/project/:id', full: true },

  // ---- Library / artifacts
  { id: 'library', route: 'library', module: 'library', target: '/t/:slug/library', full: true },
  { id: 'library-preview', route: 'library', steps: [['click', 'a:open-file']], module: 'library', target: 'dialog' },

  // ---- Automations, scenarios, code
  { id: 'automations', route: 'automations', module: 'automations', target: '/t/:slug/automations' },
  { id: 'automation-create', route: 'automations', steps: [['click', 'a:create-automation']], module: 'automations', target: 'dialog' },
  { id: 'scenarios-empty', route: 'scenarios', module: 'scenarios', target: '/t/:slug/scenarios' },
  { id: 'scenario-create', route: 'scenarios', steps: [['click', 'a:scenario-create']], module: 'scenarios', target: 'dialog' },
  { id: 'code', route: 'code', module: 'code', target: '/t/:slug/code' },

  // ---- Channels (inbox, ecosystem bindings, connection setup)
  { id: 'inbox', route: 'inbox', module: 'channels/inbox', target: '/t/:slug/inbox' },
  { id: 'ecosystem', route: 'ecosystem', module: 'channels/ecosystem', target: '/t/:slug/ecosystem', full: true },
  { id: 'ecosystem-wizard-platform', route: 'ecosystem', steps: [['click', 'a:eco-add']], module: 'channels/ecosystem', target: 'dialog' },
  { id: 'ecosystem-wizard-method', route: 'ecosystem', steps: [['click', 'a:eco-add'], ['click', 'a:eco-platform'], ['click', 'a:eco-next']], module: 'channels/ecosystem', target: 'dialog', optional: true },
  { id: 'connection-params', route: 'ecosystem', steps: addBinding, module: 'channels/connection', target: 'dialog' },
  { id: 'connection-authorization', route: 'ecosystem', steps: toAuthorization, module: 'channels/connection', target: 'dialog' },
  { id: 'connection-test-passed', route: 'ecosystem', steps: testPassed, module: 'channels/connection', target: 'dialog' },
  { id: 'ecosystem-binding-ready', route: 'ecosystem', steps: [...testPassed, ['click', 'a:conn-save'], ['wait', 3400]], module: 'channels/ecosystem', target: '/t/:slug/ecosystem', full: true },
  { id: 'channel-compose', route: 'ecosystem', steps: compose, module: 'channels/compose', target: 'dialog' },
  { id: 'channel-task-delivered', route: 'ecosystem', steps: delivered, module: 'channels/task', target: '/t/:slug/task/:id (channel)', full: true },
  { id: 'inbox-delivered', route: 'ecosystem', steps: [...delivered, ['click', 'a:nav', { page: 'inbox' }], ['wait', 200]], module: 'channels/inbox', target: '/t/:slug/inbox' },

  // ---- Organization administration (current org tenant)
  { id: 'org-general', route: 'team/general', module: 'admin', target: '/t/:slug/team/general' },
  { id: 'org-members', route: 'team/members', module: 'admin/members', target: '/t/:slug/team/members', full: true },
  { id: 'org-invite', route: 'team/members', steps: [['click', 'a:space-invite']], module: 'admin/members', target: 'dialog' },
  { id: 'org-invite-validation', route: 'team/members', steps: [['click', 'a:space-invite'], ['fill', 'css:[role="dialog"] textarea, [role="dialog"] input[type="text"], [role="dialog"] input:not([type])', 'not-an-email'], ['click', 'a:space-save-invite']], module: 'admin/members', target: 'dialog', optional: true },
  { id: 'org-permissions', route: 'team/permissions', module: 'admin/roles', target: '/t/:slug/team/permissions' },
  { id: 'org-data', route: 'team/data', module: 'admin/sharing', target: '/t/:slug/team/data', full: true },
  { id: 'org-sharing-dialog', route: 'team/data', steps: [['click', 'a:space-sharing']], module: 'admin/sharing', target: 'dialog' },
  { id: 'org-connections', route: 'team/connections', module: 'connections', target: '/t/:slug/team/connections' },
  { id: 'org-connection-add', route: 'team/connections', steps: [['click', 'a:space-add-connection']], module: 'connections', target: 'dialog' },
  { id: 'org-usage', route: 'team/usage', module: 'admin/usage', target: '/t/:slug/team/usage' },
  { id: 'org-activity', route: 'team/activity', module: 'admin/audit', target: '/t/:slug/team/activity' },
  { id: 'org-create-dialog', route: 'home', steps: [['click', 'a:profile'], ['click', 'a:space-create']], module: 'shell/account-menu', target: 'dialog' },

  // ---- Personal settings (global user)
  { id: 'settings-general', route: 'settings/general', module: 'settings', target: '/settings/general' },
  { id: 'settings-profile', route: 'settings/profile', module: 'settings', target: '/settings/profile' },
  { id: 'settings-spaces', route: 'settings/spaces', module: 'settings', target: '/settings/spaces' },

  // ---- Personal workspace
  { id: 'personal-home-empty', route: 'home', steps: toPersonal, module: 'home', target: '/t/:personal/home', full: true },
  { id: 'personal-projects-empty', route: 'home', steps: [...toPersonal, ['click', 'a:nav', { page: 'projects' }]], module: 'projects', target: '/t/:personal/projects' },
  { id: 'personal-workspace-settings', route: 'home', steps: [...toPersonal, ['click', 'a:nav', { page: 'team' }]], module: 'admin', target: '/t/:personal/team/general' },
];

export const ORG_ID = ORG;
