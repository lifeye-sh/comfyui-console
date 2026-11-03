<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FreeShotInput } from './directorApi'

type Row = FreeShotInput & { localId: number }

const props = defineProps<{ open: boolean; disabled?: boolean }>()
const emit = defineEmits<{ close: []; submit: [FreeShotInput[]] }>()

let nextId = 0
const makeRow = (index: number): Row => ({
  localId: ++nextId,
  title: `自由镜头 ${index}`,
  visual_description: '',
  duration: 5,
  shot_size: '中景',
  camera_movement: '固定镜头',
})
const rows = ref<Row[]>([makeRow(1)])
const valid = computed(() => rows.value.length > 0 && rows.value.every(row => row.title.trim() && row.duration >= .1 && row.duration <= 600))

watch(() => props.open, (open, previous) => {
  if (open && !previous) rows.value = [makeRow(1)]
})

function addRow() {
  if (rows.value.length < 50) rows.value.push(makeRow(rows.value.length + 1))
}

function removeRow(index: number) {
  if (rows.value.length > 1) rows.value.splice(index, 1)
}

function submit() {
  if (!valid.value || props.disabled) return
  emit('submit', rows.value.map(({localId: _localId, ...row}) => ({...row, title: row.title.trim()})))
}
</script>

<template>
  <div v-if="open" class="batch-layer" role="dialog" aria-modal="true" aria-label="批量新增自由镜头">
    <section>
      <header>
        <div>
          <small>FREE SHOTS</small>
          <h2>批量新增自由镜头</h2>
          <p>每一行创建一个独立镜头；一次最多创建 50 个，提交失败时不会留下部分数据。</p>
        </div>
        <button aria-label="关闭" :disabled="disabled" @click="emit('close')"><StudioIcon name="close"/></button>
      </header>

      <div class="rows">
        <article v-for="(row,index) in rows" :key="row.localId">
          <div class="row-head">
            <b>镜头 {{ index + 1 }}</b>
            <button type="button" :disabled="disabled||rows.length===1" @click="removeRow(index)">移除</button>
          </div>
          <div class="fields">
            <label>镜头名称<input v-model="row.title" maxlength="160" :disabled="disabled" placeholder="例如：产品旋转展示"/></label>
            <label class="wide">画面描述<textarea v-model="row.visual_description" rows="3" maxlength="20000" :disabled="disabled" placeholder="描述主体、场景、动作和期望画面"/></label>
            <label>时长（秒）<input v-model.number="row.duration" type="number" min="0.1" max="600" step="0.5" :disabled="disabled"/></label>
            <label>景别<select v-model="row.shot_size" :disabled="disabled"><option>特写</option><option>近景</option><option>中景</option><option>全景</option><option>远景</option></select></label>
            <label>镜头运动<input v-model="row.camera_movement" maxlength="128" :disabled="disabled" placeholder="固定镜头 / 推镜 / 跟拍"/></label>
          </div>
        </article>
      </div>

      <button class="add-row" type="button" :disabled="disabled||rows.length>=50" @click="addRow">＋ 添加一个镜头</button>
      <footer>
        <span>共 {{ rows.length }} 个镜头</span>
        <button :disabled="disabled" @click="emit('close')">取消</button>
        <button class="primary" :disabled="disabled||!valid" @click="submit">{{disabled?'创建中…':`创建 ${rows.length} 个镜头`}}</button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.batch-layer{position:fixed;inset:0;z-index:1300;padding:28px;display:grid;place-items:center;background:#29241e80;color:var(--ws-text)}.batch-layer>section{box-sizing:border-box;width:min(920px,100%);max-height:90vh;padding:22px;overflow:auto;background:var(--ws-surface);border-radius:15px}.batch-layer header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.batch-layer h2{margin:3px 0}.batch-layer p{margin:5px 0;color:var(--ws-text-muted);font-size:12px}.batch-layer small{color:var(--ws-text-muted);font-size:10px;letter-spacing:.12em}.batch-layer button{min-height:34px;padding:7px 12px;color:var(--ws-text);background:var(--ws-surface);border:1px solid var(--ws-border);border-radius:7px;cursor:pointer}.batch-layer button:disabled{opacity:.45;cursor:not-allowed}.rows{display:grid;gap:12px;margin:18px 0}.rows article{padding:14px;background:var(--ws-surface);border:1px solid var(--ws-border);border-radius:10px}.row-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}.row-head button{min-height:28px;padding:4px 9px;color:var(--ws-text-muted)}.fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.fields label{display:grid;gap:6px;color:var(--ws-text);font-size:12px}.fields .wide{grid-column:1/-1}.fields input,.fields textarea,.fields select{box-sizing:border-box;width:100%;min-width:0;min-height:36px;padding:8px;color:var(--ws-text);background:var(--ws-surface);border:1px solid var(--ws-border);border-radius:7px;font:inherit}.fields textarea{resize:vertical}.add-row{width:100%;border-style:dashed!important}.batch-layer footer{display:flex;align-items:center;justify-content:flex-end;gap:9px;padding-top:14px}.batch-layer footer span{margin-right:auto;color:var(--ws-text-muted);font-size:12px}.primary{color:var(--ws-text)!important;background:var(--ws-selected)!important}@media(max-width:700px){.batch-layer{padding:10px}.fields{grid-template-columns:1fr}.fields .wide{grid-column:auto}.batch-layer footer{flex-wrap:wrap}.batch-layer footer span{width:100%}}
</style>
