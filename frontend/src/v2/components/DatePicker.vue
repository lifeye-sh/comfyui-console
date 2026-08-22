<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  /** 当前选中的日期，格式 YYYY-MM-DD，空字符串表示未选 */
  modelValue: string
}>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  close: []
}>()

const today = new Date()
const viewYear = ref(today.getFullYear())
const viewMonth = ref(today.getMonth())

// 同步外部值到视图月份
watch(() => props.modelValue, (v) => {
  if (v) {
    const [y, m] = v.split('-').map(Number)
    if (y && m != null) { viewYear.value = y; viewMonth.value = m - 1 }
  }
}, { immediate: true })

const monthNames = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
const weekDays = ['日','一','二','三','四','五','六']

const currentMonthLabel = computed(() => `${viewYear.value}年 ${monthNames[viewMonth.value]}`)

/** 日历网格：42 格（6 行 × 7 列），每格存 {day, dateStr, inMonth} */
const calendarDays = computed(() => {
  const firstDay = new Date(viewYear.value, viewMonth.value, 1)
  const startWeekday = firstDay.getDay()
  const daysInMonth = new Date(viewYear.value, viewMonth.value + 1, 0).getDate()
  const days: Array<{day:number;dateStr:string;inMonth:boolean;isToday:boolean;isSelected:boolean}> = []
  // 上月填充
  const prevMonthDays = new Date(viewYear.value, viewMonth.value, 0).getDate()
  for (let i = startWeekday - 1; i >= 0; i--) {
    const d = prevMonthDays - i
    const pm = viewMonth.value === 0 ? 11 : viewMonth.value - 1
    const py = viewMonth.value === 0 ? viewYear.value - 1 : viewYear.value
    days.push({ day: d, dateStr: fmtDate(py, pm, d), inMonth: false, isToday: false, isSelected: props.modelValue === fmtDate(py, pm, d) })
  }
  // 当月
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = fmtDate(viewYear.value, viewMonth.value, d)
    days.push({
      day: d, dateStr: ds, inMonth: true,
      isToday: ds === fmtDate(today.getFullYear(), today.getMonth(), today.getDate()),
      isSelected: props.modelValue === ds,
    })
  }
  // 下月填充到 42 格
  const remaining = 42 - days.length
  for (let d = 1; d <= remaining; d++) {
    const nm = viewMonth.value === 11 ? 0 : viewMonth.value + 1
    const ny = viewMonth.value === 11 ? viewYear.value + 1 : viewYear.value
    days.push({ day: d, dateStr: fmtDate(ny, nm, d), inMonth: false, isToday: false, isSelected: props.modelValue === fmtDate(ny, nm, d) })
  }
  return days
})

function fmtDate(y: number, m: number, d: number) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

function prevMonth() {
  if (viewMonth.value === 0) { viewMonth.value = 11; viewYear.value-- }
  else viewMonth.value--
}
function nextMonth() {
  if (viewMonth.value === 11) { viewMonth.value = 0; viewYear.value++ }
  else viewMonth.value++
}
function goToday() {
  viewYear.value = today.getFullYear()
  viewMonth.value = today.getMonth()
}
function pick(dateStr: string) {
  emit('update:modelValue', dateStr)
  emit('close')
}
function clearDate() {
  emit('update:modelValue', '')
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="cal-overlay" @click.self="emit('close')">
      <div class="cal-panel">
        <header class="cal-header">
          <button class="cal-nav" @click="prevMonth">‹</button>
          <span class="cal-title">{{ currentMonthLabel }}</span>
          <button class="cal-nav" @click="nextMonth">›</button>
        </header>
        <div class="cal-weekdays">
          <span v-for="w in weekDays" :key="w" class="cal-weekday">{{ w }}</span>
        </div>
        <div class="cal-grid">
          <button
            v-for="(cell, i) in calendarDays"
            :key="i"
            :class="['cal-day', { 'out-month': !cell.inMonth, today: cell.isToday, selected: cell.isSelected }]"
            @click="pick(cell.dateStr)"
          >{{ cell.day }}</button>
        </div>
        <footer class="cal-footer">
          <button class="cal-action" @click="goToday">今天</button>
          <button class="cal-action" @click="clearDate">清除日期</button>
          <button class="cal-action" @click="emit('close')">关闭</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.cal-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center;
  padding: 16px;
}
.cal-panel {
  width: min(360px, 92vw);
  background: #1a2238;
  border: 1px solid rgba(130, 149, 255, 0.25);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}
.cal-header {
  padding: 14px 16px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid rgba(130, 149, 255, 0.12);
}
.cal-title { font-size: 15px; color: #e8edff; font-weight: 600; }
.cal-nav {
  width: 36px; height: 36px;
  font-size: 20px; color: #c8d0ee;
  background: rgba(130, 149, 255, 0.08);
  border: 1px solid rgba(130, 149, 255, 0.18);
  border-radius: 10px; cursor: pointer;
  display: grid; place-items: center;
}
.cal-nav:hover { background: rgba(130, 149, 255, 0.16); }
.cal-weekdays {
  display: grid; grid-template-columns: repeat(7, 1fr);
  padding: 8px 8px 4px;
}
.cal-weekday {
  text-align: center; font-size: 11px; color: #7a85a8;
  padding: 4px 0;
}
.cal-grid {
  display: grid; grid-template-columns: repeat(7, 1fr);
  gap: 2px; padding: 4px 8px 8px;
}
.cal-day {
  aspect-ratio: 1;
  display: grid; place-items: center;
  font-size: 14px; color: #c8d0ee;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: 0.12s;
  min-height: 40px;
}
.cal-day:hover { background: rgba(130, 149, 255, 0.1); }
.cal-day.out-month { color: #4a5680; opacity: 0.5; }
.cal-day.today {
  border-color: rgba(130, 149, 255, 0.4);
  color: #8295ff;
}
.cal-day.selected {
  background: linear-gradient(135deg, #8295ff, #865fee);
  color: #fff;
  border-color: transparent;
  font-weight: 700;
}
.cal-footer {
  padding: 10px 16px;
  display: flex; gap: 8px;
  border-top: 1px solid rgba(130, 149, 255, 0.12);
}
.cal-action {
  flex: 1; padding: 10px 0;
  font-size: 13px; color: #c8d0ee;
  background: rgba(130, 149, 255, 0.08);
  border: 1px solid rgba(130, 149, 255, 0.18);
  border-radius: 10px; cursor: pointer;
}
.cal-action:hover { background: rgba(130, 149, 255, 0.16); }

@media (max-width: 700px) {
  .cal-panel { width: 92vw; }
  .cal-day { font-size: 15px; min-height: 44px; }
}
</style>