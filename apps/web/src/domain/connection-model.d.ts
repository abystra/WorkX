// Types for the verbatim prototype port in connection-model.js.
/* eslint-disable @typescript-eslint/no-explicit-any */
export interface ConnectionDraft { params: Record<string, any>; confirmed: string[]; test: any }
export const CONNECTION_DOCS: Record<string, any>;
export function connectionSignature(binding: any): string;
export function connectionSpec(binding: any, params?: Record<string, any>): any;
export function demoConnectionParams(binding: any, params?: Record<string, any>): Record<string, any>;
export function validateConnection(binding: any, draft: ConnectionDraft): any;
export function sanitizeConnection(binding: any, draft: ConnectionDraft, testResult?: any): any;
export function initialConnectionDraft(binding: any): ConnectionDraft;
export function reconcileConnection(previous: any, next: any): any;
