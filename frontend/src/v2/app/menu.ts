export type V2MenuItem = {
  key: string
  label: string
  icon: string
  to?: string
  adminOnly?: boolean
  children?: V2MenuItem[]
}

export type GenerationMenu = Record<'image' | 'video' | 'audio', Array<{ code: string; name: string }>>

export function buildV2Menu(generationMenu?: Partial<GenerationMenu>): V2MenuItem[] {
  const generationGroups = (['image', 'video', 'audio'] as const).map((media) => ({
    key: `creation-${media}`,
    label: media === 'image' ? '图片生成' : media === 'video' ? '视频生成' : '音频生成',
    icon: media === 'image' ? '▧' : media === 'video' ? '▷' : '♪',
    children: (generationMenu?.[media] || []).map((type) => ({ key: `generate-${type.code}`, label: type.name, icon: '·', to: `/v2/generate/${type.code}` })),
  })).filter(group => group.children.length)

  return [
    { key: 'overview', label: '系统概览', icon: '⌂', to: '/v2' },
    { key: 'creation', label: '创作生成', icon: '✦', children: generationGroups.length ? generationGroups : [{ key: 'generate-empty', label: '生成类型加载中', icon: '·' }] },
    { key: 'tasks', label: '任务中心', icon: '☷', children: [{ key: 'task-list', label: '任务管理', icon: '·', to: '/v2/tasks' }, { key: 'batches', label: '批次任务', icon: '·', to: '/v2/batches' }] },
    { key: 'assets', label: '素材中心', icon: '◇', children: [{ key: 'library', label: '素材库', icon: '·', to: '/v2/assets' }, { key: 'asset-picker', label: '素材选择器', icon: '·', to: '/v2/assets/picker' }, { key: 'reference-video', label: '参考视频', icon: '·', to: '/v2/reference-videos' }, { key: 'prompt-library', label: '提示词库', icon: '·', to: '/v2/prompts' }, { key: 'recycle', label: '回收站', icon: '·', to: '/v2/recycle-bin' }] },
    { key: 'workflows', label: '工作流中心', icon: '⌘', children: [{ key: 'workflow-list', label: '工作流管理', icon: '·', to: '/v2/workflows' }, { key: 'schemes', label: '参数方案', icon: '·', to: '/v2/parameter-schemes' }] },
    { key: 'system', label: '系统配置', icon: '⚙', adminOnly: true, children: [{ key: 'generation-types', label: '生成类型配置', icon: '·', to: '/v2/settings/generation-types' }, { key: 'nodes', label: '运行监控', icon: '·', to: '/v2/settings/nodes' }, { key: 'users', label: '用户与权限', icon: '·', to: '/v2/settings/users' }, { key: 'settings', label: '系统设置', icon: '·', to: '/v2/settings/system' }, { key: 'audit', label: '审计日志', icon: '·', to: '/v2/settings/audit' }] },
  ]
}

export function filterV2Menu(items: V2MenuItem[], role?: string): V2MenuItem[] {
  return items.filter((item) => !item.adminOnly || role === 'admin').map((item) => ({ ...item, children: item.children ? filterV2Menu(item.children, role) : undefined }))
}
