import { onUnmounted } from 'vue'
import { getAccessToken } from '@/api/client'
import { resourceApi } from '@/api/modules'
import type { TaskOutput } from './model'

export function useTaskOutputThumbs() {
  const objectUrls = new Set<string>()
  const maxConcurrent = 4
  let active = 0
  const waiting: Array<() => void> = []

  async function limited<T>(operation: () => Promise<T>): Promise<T> {
    if (active >= maxConcurrent) await new Promise<void>(resolve => waiting.push(resolve))
    active += 1
    try { return await operation() }
    finally { active -= 1; waiting.shift()?.() }
  }

  async function withThumbs(items: TaskOutput[]): Promise<TaskOutput[]> {
    return Promise.all(items.map(item => limited(async () => {
      if (item.media_type === 'audio' || item.media_type === 'text') return item
      try {
        const options: RequestInit = { headers: { Authorization: `Bearer ${getAccessToken() || ''}` }, cache: 'default' }
        const response = await fetch(resourceApi.thumbUrl(item.id), options)
        // Never fall back to the original asset in a list. Decoding several
        // 4K/8K images on the main thread can freeze the entire page.
        if (!response.ok) return item
        const thumbUrl = URL.createObjectURL(await response.blob()); objectUrls.add(thumbUrl)
        return { ...item, thumbUrl, fileUrl: resourceApi.fileUrl(item.id) }
      } catch { return item }
    })))
  }
  function release(items?: TaskOutput[]) { for (const item of items || []) if (item.thumbUrl?.startsWith('blob:')) { URL.revokeObjectURL(item.thumbUrl); objectUrls.delete(item.thumbUrl) } }
  onUnmounted(() => { objectUrls.forEach(URL.revokeObjectURL); objectUrls.clear() })
  return { withThumbs, release }
}
