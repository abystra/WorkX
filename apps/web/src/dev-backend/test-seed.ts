// Test-only data seeding (backlog B-UI-02). Compiled in only when VITE_ENABLE_TEST_SEED === 'true'
// (fidelity mode). vite.config.ts refuses to build production with the flag set, and
// scripts/check-production-bundle.mjs fails if this code appears in a production bundle.
import type { DevBackend } from './backend';
import { freshSeed } from './store';

export const TEST_SEED_PATH = '/__test__/fidelity/seed';

export function registerTestRoutes(backend: DevBackend) {
  backend.route('POST', TEST_SEED_PATH, ({ body }) => {
    if (body.fixture !== 'prototype') throw new Error('Unknown fixture');
    backend.reset(freshSeed());
    return { ok: true, tenants: backend.root.spaces.map(s => s.id) };
  });
}
