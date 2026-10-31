// How to put each UI implementation into a catalog state.
// The prototype stores everything in localStorage, so a fresh browser context is a fresh seed.

// Approved deviation D-04 (docs/architecture/15-UI-FIDELITY.md §5): secondary text #8f959e -> #6b7079.
// Applied to the prototype baseline so comparisons only flag unapproved differences. Pass --raw to disable.
export const MUTED_FROM = '#8f959e';
export const MUTED_TO = '#6b7079';
export function applyApprovedCss(css) {
  return css
    .replace(/--muted:#8f959e/gi, '--muted:' + MUTED_TO)
    .replace(/(^|[;{\s])color:\s*#8f959e/gi, (m, pre) => `${pre}color:${MUTED_TO}`);
}

export const TARGETS = {
  prototype: {
    defaultBase: 'http://127.0.0.1:4173',
    async prepare(page, { locale, raw }) {
      if (!raw) {
        // CSS files and inline styles in the prototype's JS templates both carry the literal.
        await page.route(/\.(css|js)$/, async route => {
          const response = await route.fetch();
          route.fulfill({ response, body: applyApprovedCss(await response.text()) });
        });
      }
      await page.addInitScript(l => {
        try { if (!sessionStorage.getItem('fidelity-init')) { localStorage.setItem('workx-locale', l); sessionStorage.setItem('fidelity-init', '1'); } } catch {}
      }, locale);
    },
    async open(page, { base, state }) {
      await page.goto(`${base}/#${state.route}`);
      await page.waitForLoadState('networkidle');
    },
  },

  // Production web app (apps/web) running in fidelity mode (`pnpm dev:fidelity`): the development adapter
  // plus the test-only seed route /__test__/seed, which is excluded from production builds.
  web: {
    defaultBase: 'http://127.0.0.1:5173',
    async prepare(page, { locale }) {
      await page.addInitScript(l => {
        try { if (!sessionStorage.getItem('fidelity-init')) { localStorage.setItem('workx-locale', l); sessionStorage.setItem('fidelity-init', '1'); } } catch {}
      }, locale);
    },
    async open(page, { base, state }) {
      const path = state.route.startsWith('settings') ? '/' + state.route : '/t/wx-demo/' + state.route;
      await page.goto(`${base}/__test__/seed?fixture=prototype&next=${encodeURIComponent(path)}`);
      await page.waitForLoadState('networkidle');
      await page.waitForSelector('#app .app-layout', { timeout: 10000 });
    },
  },
};
