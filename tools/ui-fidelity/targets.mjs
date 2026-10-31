// How to put each UI implementation into a catalog state.
// The prototype stores everything in localStorage, so a fresh browser context is a fresh seed.
export const TARGETS = {
  prototype: {
    defaultBase: 'http://127.0.0.1:4173',
    async prepare(page, { locale }) {
      await page.addInitScript(l => {
        try { if (!sessionStorage.getItem('fidelity-init')) { localStorage.setItem('workx-locale', l); sessionStorage.setItem('fidelity-init', '1'); } } catch {}
      }, locale);
    },
    async open(page, { base, state }) {
      await page.goto(`${base}/#${state.route}`);
      await page.waitForLoadState('networkidle');
    },
  },

  // Production web app (apps/web). Not implemented yet: it needs the test-only seed and login
  // endpoints described in docs/architecture/15-UI-FIDELITY.md §6 (backlog B-UI-02).
  web: {
    defaultBase: 'http://127.0.0.1:5173',
    async prepare() {
      throw new Error('web target not available yet: apps/web and its fidelity seed endpoint (B-UI-02) do not exist');
    },
    async open() {},
  },
};
