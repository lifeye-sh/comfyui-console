const truthyValues = new Set(['1', 'true', 'yes', 'on'])

/**
 * V2 is deliberately build-time opt-in during the isolated development phase.
 * With no environment variable (the production default), V1 behaves exactly as before.
 */
export function isV2Enabled(): boolean {
  const enabled = truthyValues.has(String(import.meta.env.VITE_UI_V2_ENABLED || '').trim().toLowerCase())
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
  return isV2Enabled() && localStorage.getItem('cc_ui_preference') === 'v2'
}

export function setUiPreference(version: 'v1' | 'v2'): void {
  localStorage.setItem('cc_ui_preference', version)
}
