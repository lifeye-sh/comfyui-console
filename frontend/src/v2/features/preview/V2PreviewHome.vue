<script setup lang="ts">
import GlassCard from '@/v2/components/GlassCard.vue'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
</script>
<template>
  <div class="v2-page">
    <div class="v2-page-heading"><StatusBadge tone="success">Iteration 1</StatusBadge><h1>新的创作工作台已就绪</h1><p>本轮完成 V2 设计系统与响应式应用框架，业务数据将在后续迭代逐步接入。</p></div>
    <div class="metrics v2-grid v2-grid--3">
      <GlassCard interactive><span>设计令牌</span><strong>24+</strong><small>颜色、间距、圆角与动效</small></GlassCard>
      <GlassCard interactive><span>响应断点</span><strong>4</strong><small>360 / 768 / 1366 / 1920</small></GlassCard>
      <GlassCard interactive><span>稳定版影响</span><strong>0</strong><small>V1 业务页面保持不变</small></GlassCard>
    </div>
    <div class="workspace v2-grid v2-grid--2">
      <GlassPanel title="本轮已完成" description="V2 独立 UI 基础设施"><ul><li>Glassmorphism 主题和可复用组件</li><li>桌面侧栏、顶栏与折叠状态</li><li>移动端五项底部导航</li><li>动态生成菜单和管理员权限裁剪</li><li>键盘焦点、低动效与低透明度适配</li></ul><template #actions><V2Button variant="primary" @click="$router.push('/v2/design-system')">查看组件</V2Button></template></GlassPanel>
      <GlassPanel title="下一步" description="Iteration 2：系统概览与任务中心"><div class="next-list"><StatusBadge tone="info">Dashboard 数据适配</StatusBadge><StatusBadge tone="warning">任务列表与筛选</StatusBadge><StatusBadge>任务详情抽屉</StatusBadge><StatusBadge>多媒体查看器</StatusBadge></div></GlassPanel>
    </div>
  </div>
</template>
<style scoped>
.v2-page-heading h1 { margin-top:14px; }.metrics { margin-bottom:18px; }.metrics .glass-card { display:grid; gap:8px; }.metrics span,.metrics small { color:var(--v2-text-muted); }.metrics strong { font-size:34px; }.workspace { margin-top:18px; }.workspace ul { margin:0; padding-left:20px; display:grid; gap:13px; color:var(--v2-text-muted); line-height:1.6; }.next-list { display:flex; flex-wrap:wrap; gap:10px; }
</style>
