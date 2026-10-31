# WorkX web app

React + TypeScript production frontend. The approved prototype (`workmates-prototype/dist`) is the visual baseline; rules are in `docs/architecture/15-UI-FIDELITY.md`.

## Modes

| Command | Backend | Use |
| --- | --- | --- |
| `pnpm dev` | Development adapter (in-browser, simulated execution, seeded with prototype data) | Local UI work |
| `pnpm dev:fidelity` | Development adapter + test-only seed route `/__test__/seed` | Visual comparison (`tools/ui-fidelity`) |
| `pnpm build:demo` / `pnpm preview:demo` | Development adapter, no test seed | Shareable demo build |
| `pnpm dev:api` | Real API on :8000 via proxy (`VITE_API_MODE=http`, port 5174); start everything with `scripts/dev/stack.sh start` | Local work against the backend |
| `pnpm build` | Control plane over `/api/v1` (`VITE_API_MODE=http`) | Production. Refuses test seeding; `scripts/check-production-bundle.mjs` fails if adapter, fixture or seed code is bundled |

What the real API serves today, and what still waits for later phases, is in `docs/BACKEND-INTEGRATION.md`.

## Structure

- `src/styles/prototype/` — prototype stylesheets, verbatim except the approved `--muted` color (D-04).
- `src/ui/` — icons (generated from the prototype), overlay host (modal/popover), toast.
- `src/i18n/` — converted prototype dictionaries (`pnpm messages:convert`), approved wording overrides, copy for new states.
- `src/api/` — contracts, transports (HTTP and the development adapter), query hooks.
- `src/dev-backend/` — development adapter (never in production builds) and the gated test seed.
- `src/app/` — router, workspace context (navigation and workspace switching), layout, keyboard handling.
- `src/features/<screen>/` — one module per prototype screen.
- `src/features/auth/`, `src/features/knowledge/`, `src/styles/web/` — new screens without a prototype reference (account screens, Knowledge). Documented for design review in `docs/NEW-SCREENS.md`.
- `tests/e2e/` — browser checks for the new screens (Playwright, against `pnpm dev:fidelity`).

## Checks

Type check, unit tests, and the production build with its bundle check:

```bash
pnpm typecheck && pnpm test && pnpm build
```

Browser checks for the new screens need the fidelity server running (`pnpm dev:fidelity`):

```bash
node tests/e2e/account-screens.mjs && node tests/e2e/knowledge.mjs
```

Journeys against the real API (needs `scripts/dev/stack.sh start`):

```bash
node tests/e2e/real-backend.mjs --mail ../../.local/run/mail
```

Visual comparison against the prototype (serve the prototype on :4173 first) is described in `tools/ui-fidelity/README.md`; run it with `--viewports desktop,laptop` for the 1440×900 and 1280×800 check.

## Docs

- `docs/BACKEND-INTEGRATION.md` lists every endpoint the UI calls, what the development adapter simulates, and the transport work needed before connecting the real API.
- `docs/NEW-SCREENS.md` covers new screens, approved wording changes, fidelity results and deviations.
