# WorkX web app

React + TypeScript production frontend. The approved prototype (`workmates-prototype/dist`) is the visual baseline; rules are in `docs/architecture/15-UI-FIDELITY.md`.

## Modes

| Command | Backend | Use |
| --- | --- | --- |
| `pnpm dev` | Development adapter (in-browser, simulated execution, seeded with prototype data) | Local UI work |
| `pnpm dev:fidelity` | Development adapter + test-only seed route `/__test__/seed` | Visual comparison (`tools/ui-fidelity`) |
| `pnpm build:demo` / `pnpm preview:demo` | Development adapter, no test seed | Shareable demo build |
| `pnpm build` | FastAPI control plane over `/api/v1` (`VITE_API_MODE=http`) | Production. Refuses test seeding; `scripts/check-production-bundle.mjs` fails if adapter, fixture or seed code is bundled |

The FastAPI backend does not exist yet, so a production build shows the load-error state until it does. See `docs/BACKEND-INTEGRATION.md`.

## Structure

- `src/styles/prototype/` — prototype stylesheets, verbatim except the approved `--muted` color (D-04).
- `src/ui/` — icons (generated from the prototype), overlay host (modal/popover), toast.
- `src/i18n/` — converted prototype dictionaries (`pnpm messages:convert`), approved wording overrides, copy for new states.
- `src/api/` — contracts, transports (HTTP and the development adapter), query hooks.
- `src/dev-backend/` — development adapter (never in production builds) and the gated test seed.
- `src/app/` — router, workspace context (navigation and workspace switching), layout, keyboard handling.
- `src/features/<screen>/` — one module per prototype screen.

## Checks

```bash
pnpm typecheck && pnpm test && pnpm build
```
