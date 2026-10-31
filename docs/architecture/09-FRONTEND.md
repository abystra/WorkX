# Part 9 — Frontend architecture (request D)

The prototype UI is the approved design baseline **[PO]**. This part covers engineering choices only; visual design, information architecture, states and the migration map are governed by **Part 15 (UI fidelity)**. Where an earlier draft of this part proposed a component library, a new route grouping, or a separate Connections page, those proposals are withdrawn.

## 1. Current prototype (evidence)

- Vanilla ES modules, no build step, no framework; `dist/app.js` renders HTML strings; hash routes `#home, #new, #detail/:agent, #task/:id, #automations, #projects, #project/:id, #library, #hub, #code, #ecosystem, #scenarios, #team/:tab, #settings/:tab, #inbox` (from `app.js` `readRoute`).
- Eight stylesheets with a small token set (`--text`, `--muted`, `--line`, `--surface`, `--sidebar`, `--blue`, `--radius`, `--sidebar-width`, system font stack), inline SVG icon dictionary, six avatar SVGs.
- State in `localStorage` (`workx-spaces-v1`, `workx-locale`); simulated execution with timers; i18n dictionaries in `messages-*.js` (English default, zh-CN); 73 Node behavior tests.
- Full inventory of screens, overlays, interaction conventions and states: Part 15 §2.

## 2. Technology choices

| Concern | Choice | License | Note |
| --- | --- | --- | --- |
| Language | TypeScript (strict) | Apache-2.0 ○ | [DOC] decision |
| Framework | React ○ | MIT ○ | [DOC] decision; SPA |
| Build | Vite | MIT ○ | Static output for CDN |
| Routing | TanStack Router | MIT ○ | Typed workspace slug and tab params; page names kept from the prototype (Part 15 §3) |
| Server state | TanStack Query | MIT ○ | Cache keys include `tenantId` |
| Client state | Zustand (UI prefs, per-workspace drafts) | MIT ○ | Mirrors prototype draft behavior |
| API client | `openapi-typescript` + `openapi-fetch` | MIT ○ | Generated from FastAPI OpenAPI |
| Real-time | Native `EventSource` with cookie auth | — | Resumable via `Last-Event-ID` |
| **Styling** | **Prototype stylesheets ported verbatim; components render the same DOM structure and class names** | — | **No new component library** (Radix etc. not adopted). Refactors only behind the zero-diff visual gate (Part 15 §4.2, §7) |
| Overlays | Small in-house hooks reproducing `modal()`/`popover()` behavior (focus trap, Esc, backdrop) | — | Same markup as prototype |
| Icons | `<Icon>` component emitting the prototype's SVG paths | — | From `icons.js` |
| i18n | i18next + react-i18next with the prototype's keys | MIT ○ | Mechanical conversion of `messages-*.js` |
| Forms | React Hook Form + shared validation rules ported from prototype models | MIT ○ | Native required-field bubbles kept |
| Markdown/artifacts | `react-markdown` with sanitization; Office previews rendered server-side | MIT ○ | Inside the existing preview dialog |
| Testing | Vitest, Testing Library, Playwright E2E, **`tools/ui-fidelity` visual comparison against the prototype**, axe-core | MIT/Apache ○ | Part 15 §7 |

## 3. Routing

Production routes keep the prototype's page names under a workspace segment: `/t/:slug/home`, `/t/:slug/new`, `/t/:slug/task/:id`, `/t/:slug/detail/:agentId`, `/t/:slug/hub`, `/t/:slug/projects`, `/t/:slug/project/:id`, `/t/:slug/library`, `/t/:slug/automations`, `/t/:slug/scenarios`, `/t/:slug/code`, `/t/:slug/inbox`, `/t/:slug/ecosystem`, `/t/:slug/team/:tab`; global `/settings/:tab`; public `/login`, `/signup`, `/invite/:token`. The sidebar groups and order stay exactly as in the prototype (Part 15 §2.1). The full screen-to-module map is Part 15 §3.

## 4. Authentication and workspace switching

- Login: the SPA navigates to `api /auth/login` (server-side OIDC code flow); the API sets an HttpOnly session cookie. The SPA never handles tokens. CSRF token from `GET /me`, sent as `X-WorkX-CSRF`.
- The account menu and the current-workspace bar behave as in the prototype (Part 15 §2.2): list personal and organization workspaces with a check mark on the current one, create organization, invite members, organization settings, personal settings.
- On switch: abort in-flight requests for the old tenant, close its SSE streams, drop its query cache, close sensitive dialogs and clear their fields, keep non-sensitive drafts in memory keyed by tenant, reset route/filters/selection, show the prototype's "switched" toast, navigate to the same page in the new workspace.
- Background tasks keep running server-side; returning to a workspace re-subscribes from the last seen event `seq`.
- `403 TENANT_REAUTH_REQUIRED` → re-auth flow for organization SSO (R2).

## 5. Personal settings versus organization administration

| Surface | Scope | Layout (from prototype) | Tabs |
| --- | --- | --- | --- |
| Personal settings `/settings/:tab` | Global user | Settings layout with its own left navigation and "back to workbench" | General (language, notifications), Profile, My workspaces; new: Security & sessions (Part 15 §4.3) |
| Organization settings `/t/:slug/team/:tab` (personal workspace: "Workspace settings", reduced tabs) | Current tenant | Same settings layout, workspace card at top | General, Members & invitations, Roles & permissions, Data & sharing, Connections & credentials, Usage, Activity |
| Daily work | Current tenant | Main workbench layout | Home, Channel workbench, New Task, Projects, Library, Hub, Business scenarios, Automations, Ecosystem |

## 6. Agent interaction, tasks, projects, knowledge, connections

Behavior is the prototype's; data becomes real:

- **Conversation**: existing answer layout; new states (streaming text, tool steps, approval card, needs-authorization card, cancel, partial results, artifact versions) use the patterns listed in Part 15 §4.3.
- **Projects**: board columns (in progress / to review / confirmed / needs attention), assignment, context, roster as in PJ-04..07, now multi-user.
- **Knowledge**: new functionality with no prototype screen; proposed inside Workmate detail "Work Context" and as a Library filter, pending Q-15.
- **Connections**: stay in organization settings "Connections & credentials" and Ecosystem (channels), as in the prototype; real authorization replaces the checklist; secret fields remain write-only.

## 7. Real-time event handling

```text
SSEManager
  subscribe(tenantId, taskId, fromSeq) → EventSource(`/api/v1/tenants/${tenantId}/tasks/${taskId}/events?after_seq=${fromSeq}`)
  on message: drop if seq ≤ lastSeq, apply reducer to the query cache (task snapshot, messages)
  on error: backoff 1s→30s; browser sends Last-Event-ID on reconnect
  on "stream.cursor_expired": refetch snapshot, resubscribe from snapshot.seq
  on 401/403: stop and show the session or permission state
  lists use one tenant-level activity stream instead of one stream per task
```

## 8. Accessibility and viewport scope

- Keep the prototype's keyboard model: arrow keys in menus, focus trap and Esc in dialogs, ⌘/Ctrl+K, ⌘/Ctrl+Enter, visible focus ring, `aria-live` toast region; add `aria-live` throttled announcements for streamed answers.
- Contrast issue in the baseline (`--muted` 3.02:1) is documented as a proposed deviation, not silently changed (Part 15 D-04).
- **Viewport scope: desktop web** (1440×900 primary, 1280×800 secondary) **[PO 2026-10-31]**. The prototype's responsive CSS is carried over with the stylesheets but narrow layouts are not acceptance criteria.

## 9. Migration plan from the prototype

| Step | Work | Exit criterion |
| --- | --- | --- |
| F0 | Port stylesheets, icons, avatars, i18n dictionaries; app shell with sidebar and account menu; fidelity seed endpoint (B-UI-02) | Shell states in the catalog pass `compare` |
| F1 | Auth pages (new), workspace switching, personal settings, organization settings (members, invitations, roles, data & sharing, connections, usage, activity) | J1–J3 E2E; settings/admin catalog states pass |
| F2 | Workmates (hub, detail tabs, create/edit) | J4; agent states pass |
| F3 | Composer and conversation with SSE, approvals, needs-auth, artifacts | J5, J9, J10; task states pass; new states signed off |
| F4 | Projects, Library, Knowledge (new) | J7; project/library states pass |
| F5 | Channel workbench and Ecosystem with real Feishu integration | J6; channel/ecosystem states pass |
| F6 | Default navigation switches to `apps/web` | **All catalog states pass or are approved deviations; prototype remains in repo as reference** |

Behaviors enforced client-side in the prototype (e.g., `canManageSpace`, sharing and invitation validation) move to the server; the UI keeps the same messages and placement.
