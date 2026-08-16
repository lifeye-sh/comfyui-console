export type TaskItem = {
  id: number; batch_id: number; row_no: number; generation_type_id: number | null; workflow_version_id: number | null
  params: Record<string, unknown>; status: string; priority: number; node_id: number | null; prompt_id: string | null
  retries: number; error: string | null; started_at: string | null; finished_at: string | null; created_at: string
  workflow_param_schema?: Array<{ key: string; label?: string; type?: string; options?: Array<{label:string;value:unknown}>; options_from?: string }>
}
export type TaskEvent = { id: number; type: string; progress: number; payload: Record<string, unknown>; created_at: string }
export type TaskOutput = { id: number; filename: string; media_type: 'image' | 'video' | 'audio'; mime: string; thumbUrl?: string; fileUrl?: string; width?: number | null; height?: number | null; duration?: number | null }
export type GenerationTypeItem = { id: number; code: string; name: string; media_type: string; param_schema?: Array<{ key: string; label?: string; type?: string; options?: Array<{label:string;value:unknown}>; options_from?: string }> }
export type DashboardSummary = {
  generated_at: string
  tasks: { total: number; today: number; active: number; success: number; failed: number; success_rate: number; status_counts: Record<string, number> }
  nodes: { total: number; online: number; capacity: number; items: Array<{ id: number; name: string; status: string; last_seen_at?: string; max_concurrent: number }> }
  resources: { total: number; image: number; video: number; audio: number }
  workflows: { total: number; generation_types: number; configured_types: number }
  trend: Array<{ date: string; total: number; success: number; failed: number }>
  recent_tasks: Array<{ id: number; status: string; generation_type_name: string; prompt?: string; created_at: string }>
}

export const statusMeta: Record<string, { label: string; tone: 'neutral' | 'success' | 'warning' | 'danger' | 'info' }> = {
  DRAFT:{label:'草稿',tone:'neutral'}, PENDING:{label:'等待中',tone:'warning'}, DISPATCHING:{label:'分配中',tone:'info'}, QUEUED:{label:'已入队',tone:'info'}, RUNNING:{label:'执行中',tone:'info'}, FINALIZING:{label:'处理中',tone:'info'}, SUCCESS:{label:'成功',tone:'success'}, FAILED:{label:'失败',tone:'danger'}, CANCELLED:{label:'已取消',tone:'neutral'},
}
export const activeStatuses = ['PENDING','DISPATCHING','QUEUED','RUNNING','FINALIZING']
function localDateInput(date: Date) { return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}` }
function parseServerDate(value: string) { return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`) }
export function formatDate(value?: string | null) { if (!value) return '—'; const date = parseServerDate(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12:false }) }
export function todayRange() { const from = new Date(); from.setHours(0,0,0,0); const to = new Date(from); to.setDate(to.getDate()+1); return { from: from.toISOString(), to: to.toISOString(), date: localDateInput(from) } }
export function flattenGenerationMenu(menu: Record<string, GenerationTypeItem[]>): GenerationTypeItem[] { return [...(menu.image||[]),...(menu.video||[]),...(menu.audio||[])] }
