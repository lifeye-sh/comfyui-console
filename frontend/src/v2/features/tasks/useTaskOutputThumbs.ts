import { onUnmounted } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import type { TaskOutput } from './model'

export function useTaskOutputThumbs() {
  const objectUrls = new Set<string>()
  async function withThumbs(items: TaskOutput[]): Promise<TaskOutput[]> {
    return Promise.all(items.map(async item => {
      if (item.media_type === 'audio') return item
      try {
        const options: RequestInit = { headers: { Authorization: `Bearer ${getAccessToken() || ''}` }, cache: 'no-store' }
        let response = await fetch(`${resourceApi.thumbUrl(item.id)}?v=${Date.now()}`, options)
        // 图片缩略图尚未生成时直接读取原图，避免任务刚完成时出现空白或旧图。
        if (!response.ok && item.media_type === 'image') response = await fetch(`${resourceApi.fileUrl(item.id)}?v=${Date.now()}`, options)
        if (!response.ok) return item
        const thumbUrl = URL.createObjectURL(await response.blob()); objectUrls.add(thumbUrl)
        return { ...item, thumbUrl, fileUrl: resourceApi.fileUrl(item.id) }
      } catch { return item }
    }))
  }
  function release(items?: TaskOutput[]) { for (const item of items || []) if (item.thumbUrl?.startsWith('blob:')) { URL.revokeObjectURL(item.thumbUrl); objectUrls.delete(item.thumbUrl) } }
  onUnmounted(() => { objectUrls.forEach(URL.revokeObjectURL); objectUrls.clear() })
  return { withThumbs, release }
}
