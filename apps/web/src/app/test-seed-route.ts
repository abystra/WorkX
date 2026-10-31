// Test-only entry: /__test__/seed?fixture=prototype&next=/t/wx-demo/home
// Loaded only when VITE_ENABLE_TEST_SEED === 'true'; absent from production bundles.
import type { Transport } from '@/api/transport';

export async function runTestSeed(transport: Transport) {
  const params = new URLSearchParams(window.location.search);
  await transport.request('POST', '/__test__/fidelity/seed', { fixture: params.get('fixture') || 'prototype' });
  const next = params.get('next') || '/';
  window.history.replaceState(null, '', next.startsWith('/') && !next.startsWith('//') ? next : '/');
}
