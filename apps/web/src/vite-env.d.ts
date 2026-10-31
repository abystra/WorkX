/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_MODE: 'http' | 'development';
  readonly VITE_ENABLE_TEST_SEED?: 'true';
}
declare module '*.svg' { const src: string; export default src; }
