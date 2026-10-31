#!/usr/bin/env node
// Fails the production build if development-only or test-only code reached the bundle.
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';

const dir = new URL('../dist/assets/', import.meta.url).pathname;
const markers = [
  ['/__test__/fidelity/seed', 'test seed route'],
  ['__test__/seed', 'test seed entry'],
  ['workx-dev-backend-v1', 'development adapter storage'],
  ['我的智能伙伴', 'prototype seed fixture data'],
];
const files = (await readdir(dir)).filter(f => f.endsWith('.js'));
const problems = [];
for (const file of files) {
  const text = await readFile(join(dir, file), 'utf8');
  for (const [marker, what] of markers) if (text.includes(marker)) problems.push(`${file}: contains ${what} (${marker})`);
}
if (problems.length) {
  console.error('Production bundle check failed:\n' + problems.join('\n'));
  process.exit(1);
}
console.log(`Production bundle check passed (${files.length} files; no development adapter, fixture, or test seed code).`);
