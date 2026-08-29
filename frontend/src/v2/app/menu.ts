import { isShortDramaEnabled } from '@/v2/app/featureFlags'

export type V2MenuItem = {
  key: string
  label: string
  icon: string
  to?: string
  adminOnly?: boolean
  children?: V2MenuItem[]
}

export type GenerationMenu = Partial<Record<'image' | 'video' | 'audio' | 'tool', Array<{ code: string; name: string }>>>

export function buildV2Menu(generationMenu?: Partial<GenerationMenu>): V2MenuItem[] {
  const generationGroups = (['image', 'video', 'audio'] as const).map((media) => ({
    key: `creation-${media}`,
    label: media === 'image' ? '图片生成' : media === 'video' ? '视频生成' : '音频生成',
    icon: media === 'image' ? '�' : media === 'video' ? '▷' : '♪',
    children: (generationMenu?.[media] || []).map((type) => ({ key: `generate-${type.code}`, label: type.name, icon: '·', to: `/v2/generate/${type.code}` })),
  })).filter(group => group.children.length)

  // 工具类（图片反推、中英互译）独立分组，不归入 image/video/audio
  const toolChildren = (generationMenu?.['image'] || []).filter(_ => false) // placeholder
  const tools: Array<{ code: string; name: string }> = (generationMenu as any)?.tool || []
  const toolsGroup: V2MenuItem[] = tools.length ? [{
    key: 'creation-tools',
    label: '系统工具',
    icon: '✚',
    children: tools.map((t) => ({ key: `generate-${t.code}`, label: t.name, icon: '·', to: `/v2/generate/${t.code}` })),
  }] : []

  return [
    { key: 'overview', label: '系统概览', icon: '⌂', to: '/v2' },
    ...(isShortDramaEnabled() ? [{ key: 'drama', label: '短剧项目', icon: '▤', children: [
      { key: 'drama-projects', label: '全部项目', icon: '·', to: '/v2/drama/projects' },
      { key: 'drama-new', label: '新建短剧', icon: '·', to: '/v2/drama/new' },
    ] }] : []),
    { key: 'creation', label: '创作生成', icon: '✦', children: [...generationGroups, ...toolsGroup] },
    { key: 'tasks', label: '任务中心', icon: '☷', children: [{ key: 'task-list', label: '任务管理', icon: '·', to: '/v2/tasks' }, { key: 'batches', label: '批次任务', icon: '·', to: '/v2/batches' }] },
    { key: 'assets', label: '素材中心', icon: '◇', children: [{ key: 'library', label: '素材库', icon: '·', to: '/v2/assets' }, { key: 'asset-picker', label: '素材选择器', icon: '·', to: '/v2/assets/picker' }, { key: 'reference-video', label: '参考视频', icon: '·', to: '/v2/reference-videos' }, { key: 'prompt-library', label: '提示词库', icon: '·', to: '/v2/prompts' }, { key: 'recycle', label: '回收站', icon: '·', to: '/v2/recycle-bin' }] },
    { key: 'workflows', label: '工作流中心', icon: '⌘', children: [{ key: 'workflow-list', label: '工作流管理', icon: '·', to: '/v2/workflows' }, { key: 'schemes', label: '参数方案', icon: '·', to: '/v2/parameter-schemes' }] },
    { key: 'system', label: '系统配置', icon: '�', adminOnly: true, children: [{ key: 'generation-types', label: '生成类型配置', icon: '·', to: '/v2/settings/generation-types' }, { key: 'ai-settings', label: 'AI 模型配置', icon: '·', to: '/v2/settings/ai' }, { key: 'image-providers', label: '图片模型配置', icon: '·', to: '/v2/settings/image-providers' }, { key: 'nodes', label: '运行监控', icon: '·', to: '/v2/settings/nodes' }, { key: 'users', label: '用户与权限', icon: '·', to: '/v2/settings/users' }, { key: 'settings', label: '系统设置', icon: '·', to: '/v2/settings/system' }, { key: 'audit', label: '审计日志', icon: '·', to: '/v2/settings/audit' }] },
  ]
}

export function filterV2Menu(items: V2MenuItem[], role?: string): V2MenuItem[] {
  return items.filter((item) => !item.adminOnly || role === 'admin').map((item) => ({ ...item, children: item.children ? filterV2Menu(item.children, role) : undefined }))
}
