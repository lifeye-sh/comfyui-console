<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { shortDramaApi } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import ManifestCompilePanel from './ManifestCompilePanel.vue'

const props = defineProps<{ projectId: number }>()

const manifests = ref<any[]>([])
const selectedManifest = ref<any>(null)
const building = ref(false)
const approving = ref(false)
const error = ref('')
const showRefs = ref<Record<number, boolean>>({})

async function load() {
  error.value = ''
  try {
    manifests.value = await shortDramaApi.directorManifests(props.projectId) as any[]
    if (manifests.value.length && !selectedManifest.value) {
      await openManifest(manifests.value[0].id)
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载清单失败'
  }
}

async function openManifest(id: number) {
  try {
    selectedManifest.value = await shortDramaApi.directorManifestDetail(props.projectId, id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载清单详情失败'
  }
}

async function build() {
  building.value = true; error.value = ''
  try {
    await shortDramaApi.directorBuildManifest(props.projectId, { notes: '' })
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '生成清单失败'
  } finally { building.value = false }
}

async function approve() {
  if (!selectedManifest.value) return
  approving.value = true; error.value = ''
  try {
    await shortDramaApi.directorApproveManifest(props.projectId, selectedManifest.value.id)
    await openManifest(selectedManifest.value.id)
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '审批失败'
  } finally { approving.value = false }
}

/** 编译任务创建或状态刷新后重新加载清单项状态 */
async function onManifestChanged() {
  if (selectedManifest.value) await openManifest(selectedManifest.value.id)
}

const statusTone = (s: string) => s === 'approved' ? 'success' : s === 'draft' ? 'info' : 'neutral'
const statusLabel = (s: string) => s === 'approved' ? '已批准' : s === 'draft' ? '草稿' : s

const itemsByType = computed(() => {
  if (!selectedManifest.value?.items) return {}
  const groups: Record<string, any[]> = {}
  for (const item of selectedManifest.value.items) {
    (groups[item.asset_type] ??= []).push(item)
  }
  return groups
})

const typeLabel: Record<string, string> = {
  character_anchor: '角色锚点',
  prop_anchor: '道具锚点',
  location_view: '地点视图',
}

function toggleRefs(itemId: number) {
  showRefs.value[itemId] = !showRefs.value[itemId]
}

onMounted(load)
watch(() => props.projectId, load)
</script>

<template>
  <GlassPanel title="生成清单 (Manifest)" description="从已批准资产自动生成版本化清单。已批准清单不可原地修改。">
    <template #actions>
      <V2Button variant="primary" :disabled="building" @click="build">{{ building ? '生成中…' : '生成清单' }}</V2Button>
    </template>

    <div v-if="error" class="wb-error">{{ error }}</div>

    <div v-if="!manifests.length" class="empty-tip">
      暂无清单。确认已批准角色/道具锚点和地点视图后，点击「生成清单」。
    </div>

    <div v-else class="manifest-section">
      <!-- Manifest 版本列表 -->
      <div class="manifest-tabs">
        <button v-for="m in manifests" :key="m.id" class="manifest-tab"
          :class="{ active: selectedManifest?.id === m.id }" @click="openManifest(m.id)">
          v{{ m.version }}
          <StatusBadge :tone="statusTone(m.status)">{{ statusLabel(m.status) }}</StatusBadge>
        </button>
      </div>

      <div v-if="selectedManifest" class="manifest-detail">
        <div class="manifest-meta">
          <span>版本: <b>v{{ selectedManifest.version }}</b></span>
          <span>状态: <StatusBadge :tone="statusTone(selectedManifest.status)">{{ statusLabel(selectedManifest.status) }}</StatusBadge></span>
          <span v-if="selectedManifest.style_bible_id">风格圣经: #{{ selectedManifest.style_bible_id }}</span>
          <span v-if="selectedManifest.approved_at">批准于 {{ new Date(selectedManifest.approved_at).toLocaleDateString() }}</span>
        </div>

        <div class="approve-row" v-if="selectedManifest.status === 'draft'">
          <V2Button variant="primary" :disabled="approving" @click="approve">{{ approving ? '审批中…' : '✅ 审批清单' }}</V2Button>
          <small>审批后清单不可修改，如需变更需生成新版本。</small>
        </div>

        <!-- 第 8 轮：编译为生产任务（仅已审批清单） -->
        <ManifestCompilePanel
          :project-id="projectId"
          :manifest-id="selectedManifest.id"
          :manifest-status="selectedManifest.status"
          @tasks-created="onManifestChanged"
          @status-refreshed="onManifestChanged"
        />

        <!-- 按类型分组的清单项 -->
        <div v-for="(items, type) in itemsByType" :key="type" class="item-group">
          <h4 class="group-title">{{ typeLabel[type] || type }}（{{ items.length }}）</h4>
          <div class="item-list">
            <div v-for="item in items" :key="item.id" class="item-card">
              <header>
                <code>{{ item.asset_stable_key }}</code>
                <small>{{ item.required_view }}</small>
                <StatusBadge :tone="item.status === 'planned' ? 'info' : 'neutral'">{{ item.status }}</StatusBadge>
              </header>
              <p class="item-prompt">{{ item.prompt }}</p>
              <div class="item-meta">
                <small>比例: {{ item.aspect_ratio }}</small>
                <small v-if="item.negative_constraints">约束: {{ item.negative_constraints }}</small>
              </div>
              <!-- 引用展开 -->
              <div v-if="item.references?.length" class="ref-section">
                <button class="ref-toggle" @click="toggleRefs(item.id)">
                  {{ showRefs[item.id] ? '收起' : '展开' }}引用（{{ item.references.length }}）
                </button>
                <div v-if="showRefs[item.id]" class="ref-list">
                  <div v-for="ref in item.references" :key="ref.id" class="ref-item">
                    <code>{{ ref.reference_type }}</code>
                    <span>{{ ref.reference_key }}</span>
                    <small v-if="ref.reference_version_id">v#{{ ref.reference_version_id }}</small>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.wb-error{padding:10px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px;margin-bottom:10px}
.empty-tip{color:var(--v2-text-subtle);font-size:12px;padding:20px 0}
.manifest-section{display:grid;gap:14px}
.manifest-tabs{display:flex;gap:6px;flex-wrap:wrap}
.manifest-tab{display:flex;align-items:center;gap:6px;padding:7px 12px;color:var(--v2-text-muted);background:transparent;border:1px solid var(--v2-border);border-radius:9px;cursor:pointer;font-size:12px}
.manifest-tab.active{color:var(--v2-text);background:rgba(130,149,255,.1);border-color:rgba(130,149,255,.35)}
.manifest-detail{display:grid;gap:14px}
.manifest-meta{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--v2-text-muted)}
.manifest-meta b{color:var(--v2-text)}
.approve-row{display:flex;align-items:center;gap:10px;padding:12px;background:rgba(79,209,165,.06);border-radius:10px}
.approve-row small{color:var(--v2-text-subtle);font-size:11px}
.item-group{display:grid;gap:8px}
.group-title{margin:0;font-size:13px;color:#e8edff;border-bottom:1px solid var(--v2-border);padding-bottom:6px}
.item-list{display:grid;gap:8px}
.item-card{padding:12px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;display:grid;gap:8px}
.item-card header{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.item-card header code{color:var(--v2-primary);font-size:11px}
.item-prompt{margin:0;font-size:12px;color:var(--v2-text);line-height:1.5}
.item-meta{display:flex;gap:12px;flex-wrap:wrap}
.item-meta small{color:var(--v2-text-subtle);font-size:10px}
.ref-section{border-top:1px solid var(--v2-border);padding-top:8px}
.ref-toggle{padding:4px 8px;color:var(--v2-primary);background:transparent;border:none;cursor:pointer;font-size:11px}
.ref-list{display:grid;gap:4px;margin-top:6px}
.ref-item{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--v2-text-muted)}
.ref-item code{color:var(--v2-primary);font-size:10px}
</style>