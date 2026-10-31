# UI fidelity tooling

The prototype in `workmates-prototype/dist/` is the approved design baseline. This tool captures it in named states and compares the production web app against it. Rules, inventory, migration map, and acceptance criteria are in [docs/architecture/15-UI-FIDELITY.md](../../docs/architecture/15-UI-FIDELITY.md).

| File | Purpose |
| --- | --- |
| `states.mjs` | Catalog of 63 named UI states (62 desktop) with the steps that reach them through `data-action` hooks, and the target module/route for each |
| `targets.mjs` | How to prepare and open each implementation (`prototype` works; `web` waits for the test seed endpoint, backlog B-UI-02) |
| `capture.mjs` | Screenshots every state per locale and viewport; reports failed steps, console errors, horizontal overflow |
| `compare.mjs` | Pixel comparison with pass ≤ 0.5 %, review ≤ 3 %, fail above; honors `approved-deviations.json` |
| `contact-sheet.mjs` | HTML review sheet, optionally baseline / candidate / diff side by side |
| `export-fixture.mjs` | Exports the prototype's seeded data to `fixtures/prototype-seed.json` for the production seed endpoint |

## Run locally

Node 20+.

```bash
npm ci
```

```bash
npx playwright install chromium
```

Start the prototype in one terminal:

```bash
npm run prototype:serve
```

Capture the baseline (desktop, en + zh-CN) and build the review sheet:

```bash
npm run capture:prototype
```

```bash
npm run contact-sheet
```

When `apps/web` and its seed endpoint exist:

```bash
npm run capture:web -- --base http://127.0.0.1:5173
```

```bash
npm run compare
```

```bash
node contact-sheet.mjs --in out/prototype --candidate out/web --diff out/diff --out out/review.html
```

Scope is the desktop web browser (1440×900; add `--viewports desktop,laptop` for the 1280×800 check). Output goes to `out/` (git-ignored); the baseline is reproducible, so screenshots are not committed.
