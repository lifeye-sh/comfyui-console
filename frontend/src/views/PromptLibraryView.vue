<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { promptApi } from '@/api/modules'

const message = useMessage()
const prompts = ref<any[]>([])
const categories = ref<any[]>([])
const showAdd = ref(false)
const showAddCat = ref(false)
const selected = ref<any>(null)

const form = reactive({
  name: '',
  content: '',
  negative_content: '',
  category_id: null as number | null,
  remark: '',
  tags: [] as string[],
})
const catName = ref('')

async function load() {
  try {
    prompts.value = await promptApi.list({ limit: 200 })
    categories.value = await promptApi.listCategories()
  } catch {
    message.error('加载失败')
  }
}
onMounted(load)

async function add() {
  try {
    await promptApi.create({ ...form })
    showAdd.value = false
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.message || '创建失败')
  }
}

async function addCategory() {
  try {
    await promptApi.createCategory(catName.value)
    catName.value = ''
    showAddCat.value = false
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.message || '创建失败')
  }
}

async function del(id: number) {
  try {
    await promptApi.remove(id)
    await load()
  } catch {
    message.error('删除失败')
  }
}

function openEdit(p: any) {
  selected.value = p
  form.name = p.name
  form.content = p.content
  form.negative_content = p.negative_content
  form.category_id = p.category_id
  form.remark = p.remark
  form.tags = p.tags || []
  showAdd.value = true
}

async function update() {
  if (!selected.value) return
  try {
    await promptApi.patch(selected.value.id, { ...form })
    showAdd.value = false
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.message || '更新失败')
  }
}

function reset() {
  selected.value = null
  form.name = ''
  form.content = ''
  form.negative_content = ''
  form.category_id = null
  form.remark = ''
  form.tags = []
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex justify-between items-center mb-4">
      <NH2 style="margin: 0">提示词库</NH2>
      <div class="flex gap-2">
        <NButton @click="showAddCat = true">添加分类</NButton>
        <NButton type="primary" @click="reset(); showAdd = true">添加提示词</NButton>
      </div>
    </div>

    <div class="text-sm text-gray-500">分类：{{ categories.map((c) => c.name).join(' / ') }}</div>

    <div v-if="!prompts.length" class="text-gray-400">暂无提示词</div>
    <div v-else class="space-y-2">
      <div v-for="p in prompts" :key="p.id" class="border rounded p-3">
        <div class="flex justify-between">
          <NText strong>{{ p.name }}</NText>
          <NSpace>
            <NButton size="tiny" quaternary @click="openEdit(p)">编辑</NButton>
            <NButton size="tiny" type="error" quaternary @click="del(p.id)">删除</NButton>
          </NSpace>
        </div>
        <NText style="font-size: 12px" depth="3">{{ p.content }}</NText>
      </div>
    </div>

    <NModal :show="showAdd" @update:show="showAdd = false" preset="card" :title="selected ? '编辑提示词' : '添加提示词'" style="max-width: 600px">
      <NSpace vertical :size="12">
        <NInput v-model:value="form.name" placeholder="名称" />
        <NSelect v-model:value="form.category_id" :options="categories.map((c) => ({ label: c.name, value: c.id }))" placeholder="分类" clearable />
        <NInput v-model:value="form.content" type="textarea" :rows="4" placeholder="提示词正文" />
        <NInput v-model:value="form.negative_content" type="textarea" :rows="2" placeholder="负面提示词" />
        <NInput v-model:value="form.remark" placeholder="备注" />
        <NButton type="primary" block @click="selected ? update() : add()">{{ selected ? '更新' : '保存' }}</NButton>
      </NSpace>
    </NModal>

    <NModal :show="showAddCat" @update:show="showAddCat = false" preset="card" title="添加分类" style="max-width: 360px">
      <NSpace vertical :size="12">
        <NInput v-model:value="catName" placeholder="分类名称" />
        <NButton type="primary" block @click="addCategory">保存</NButton>
      </NSpace>
    </NModal>
  </div>
</template>

<script lang="ts">
import { NH2, NSpace, NText, NButton, NModal, NInput, NSelect } from 'naive-ui'
</script>
