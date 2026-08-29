<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  /** 情感曲线数据：[{stable_key, order, label, intensity, valence, evidence_type}] */
  curve: Array<Record<string, any>>
}>()

const W = 720
const H = 260
const PAD = { top: 24, right: 16, bottom: 44, left: 36 }
const plotW = W - PAD.left - PAD.right
const plotH = H - PAD.top - PAD.bottom

/** 强度线 Y 坐标（0-10 → 底部到顶部） */
function iy(v: number) {
  return PAD.top + plotH - (Math.max(0, Math.min(10, v)) / 10) * plotH
}
/** 效价线 Y 坐标（-5~+5 → 中线上下） */
function vy(v: number) {
  const clamped = Math.max(-5, Math.min(5, v))
  const mid = PAD.top + plotH / 2
  return mid - (clamped / 5) * (plotH / 2)
}
function x(i: number) {
  if (!props.curve.length) return PAD.left
  return PAD.left + (i / Math.max(1, props.curve.length - 1)) * plotW
}

const intensityPath = computed(() =>
  props.curve.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${iy(Number(p.intensity)).toFixed(1)}`).join(' ')
)
const valencePath = computed(() =>
  props.curve.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${vy(Number(p.valence)).toFixed(1)}`).join(' ')
)

const peak = computed(() => props.curve.length ? props.curve.reduce((a, b) => (Number(b.intensity) > Number(a.intensity) ? b : a)) : null)
const trough = computed(() => props.curve.length ? props.curve.reduce((a, b) => (Number(b.intensity) < Number(a.intensity) ? b : a)) : null)

const assumptionCount = computed(() => props.curve.filter(p => p.evidence_type === 'assumed').length)
</script>

<template>
  <div class="curve-wrap">
    <svg :viewBox="`0 0 ${W} ${H}`" class="curve-svg" role="img" aria-label="情感曲线">
      <!-- 网格与坐标 -->
      <line v-for="g in [0, 2.5, 5, 7.5, 10]" :key="'gi' + g" :x1="PAD.left" :x2="W - PAD.right"
        :y1="iy(g)" :y2="iy(g)" class="grid" />
      <text v-for="g in [0, 5, 10]" :key="'ti' + g" :x="PAD.left - 6" :y="iy(g) + 3" class="tick" text-anchor="end">{{ g }}</text>
      <text v-for="v in [-5, 0, 5]" :key="'tv' + v" :x="PAD.left - 6" :y="vy(v) + 3" class="tick" text-anchor="end">{{ v }}</text>
      <line :x1="PAD.left" :x2="W - PAD.right" :y1="vy(0)" :y2="vy(0)" class="midline" />
      <!-- 节拍标签（采样显示） -->
      <text v-for="(p, i) in curve" :key="'x' + p.stable_key" v-show="curve.length <= 12 || i % Math.ceil(curve.length / 12) === 0"
        :x="x(i)" :y="H - PAD.bottom + 14" class="tick" text-anchor="middle">{{ p.stable_key.replace('BT-', '') }}</text>
      <!-- 效价线 -->
      <path :d="valencePath" class="line valence-line" />
      <!-- 强度线 -->
      <path :d="intensityPath" class="line intensity-line" />
      <!-- 数据点 -->
      <circle v-for="(p, i) in curve" :key="'c' + p.stable_key" :cx="x(i)"
        :cy="iy(Number(p.intensity))" r="4" :class="['dot', p.evidence_type]" />
    </svg>
    <div class="legend">
      <span><i class="swatch intensity-swatch" />情绪强度（0-10）</span>
      <span><i class="swatch valence-swatch" />情感效价（-5~+5）</span>
      <span><i class="dot hollow" />assumed 假设节拍（{{ assumptionCount }}）</span>
    </div>
    <div v-if="peak && trough" class="summary">
      <span>🔺 最高峰：<b>{{ peak.stable_key }}</b> 强度 {{ peak.intensity }} · {{ peak.dominant_emotion }}</span>
      <span>🔻 最低谷：<b>{{ trough.stable_key }}</b> 强度 {{ trough.intensity }} · {{ trough.dominant_emotion }}</span>
    </div>
  </div>
</template>

<style scoped>
.curve-wrap{display:grid;gap:8px}
.curve-svg{width:100%;height:auto;background:rgba(255,255,255,.02);border:1px solid var(--v2-border);border-radius:12px}
.grid{stroke:rgba(130,149,255,.12);stroke-width:1}
.midline{stroke:rgba(130,149,255,.25);stroke-width:1;stroke-dasharray:4 4}
.tick{fill:#7a85a8;font-size:9px}
.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.intensity-line{stroke:#8295ff}
.valence-line{stroke:#4fd1a5;opacity:.85}
.dot{fill:#8295ff;stroke:#fff;stroke-width:1}
.dot.assumed{fill:none;stroke:#ffb347;stroke-width:2}
.dot.explicit{fill:#8295ff}
.dot.inferred{fill:#8295ff;fill-opacity:.6}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:#7a85a8;font-size:11px;align-items:center}
.legend .swatch{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:4px;vertical-align:middle}
.intensity-swatch{background:#8295ff}.valence-swatch{background:#4fd1a5}
.legend .dot{position:relative;display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;background:#ffb347}
.summary{display:flex;flex-direction:column;gap:6px;color:#7a85a8;font-size:11px}
.summary b{color:#e8edff}
</style>