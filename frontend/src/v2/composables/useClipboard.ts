import { ref } from 'vue'

/**
 * 剪贴板复制 composable — 带成功反馈状态。
 *
 * 用法：
 *   const { copied, copy } = useClipboard()
 *   await copy('要复制的文本')
 *   copied.value // true（1.5 秒后自动恢复 false）
 */

export function useClipboard(duration = 1500) {
  const copied = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null

  async function copy(text: string): Promise<boolean> {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        // 回退方案：用临时 textarea + execCommand
        const ta = document.createElement('textarea')
        ta.value = text
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      copied.value = true
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => { copied.value = false }, duration)
      return true
    } catch {
      return false
    }
  }

  return { copied, copy }
}