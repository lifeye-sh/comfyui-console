import type { ParameterConfig, RuntimeWorkflow } from '../generation-config/model'

export type SelectSettings = Record<string, { label?: string; options: Array<{label: string; value: any}>; default_value?: any }>
export function parameterOptions(parameter: ParameterConfig, settings: SelectSettings) {
  return parameter.options || settings[parameter.options_from || '']?.options || []
}
export function parameterVisible(parameter: ParameterConfig, params: Record<string, any>) {
  const rule = parameter.visible_when
  if (rule) {
    const value = params[rule.key]
    if (rule.operator === 'truthy' && !value) return false
    if (rule.operator === 'equals' && value !== rule.value) return false
    if (rule.operator === 'not_equals' && value === rule.value) return false
  }
  const reference = parameter.key.match(/^reference_image_(\d)$/)
  return !reference || (!!params.multi_reference_enabled && Number(reference[1]) <= Number(params.multi_reference_count || 1))
}
export function workflowDefaults(workflow: RuntimeWorkflow, settings: SelectSettings, sizeKey = 'image_size') {
  const params: Record<string, any> = {}
  for (const parameter of workflow.parameters) {
    const value = parameter.type === 'seed' ? Math.floor(Math.random() * 4294967295)
      : parameter.default ?? settings[parameter.options_from || '']?.default_value ?? (parameter.type === 'bool' ? false : null)
    params[parameter.key] = value == null ? value : JSON.parse(JSON.stringify(value))
  }
  const size = settings[sizeKey]?.default_value
  if (size && workflow.parameters.some(p => p.key === 'width') && workflow.parameters.some(p => p.key === 'height')) {
    const [width, height] = String(size).split('x').map(Number)
    if (width && height) Object.assign(params, {width, height, __size: String(size)})
  }
  return params
}
export function promptParameter(parameters: ParameterConfig[]) {
  return parameters.find(p => ['text', 'textarea'].includes(p.type) && /prompt/i.test(p.key) && !/negative/i.test(p.key))
    || parameters.find(p => p.type === 'textarea' && !/negative/i.test(p.key))
}
export function workflowValidation(parameters: ParameterConfig[], params: Record<string, any>) {
  for (const parameter of parameters) {
    if (!parameterVisible(parameter, params)) continue
    const value = params[parameter.key]
    if (parameter.required && (value == null || (typeof value === 'string' && !value.trim()) || (Array.isArray(value) && !value.length))) return `请填写${parameter.label || parameter.key}`
    if (Array.isArray(value) && parameter.max_items && value.length > parameter.max_items) return `${parameter.label}最多选择${parameter.max_items}项`
  }
  return ''
}
export function workflowPayload(parameters: ParameterConfig[], params: Record<string, any>) {
  const result: Record<string, any> = {}
  for (const parameter of parameters) {
    if (!parameterVisible(parameter, params)) continue
    const value = params[parameter.key]
    if (value != null && value !== '') result[parameter.key] = value
    if (parameter.type === 'image' && value && params[`${parameter.key}__mask`]) result[`${parameter.key}__mask`] = params[`${parameter.key}__mask`]
  }
  return result
}
export function migrateWorkflowParams(previous: ParameterConfig[], next: ParameterConfig[], params: Record<string, any>) {
  const result: Record<string, any> = {}; const used = new Set<string>()
  for (const parameter of next) {
    const old = previous.find(p => !used.has(p.key) && p.key === parameter.key && p.type === parameter.type && !!p.multiple === !!parameter.multiple)
      || (['image','video','audio'].includes(parameter.type) ? previous.find(p => p.type === parameter.type && !!p.multiple === !!parameter.multiple && !used.has(p.key) && !next.some(n => n.key === p.key && n.type === p.type && !!n.multiple === !!p.multiple)) : undefined)
    if (old && params[old.key] !== undefined) {
      used.add(old.key); result[parameter.key] = params[old.key]
      if (parameter.type === 'image' && params[`${old.key}__mask`]) result[`${parameter.key}__mask`] = params[`${old.key}__mask`]
    }
  }
  return result
}
