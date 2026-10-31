// Persistent state of the development adapter. Shape matches the prototype's `workx-spaces-v1` root so
// the prototype's seed (tools/ui-fidelity/fixtures/prototype-seed.json) loads unchanged.
import seed from './fixtures/prototype-seed.json';

export const DEV_STORAGE_KEY = 'workx-dev-backend-v1';

/* eslint-disable @typescript-eslint/no-explicit-any */
export type SpaceData = Record<string, any> & {
  tenantId: string;
  spaceType: 'personal' | 'organization';
  enterprise: { id: string; name: string };
};
export interface Space { id: string; type: 'personal' | 'organization'; name: string; data: SpaceData }
export interface Root {
  schemaVersion: number;
  user: { id: string; name: string; email: string; notifications: boolean };
  activeSpaceId: string;
  spaces: Space[];
}

export const freshSeed = (): Root => structuredClone(seed) as Root;

export function loadRoot(): Root {
  try {
    const saved = JSON.parse(localStorage.getItem(DEV_STORAGE_KEY) || 'null');
    if (saved?.schemaVersion === 1 && Array.isArray(saved.spaces)) return saved;
  } catch { /* fall back to seed */ }
  return freshSeed();
}

export function saveRoot(root: Root) {
  try { localStorage.setItem(DEV_STORAGE_KEY, JSON.stringify(root)); } catch { /* storage unavailable: keep in memory */ }
}
