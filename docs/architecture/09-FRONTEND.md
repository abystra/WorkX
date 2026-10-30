# Part 9 — Frontend architecture (request D)

## 1. Current prototype (evidence)

- Vanilla ES modules, no build step, no framework; `dist/app.js` renders HTML strings; hash routes `#home, #new, #detail/:agent, #task/:id, #automations, #projects, #project/:id, #library, #hub, #code, #ecosystem, #scenarios, #team/:tab, #settings/:tab, #inbox` (extracted from `app.js`).
- State in `localStorage` (`workx-spaces-v1`, `workx-locale`); simulated execution with timers; i18n with `messages-*.js` dictionaries (en default, zh-CN); 73 Node behavior tests with browser I/O doubles.
- Valuable assets to keep: information architecture, copy and translations, interaction rules (e.g., sensitive inputs cleared on close, drafts per workspace, late callbacks only update their origin workspace, execution vs delivery separation), and the test scenarios as acceptance criteria.

## 2. Technology choices

| Concern | Choice | License | Alternative | Why |
| --- | --- | --- | --- | --- |
| Language | TypeScript (strict) | Apache-2.0 ○ | — | [DOC] decision |
| Framework | React 19 ○ | MIT ○ | Vue 3; Next.js | [DOC] decision; SPA is enough (no SEO needs; backend authority in FastAPI) |
| Build | Vite | MIT ○ | Rspack | Fast dev, simple static output for CDN |
| Routing | TanStack Router (type-safe params/search) | MIT ○ | React Router 7 | Typed `tenantSlug` params and search-state for filters |
| Server state | TanStack Query | MIT ○ | SWR | Cache keys include `tenantId`; mutations with optimistic updates |
| Client state | Zustand (small: UI prefs, drafts) | MIT ○ | Redux Toolkit | Minimal; per-tenant draft store mirrors prototype behavior |
| API client | `openapi-typescript` types + `openapi-fetch` | MIT ○ | Orval | Generated from FastAPI OpenAPI; no handwritten DTOs |
| Real-time | Native `EventSource` (cookie auth) wrapped by an SSE manager | — | WebSocket | SSE fits server→client streams; resumable by `Last-Event-ID` |
| UI primitives | Radix UI primitives + WorkX tokens (CSS variables), CSS Modules or Tailwind | MIT ○ | MUI, Ant Design | Accessible primitives; keep prototype look |
| i18n | i18next + react-i18next, ICU messages | MIT ○ | FormatJS | Port prototype dictionaries mechanically |
| Forms | React Hook Form + Zod (schemas generated from JSON Schema where possible) | MIT ○ | Formik | Validation parity with backend |
| Markdown/artifacts | `react-markdown` + sanitization; Office previews via server-rendered PDF/HTML previews | MIT ○ | — | Never render artifact HTML unsanitized |
| Testing | Vitest, Testing Library, Playwright (E2E + a11y via axe), MSW for API mocks | MIT/Apache ○ | Cypress | Port prototype tests to MSW-backed component tests |

## 3. Routing and information architecture

| Prototype route | Production route | Notes |
| --- | --- | --- |
| `#home` | `/t/:tenantSlug/home` | Task list, partners, quick start |
| `#new` | `/t/:tenantSlug/tasks/new?agent=` | |
| `#task/:id` | `/t/:tenantSlug/tasks/:taskId` | Chat or channel-task view by `task.source` |
| `#detail/:agent` | `/t/:tenantSlug/agents/:agentId/(instructions|skills|knowledge|channels|versions)` | |
| `#hub` | `/t/:tenantSlug/agents` | Catalog + tenant agents |
| `#projects`, `#project/:id` | `/t/:tenantSlug/projects`, `/t/:tenantSlug/projects/:projectId/(board|context|members|artifacts)` | |
| `#library` | `/t/:tenantSlug/library` | Artifacts and files |
| — | `/t/:tenantSlug/knowledge`, `/t/:tenantSlug/knowledge/:sourceId` | New |
| `#inbox` | `/t/:tenantSlug/inbox` | Channel tasks |
| `#ecosystem` | `/t/:tenantSlug/admin/channels` (org) | Channel bindings are admin-managed |
| `#team/:tab` | `/t/:tenantSlug/admin/(general|members|roles|sharing|connections|usage|audit)` | Org administration; personal tenant shows reduced set |
| — | `/t/:tenantSlug/connections` | Member's own connections + usable shared ones |
| `#settings/:tab` | `/settings/(general|profile|workspaces|security|sessions)` | **Global**, no tenant segment |
| `#automations`, `#scenarios`, `#code` | Feature-flagged; R2/R3 | Keep entry with "coming soon" state |
| — | `/invite/:token`, `/auth/*` | Public routes |

The tenant segment in the URL makes deep links unambiguous across tabs and matches the API's path-scoped tenant.

## 4. Authentication and workspace switching

- Login: SPA navigates to `api /auth/login` (server-side OIDC code flow); API sets `wx_session` HttpOnly cookie. SPA never handles tokens. CSRF token from `GET /me` stored in memory and sent as `X-WorkX-CSRF`.
- `TenantProvider` resolves `tenantSlug` → `tenant_id` from `GET /me/tenants`; unknown/forbidden slug → workspace picker.
- On switch: (1) abort in-flight requests for the old tenant (`AbortController` per tenant), (2) close SSE connections, (3) `queryClient.removeQueries({queryKey: ['t', oldTenantId]})`, (4) clear sensitive form state (credential fields are never stored in any store), (5) keep non-sensitive drafts in memory keyed by tenant (prototype behavior), (6) navigate.
- Background tasks keep running server-side; returning to a tenant re-subscribes using the last seen `seq`.
- `403 TENANT_REAUTH_REQUIRED` → re-auth flow for org SSO (R2).

## 5. Personal settings versus organization administration

| Surface | Scope | Visible to | Contents |
| --- | --- | --- | --- |
| Personal settings `/settings/*` | Global user | The user | Profile, language, notifications, my workspaces (leave org, create org), login sessions & devices, security |
| Workspace settings `/t/:slug/admin/*` | Current tenant | Personal: owner; Org: owner/admin (members see read-only "about") | General, members & invitations, roles (read-only matrix in R1), sharing inventory, connections policy, channels, usage & budgets, audit log |
| Daily work | Current tenant | Members | Home, tasks, projects, agents, knowledge, library, inbox |

## 6. Agent interaction, tasks, projects, knowledge, connections

- **Task view**: message timeline from `task_messages` + live `assistant.delta`; tool steps collapsed with redacted summaries; approval cards (approve/deny with operation details and risk); `needs_auth` card with Authorize button; artifact cards with preview, version list, download; status chip mapping Task states; separate delivery chip for channel tasks (prototype CU-03/CU-04 separation).
- **Projects**: board columns map to task review state (in progress / to review / confirmed / needs attention) like PJ-04, backed by server fields.
- **Knowledge**: source list with per-file pipeline status; re-index action; sharing.
- **Connections**: "My connections" vs "Organization connections available to me"; health, scopes, last used; authorize/reauthorize/disconnect; **no secret display, ever**; API-key entry fields are write-only and cleared on submit/close.

## 7. Real-time event handling

```text
SSEManager
  subscribe(tenantId, taskId, fromSeq) → EventSource(`/api/v1/tenants/${tenantId}/tasks/${taskId}/events?after_seq=${fromSeq}`)
  on message: parse envelope, drop if seq ≤ lastSeq (dedupe), apply reducer to Query cache (task snapshot, messages)
  on error: exponential backoff 1s→30s; on reconnect browser sends Last-Event-ID
  on event "stream.cursor_expired": refetch task snapshot, resubscribe from snapshot.seq
  on 401/403: stop, surface auth state
  max concurrent streams per tab: 6 (HTTP/1.1 limit) → use HTTP/2 at the edge; a tenant-level "activity" stream multiplexes task status for lists
```

## 8. Accessibility and responsive behavior

- WCAG 2.2 AA target: keyboard navigation (prototype already supports menu arrows, focus trap, Esc), visible focus, `aria-live="polite"` for streaming text with throttled announcements, reduced motion.
- Layout: desktop sidebar (collapsible), ≤ 768 px drawer navigation, 390 px tested breakpoint (prototype verified), chat composer sticky with safe-area insets.
- CJK typography: font stack with system CJK fonts; line-height tuned; long-word wrapping for URLs.
- Automated axe checks in Playwright on all primary routes in both languages.

## 9. Migration plan from the prototype

| Step | Work | Exit criterion |
| --- | --- | --- |
| F0 | Freeze prototype as acceptance reference; export dictionaries to i18next JSON; extract design tokens from `style.css` | Token + i18n packages build |
| F1 | Scaffold `apps/web` with shell, auth, tenant routing, switcher, personal settings, org admin (members/invitations) against the real API | J1–J3 pass E2E |
| F2 | Agents (create/edit/publish/share) and connections pages | J4 passes |
| F3 | Task creation + task view with SSE, approvals, needs_auth, artifacts | J5, J9, J10 pass |
| F4 | Projects, library, knowledge | J7 passes |
| F5 | Inbox and channel bindings (Feishu) | J6 passes |
| F6 | Retire prototype from default navigation; keep it runnable for design comparison | All prototype CU/SA/IN acceptance scenarios mapped to new E2E tests or explicitly descoped |

Prototype tests are converted to: (a) unit tests of pure reducers (sharing, invitation validation become **server** tests), (b) component tests with MSW, (c) E2E flows. Behaviors that were client-enforced in the prototype (e.g., `canManageSpace`, sharing validation) move to the server; the UI only mirrors them for UX.
