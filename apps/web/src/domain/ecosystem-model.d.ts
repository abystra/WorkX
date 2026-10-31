// Types for the verbatim prototype port in ecosystem-model.js. Lookups mirror the prototype and
// are loosely typed because callers pass ids that the rules have already validated.
/* eslint-disable @typescript-eslint/no-explicit-any */
export interface PlatformDef { id: string; name: string; type: string; description: string; icon: string }
export interface CapabilityDef { id: string; name: string; description: string; group: string }
export interface MethodDef { id: string; platform: string; name: string; description: string; kind: string; required: string[]; optional: string[] }
export const PLATFORMS: PlatformDef[];
export const CAPABILITIES: CapabilityDef[];
export const METHODS: MethodDef[];
export function platformBy(id: string | undefined): any;
export function methodBy(id: string | undefined): any;
export function capabilityBy(id: string | undefined): any;
export function normalizeCapabilities(methodId: string | undefined, selected?: unknown): string[];
export function bindingIsReady(binding: any, data: any): boolean;
export function ensureEcosystemData(data: any): void;
