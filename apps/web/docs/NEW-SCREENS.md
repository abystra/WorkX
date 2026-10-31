# New screens, changed wording and deviations: for design review

Everything in `apps/web` that is **not** a faithful copy of the approved prototype (`workmates-prototype/dist`) is listed here. All other screens reproduce the prototype's DOM, class names and stylesheets. They are checked against it pixel by pixel, see §5.

Screenshots for review are produced locally. They are not committed because they are reproducible:

```bash
cd apps/web && pnpm dev:fidelity
```

```bash
cd apps/web && node tests/e2e/account-screens.mjs --shots ../../tools/ui-fidelity/out/new-screens
```

```bash
cd apps/web && node tests/e2e/knowledge.mjs --shots ../../tools/ui-fidelity/out/new-screens
```

Output: `tools/ui-fidelity/out/new-screens/{en,zh-CN}/{desktop,laptop}/*.png` (1440×900 and 1280×800).

## 1. Account screens (no prototype reference)

Routes: `/login`, `/signup`, `/invite/:token`, `/session-expired`. Source: `src/features/auth/AuthPages.tsx`, `src/styles/web/auth.css`.

**Design.** The screens are built only from existing parts:

- Prototype tokens (`--sidebar` page background, `--muted`, `--line`).
- The sidebar brand row (logo and "WorkX" word mark) at the top left.
- One centred `.modal` card (440px) with `.modal-header` and `.modal-body`.
- Full-width `.btn primary` / `.btn` actions.
- The connection dialog's `中文 / English` switch under the card.

Notes use the prototype's neutral info style. The development-adapter notice uses a muted amber so it is never mistaken for product copy. Errors use a red box with `role="alert"`.

**Behavior** (architecture Part 9 §3, Part 8 J1/J2):

| Screen | Content | Action |
| --- | --- | --- |
| Sign in | Title, one-line explanation, notice that WorkX never sees the password, link to sign-up | "Continue to sign in" navigates to `GET /api/v1/auth/login?intent=login&return_to=…`. Keycloak hosts the credential form. **No password field exists in the SPA.** |
| Sign up | Same layout; explains the personal workspace is created after email verification | `intent=signup` |
| Invitation | Explains joining with the inviter's role, hint to use the invited email | "Accept invitation" calls `POST /api/v1/invitations/accept` and lands on the organization's Home. Opening the link alone never accepts it. Signed-out visitors are offered sign-in/sign-up and returned to the link. Code-specific errors: not valid, expired, already used, wrong email, no seats. |
| Session ended | Explains the session expired or was revoked | "Sign in again" returns the user to the page they were on. |

`return_to` accepts only same-origin relative paths (`safeReturnTo`); anything else falls back to `/`. A 401 inside the app goes to `/session-expired` if a session had worked before (or the code is `SESSION_REVOKED`), otherwise to `/login`.

With the development adapter there is no identity service. Continue goes straight to the destination, and the amber notice says so.

**For review:**

- (a) Card copy length in zh-CN.
- (b) Whether the invitation screen should show the organization name and inviter. That needs an invitation-preview endpoint, which the architecture does not define. See `BACKEND-INTEGRATION.md`.
- (c) Whether sign-in should go straight to Keycloak without this intermediate page.

## 2. Knowledge (approved placement, decision 30 / Q-15)

Source: `src/features/knowledge/Knowledge.tsx`, `src/styles/web/knowledge.css`.

- **Workmate › Work Context tab:** a "Knowledge" section below the existing work-context box. It has:
  - the same `.detail-label` heading-and-button row as the section above ("Attach from Library");
  - a one-line explanation;
  - a bordered list (file icon, name, status tag, "Remove"), or an `.instruction-box` empty state.
- **Attach dialog:** the project roster dialog's checkbox list (`.wx-team-choice-list`) over Library files, with Cancel and Save.
- **Library:** a fifth filter chip, "Knowledge". Cards of files used as knowledge show the status tag at the right of the card footer.
- **Status tags** reuse the channel status tag colours, as Part 15 §4.3 specifies:
  - Processing: neutral blue-grey.
  - Ready: the green "delivered" style.
  - Processing failed: the amber "failed" style.
- **No new sidebar item.**

On the real API, a failed source shows the reason after its status tag (for example "This file type cannot be read yet."). With the development adapter, processing is simulated (Processing → Ready after 1.2 s) and a `.prototype-note` says files are not parsed or searched. Upload of new files is not built; Knowledge uses existing Library files only.

## 2b. Run states in the conversation (real runtime only)

Source: `src/features/tasks/RealConversation.tsx`, `src/styles/web/conversation.css`. Used only when execution is not simulated; the adapter keeps the prototype's simulated answer.

It renders the real messages with the prototype classes (`chat-user`, `assistant-header`, `assistant-answer`, `answer-artifact` for result files), plus these new states:

- **Queued:** "Waiting to start…".
- **Working:** a pulse line with a Stop button and a list of tool steps (running, done, failed, or reused from an earlier attempt).
- **Approval needed:** a bordered card with a summary, Approve and Reject.
- **Failed, interrupted or cancelled:** a short explanation, the reason for failures, and Try again.
- **Needs access:** an explanation plus Try again.

- **Citations:** an answer that used knowledge keeps `[n]` markers in its text. Below it, a "Sources" list (small, muted, separated by the prototype's line colour) shows the number, the file name and the page, slide, sheet range or section. Hovering an item shows the quoted passage.

**For review:** the tool names shown in steps come straight from the gateway, such as "crm list accounts". The product might want friendlier labels per connector.

## 2c. Add connection on the real API (P-07)

Source: `src/features/settings/AdminDialogs.tsx` (`RealConnectionForm`), copy keys `web.conn.*`. The development adapter keeps the prototype's metadata-only form.

Same dialog, same fields and order, with these differences:

- **Provider** lists the connectors in the workspace catalog (for example "CRM (test API)") instead of the prototype's fixed list.
- **Auth method** is read-only: the connector decides it.
- **API key** (password field) appears below the two selects for API-key connectors. The prototype's hint "Do not enter real secrets" is replaced by `web.conn.formHint`.
- **Shared connection** is offered only for app-identity connectors (member-identity ones such as Feishu Docs are per member).
- A note under the workmate list explains that shared connections are used only by the bound workmates.

The connection card shows "Connected" for active connections and a rule line (`web.conn.bindingRule` or `web.conn.memberRule`) instead of "Association is a prototype record".

- **Installing a connector from the dialog:** when the workspace has not installed the chosen connector yet and the user may install it, its settings appear as extra fields (Server URL, OAuth client ID, OAuth client secret as a password field).
- **OAuth connectors:** a note says the user continues at the service after saving; Save then leaves for the provider. The card shows an **Authorize** button (primary) to the connection's owner while it needs authorization. On return, a toast reports authorized / cancelled / not accepted / expired link.
- **Task waiting for authorization:** under the existing "needs access" text, a note that the task resumes by itself, an **Open connections** button, then Try again.

**For review:** whether the auth method should be shown at all when it is fixed by the connector; whether connector installation belongs in this dialog or in a separate admin screen.

## 2d. Channels on the real API (P-09)

- **Binding preview:** for admins, a note "Callback URL (set it in the platform console)" with the URL in monospace (selectable). For dialogue bindings, a secondary **Link my chat account** button opens a small dialog with the message to send to the bot (`link ABCD2345`, monospace).
- **Workbench vocabulary:** new stage tags "Account not linked", "Not addressed to the bot", "Account linked", "Not accepted"; execution "Not started", "Needs authorization"; delivery "No reply", "Queued", "Unconfirmed", "Blocked". They reuse the existing tag styles. Error lines explain the reason (for example a reply held back because the bot changed after the message arrived).
- The "Simulate incoming message" control stays development-adapter only.

**For review:** whether linking belongs in Settings (per member) rather than in each binding's preview.

## 3. Changed wording (approved, decision 31 / Q-17, D-02)

Source: `src/i18n/overrides.ts`. Same position, similar length. Prototype-only claims (browser storage, "this prototype") are replaced:

| Key / original | New English | New Chinese |
| --- | --- | --- |
| About this prototype | About WorkX | 关于 WorkX |
| 保存在此浏览器中，随时可以编辑。 | Saved to this workspace. You can edit it anytime. | 保存在当前空间中，随时可以编辑。 |
| About dialog description | WorkX brings workmates, tasks, projects, and results together for individuals and teams. | WorkX 让个人与团队与智能伙伴协作，统一管理任务、项目与成果。 |
| About dialog data note | Data belongs to the current workspace. Connections to Feishu, WeCom, and AI execution depend on your workspace configuration. | 数据归属当前空间；… |
| `spaces.local` | Data, members, and connections belong to this workspace. Secrets are stored encrypted and never shown again. | 数据、成员与连接归属当前空间；… |
| `spaces.accountHint` | Your email is used for sign-in and invitations. Contact support to change it. | 邮箱用于登录与接收邀请，… |
| `saas.boundary` | Workspace roles manage the organization. Access to content is granted per resource. | 空间角色负责组织管理；… |
| `saas.memberNote` | Deactivating a member ends their sessions and stops tasks they started. | 停用成员会结束其登录会话，… |
| Automation note | Scheduled runs start once the scheduler is enabled for this workspace. You can create and pause automations now. | 空间启用调度服务后才会按时执行；… |

Copy that describes **simulated** behavior is not reworded. It is shown only while the development adapter is active (`runtime.simulated`): demo badges, "Simulate incoming message", "Replay same event", connection-test simulation and the simulated-answer footnote.

**For review:** the automation note promises a scheduler that does not exist yet. Keep it, or hide the note until the scheduler ships.

## 4. Other added states

Keys prefixed `web.` in `src/i18n/additions.ts`, rendered with the prototype's `.empty-state` pattern: loading, load error with retry, page not available, request failed. Also the model caption and the chat footnote shown when execution is not simulated.

## 5. Fidelity results and deviations

Run on 2026-10-31 in the cloud environment, with the prototype served with the D-04 colour applied. Desktop web only:

- **Viewports:** 1440×900 and 1280×800.
- **Locales:** en and zh-CN.
- **States:** the catalog has 70 states. One is mobile-only and skipped. One (collapsed sidebar) runs only at 1440, so there are 69 states at 1440×900 and 68 at 1280×800.
- **Captures:** 274 per target, 0 capture failures, 0 horizontal overflow, 0 console errors.

| Verdict | Count | States |
| --- | --- | --- |
| Pass (≤0.5% pixels differ) | 272 | All others; largest difference 0.33% (`agent-detail-context`, Knowledge section) |
| Approved deviation | 0 triggered | `agent-detail-context`, `library`, `library-preview` are recorded under decision 30 but currently stay under the pass threshold |
| **Proposed deviation (needs review)** | 2 | `channel-compose` at 1280×800 (en, zh-CN), about 3.1%. See below. |
| Fail | 0 | |

**Proposed deviation: compose dialog scroll position.**
- **What differs:** at 1280×800 the "Simulate incoming message" dialog is taller than the viewport. After "Use demo message", the prototype rebuilds the dialog's HTML and its scroll jumps back to the top, moving the button away from the pointer. The React dialog keeps the user's scroll position.
- **Scope:** 1440×900 is pixel-identical.
- **Recommendation:** accept the React behavior. Matching it would mean reproducing the jump. This dialog is a development-adapter control only.
- **Recorded in:** `tools/ui-fidelity/approved-deviations.json` with `status: "proposed"`.
