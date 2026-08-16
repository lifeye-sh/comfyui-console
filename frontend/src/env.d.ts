/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_UI_V2_ENABLED?: string
  readonly VITE_UI_V2_ROLLOUT_PERCENT?: string
  readonly VITE_UI_V2_DEFAULT?: string
  readonly VITE_UI_V2_1_SHORT_DRAMA_ENABLED?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}
