export type MediaType = 'image' | 'video' | 'audio'

export type ParameterConfig = {
  key: string
  type: string
  label: string
  group?: 'parameter' | 'media'
  media_order?: number
  multiple?: boolean
  max_items?: number
  default?: unknown
  required?: boolean
  min?: number
  max?: number
  step?: number
  unit?: string
  help?: string
  options?: Array<{ label: string; value: unknown }>
  options_from?: string
  visible_when?: { key: string; operator: 'equals' | 'not_equals' | 'truthy'; value?: unknown }
}

export type GenerationConfig = {
  schema_version: number
  basic: { name: string; code: string; media_type: MediaType; menu_order: number }
  page: { title: string; description: string; icon?: string; layout?: 'list' | 'cards' }
  parameters: ParameterConfig[]
  parameter_schemes: Array<{ id: string; name: string; is_default: boolean; params: Record<string, unknown> }>
  workflow_bindings: Array<{ workflow_id?: number; workflow_version_id: number; is_default: boolean }>
  workflow_mapping_presets?: Array<{
    id: string
    name: string
    workflow_id?: number
    workflow_version_id?: number
    mappings: Array<{ key: string; node: string; path: string }>
    output_mapping: Record<string, unknown>
  }>
  outputs: { media_type: MediaType; multiple: boolean; naming_pattern?: string }
}

export type ConfigIssue = { path: string; code: string; message: string }
export type ConfigValidation = {
  valid: boolean
  errors: ConfigIssue[]
  warnings: ConfigIssue[]
  workflow_checks: Array<{ workflow_version_id: number; valid: boolean; missing_parameters: string[] }>
}

export type ConfigVersion = {
  id: number
  generation_type_id: number
  version: number
  status: string
  config: GenerationConfig
  validation_errors: ConfigIssue[]
  source_version_id: number | null
  published_at: string | null
  updated_at: string
}

export const parameterTypes = [
  ['textarea', '多行文本'], ['text', '单行文本'], ['int', '整数'], ['float', '小数'],
  ['bool', '开关'], ['select', '下拉选择'], ['seed', '随机种子'], ['size', '尺寸'],
  ['image', '图片'], ['video', '视频'], ['audio', '音频'], ['slider', '滑块'],
] as const

export function cloneConfig<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}
