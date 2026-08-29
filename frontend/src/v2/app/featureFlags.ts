const truthyValues = new Set(['1', 'true', 'yes', 'on'])
const falseyValues = new Set(['0', 'false', 'no', 'off'])

function envFlag(value: string | undefined, defaultValue: boolean): boolean {
  const normalized = String(value || '').trim().toLowerCase()
  if (truthyValues.has(normalized)) return true
  if (falseyValues.has(normalized)) return false
  return defaultValue
}

/**
 * V2 is the default UI. Deployments can still explicitly disable it for rollback.
 */
export function isV2Enabled(): boolean {
  const enabled = envFlag(import.meta.env.VITE_UI_V2_ENABLED, true)
  if (!enabled) return false
  const rollout = Number(import.meta.env.VITE_UI_V2_ROLLOUT_PERCENT ?? 100)
  if (!Number.isFinite(rollout) || rollout >= 100) return true
  if (rollout <= 0) return false
  const key = localStorage.getItem('cc_v2_rollout_key') || crypto.randomUUID()
  localStorage.setItem('cc_v2_rollout_key', key)
  let hash = 0
  for (const char of key) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return hash % 100 < rollout
}

export function preferV2(): boolean {
  if (!isV2Enabled()) return false
  const preference = localStorage.getItem('cc_ui_preference')
  if (preference === 'v1') return false
  if (preference === 'v2') return true
  return envFlag(import.meta.env.VITE_UI_V2_DEFAULT, true)
}

export function setUiPreference(version: 'v1' | 'v2'): void {
  localStorage.setItem('cc_ui_preference', version)
}

export function isShortDramaEnabled(): boolean {
  return isV2Enabled() && envFlag(import.meta.env.VITE_UI_V2_1_SHORT_DRAMA_ENABLED, true)
}

/**
 * V3 AI 导演前期制作模块（实验）。默认关闭，灰度开放。
 */
export function isV3DirectorEnabled(): boolean {
  return isShortDramaEnabled() && envFlag(import.meta.env.VITE_V3_DIRECTOR_ENABLED, false)
}
