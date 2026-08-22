<script setup lang="ts">
import { computed } from 'vue'
import { useClipboard } from '@/v2/composables/useClipboard'

const props = defineProps<{
  text: string
  /** 按钮大小，默认跟随上下文 */
  size?: 'sm' | 'md'
  /** 自定义标签，默认"复制" */
  label?: string
}>()

const { copied, copy } = useClipboard()
const displayLabel = computed(() => props.label || '复制')
const canCopy = computed(() => Boolean(props.text))
</script>

<template>
  <button
    type="button"
    class="copy-btn"
    :class="{ sm: size === 'sm' }"
    :disabled="!canCopy"
    :title="copied ? '已复制' : '复制到剪贴板'"
    @click="copy(props.text)"
  >
    {{ copied ? '✓ 已复制' : displayLabel }}
  </button>
</template>

<style scoped>
.copy-btn {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--v2-text-subtle, #a0abc8);
  background: rgba(130, 149, 255, 0.08);
  border: 1px solid rgba(130, 149, 255, 0.18);
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: 0.15s;
}
.copy-btn:hover:not(:disabled) {
  background: rgba(130, 149, 255, 0.16);
  color: var(--v2-text, #e8edff);
}
.copy-btn.sm {
  padding: 1px 6px;
  font-size: 10px;
}
.copy-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
</style>