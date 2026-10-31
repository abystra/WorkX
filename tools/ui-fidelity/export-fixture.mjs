#!/usr/bin/env node
// Export the prototype's seeded state (after its own migration/normalization) as a JSON fixture.
// The production test seed endpoint loads an equivalent dataset so both UIs render the same content.
import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
const base = process.argv[2] || 'http://127.0.0.1:4173';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.clock.setFixedTime(new Date('2026-10-30T09:00:00+08:00'));
await page.goto(`${base}/#home`);
await page.waitForLoadState('networkidle');
// Trigger one persist without changing data: switching to the active workspace re-saves it.
await page.evaluate(() => document.querySelector('[data-action="profile"]')?.click());
await page.evaluate(() => document.querySelector('[data-action="space-switch"][data-id="wx-demo"]')?.click());
const raw = await page.evaluate(() => localStorage.getItem('workx-spaces-v1'));
await browser.close();
if (!raw) throw new Error('prototype did not persist workx-spaces-v1');
await writeFile(new URL('./fixtures/prototype-seed.json', import.meta.url), JSON.stringify(JSON.parse(raw), null, 2) + '\n');
console.log('wrote fixtures/prototype-seed.json', raw.length, 'bytes');
