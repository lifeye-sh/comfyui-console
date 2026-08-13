<script setup lang="ts">
import { ref } from 'vue'
import GlassCard from '@/v2/components/GlassCard.vue'
import GlassDrawer from '@/v2/components/GlassDrawer.vue'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import V2Field from '@/v2/components/V2Field.vue'
const drawerOpen = ref(false)
const demoText = ref('1088 × 1920')
</script>
<template>
  <div class="v2-page">
    <div class="v2-page-heading"><StatusBadge tone="info">Design system</StatusBadge><h1>V2 组件与视觉规范</h1><p>用于验证颜色、玻璃容器、按钮、表单、状态和响应式行为。</p></div>
    <div class="token-grid"><div v-for="token in ['primary','success','warning','danger','info']" :key="token" class="token"><i :class="token" /><span>{{ token }}</span></div></div>
    <GlassPanel title="按钮与状态" description="所有交互元素均有键盘焦点状态"><div class="button-row"><V2Button variant="primary">主要操作</V2Button><V2Button>次要操作</V2Button><V2Button variant="ghost">极简按钮</V2Button><V2Button variant="danger">危险操作</V2Button><V2Button disabled>不可用</V2Button></div><div class="button-row badges"><StatusBadge>草稿</StatusBadge><StatusBadge tone="info">运行中</StatusBadge><StatusBadge tone="success">已完成</StatusBadge><StatusBadge tone="warning">等待中</StatusBadge><StatusBadge tone="danger">失败</StatusBadge></div></GlassPanel>
    <div class="v2-grid v2-grid--2 section-gap"><GlassCard><h2>表单字段</h2><div class="form-demo"><V2Field label="图片尺寸" hint="默认竖屏尺寸"><select v-model="demoText"><option>1088 × 1920</option><option>1024 × 1024</option></select></V2Field><V2Field label="任务名称" required><input placeholder="输入任务名称" /></V2Field><V2Button variant="primary" @click="drawerOpen = true">打开玻璃抽屉</V2Button></div></GlassCard><GlassCard interactive><h2>交互卡片</h2><p>悬浮时显示柔和阴影和轻微位移。降低动效偏好下会自动取消动画。</p><StatusBadge tone="success">响应式就绪</StatusBadge></GlassCard></div>
    <GlassDrawer :open="drawerOpen" title="抽屉组件示例" @close="drawerOpen = false"><p class="drawer-copy">桌面端从右侧展开，移动端限制在视口宽度内，并支持 Esc 键关闭。</p><V2Button variant="primary" @click="drawerOpen = false">完成</V2Button></GlassDrawer>
  </div>
</template>
<style scoped>
.v2-page-heading h1 { margin-top:14px; }.token-grid { margin-bottom:18px; display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }.token { padding:12px; display:flex; align-items:center; gap:9px; color:var(--v2-text-muted); background:var(--v2-surface-soft); border:1px solid var(--v2-border); border-radius:12px; }.token i { width:22px; height:22px; border-radius:7px; }.token .primary{background:var(--v2-primary)}.token .success{background:var(--v2-success)}.token .warning{background:var(--v2-warning)}.token .danger{background:var(--v2-danger)}.token .info{background:var(--v2-info)}.button-row { display:flex; flex-wrap:wrap; gap:10px; }.badges { margin-top:18px; }.section-gap { margin-top:18px; }.section-gap h2 { margin-top:0; }.section-gap p,.drawer-copy { color:var(--v2-text-muted); line-height:1.8; }.form-demo { display:grid; gap:18px; }.form-demo .v2-button { width:max-content; }@media(max-width:620px){.token-grid{grid-template-columns:repeat(2,1fr)}.token:last-child{grid-column:span 2}}
</style>
