<script setup lang="ts">
import { computed, watch } from 'vue'
import type { ParameterConfig } from '../generation-config/model'
import { parameterOptions, parameterVisible, type SelectSettings } from './workflowParameters'
import MediaParameterField from './MediaParameterField.vue'
import V2Field from '@/v2/components/V2Field.vue'
import V2Button from '@/v2/components/V2Button.vue'
const props = defineProps<{parameters: ParameterConfig[]; modelValue: Record<string, any>; settings: SelectSettings; disabled?: boolean; sizeKey?: string; excludeKeys?: string[]; promptLibrary?: boolean; savingPromptKey?: string|null}>()
const emit = defineEmits<{ 'update:modelValue': [Record<string, any>]; 'save-prompt': [ParameterConfig] }>()
const sizeSetting = computed(() => props.settings[props.sizeKey || 'image_size'])
const combinedSize = computed(() => !!sizeSetting.value?.options?.length && ['width','height'].every(key => props.parameters.some(p => p.key === key && parameterVisible(p,props.modelValue))))
const fields = computed(() => props.parameters.filter(p => !props.excludeKeys?.includes(p.key) && !(combinedSize.value && ['width','height'].includes(p.key)) && parameterVisible(p,props.modelValue)))
const selectedSize = computed(() => `${props.modelValue.width}x${props.modelValue.height}`)
// Media selection emits the resource update and mask reset synchronously.
// Props refresh on the next render, so merge consecutive edits into the last
// emitted value instead of letting the mask reset restore the old resource.
let pendingValue = props.modelValue
watch(() => props.modelValue, value => { pendingValue = value }, { flush: 'sync' })
function patch(values: Record<string, any>) {
  pendingValue = {...pendingValue, ...values}
  emit('update:modelValue', pendingValue)
}
function set(key: string, value: any) { patch({[key]: value}) }
function setSize(event: Event) { const value=(event.target as HTMLSelectElement).value; const [width,height]=value.split('x').map(Number); patch({width,height,__size:value}) }
function input(parameter: ParameterConfig, event: Event) { const value=(event.target as HTMLInputElement).value; set(parameter.key,['int','float','slider'].includes(parameter.type) ? (value === '' ? null : Number(value)) : value) }
</script>
<template>
  <V2Field v-if="combinedSize" :label="sizeKey === 'video_size' ? '视频尺寸' : '图片尺寸'"><select :value="selectedSize" :disabled="disabled" @change="setSize"><option v-if="!sizeSetting?.options.some(o=>String(o.value)===selectedSize)" :value="selectedSize">自定义 {{ selectedSize }}</option><option v-for="option in sizeSetting?.options" :key="String(option.value)" :value="option.value">{{ option.label }}</option></select></V2Field>
  <V2Field v-for="parameter in fields" :key="parameter.key" :label="parameter.label || parameter.key" :hint="parameter.help || (parameter.unit ? `单位：${parameter.unit}` : undefined)" :required="parameter.required" :class="{'wide-field':['textarea','image','video','audio'].includes(parameter.type)}">
    <div v-if="parameter.type==='textarea'" class="textarea-wrap"><textarea :value="modelValue[parameter.key]" rows="3" :disabled="disabled" @input="input(parameter,$event)"/><button v-if="promptLibrary && /prompt/i.test(parameter.key)" type="button" class="save-prompt-btn" :disabled="disabled || savingPromptKey===parameter.key" @click="emit('save-prompt',parameter)">{{ savingPromptKey===parameter.key?'保存中…':'存入提示词库' }}</button></div>
    <select v-else-if="parameter.type==='select'||parameter.type==='size'" :value="modelValue[parameter.key]" :disabled="disabled" @change="set(parameter.key,parameterOptions(parameter,settings).find(o=>String(o.value)===($event.target as HTMLSelectElement).value)?.value)"><option v-for="option in parameterOptions(parameter,settings)" :key="String(option.value)" :value="option.value">{{ option.label }}</option></select>
    <label v-else-if="parameter.type==='bool'" class="parameter-switch"><input :checked="!!modelValue[parameter.key]" type="checkbox" :disabled="disabled" @change="set(parameter.key,($event.target as HTMLInputElement).checked)"/><span>{{ modelValue[parameter.key]?'已开启':'已关闭' }}</span></label>
    <MediaParameterField v-else-if="['image','video','audio'].includes(parameter.type)" :model-value="modelValue[parameter.key]" :media-type="parameter.type as 'image'|'video'|'audio'" :multiple="parameter.multiple" :disabled="disabled" :mask-resource-id="parameter.type==='image'?(modelValue[parameter.key+'__mask']||null):undefined" @update:model-value="set(parameter.key,$event)" @update:mask-resource-id="set(parameter.key+'__mask',$event)"/>
    <div v-else-if="parameter.type==='seed'" class="seed-input"><input :value="modelValue[parameter.key]" type="number" :disabled="disabled" @input="set(parameter.key,($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value))"/><V2Button variant="ghost" :disabled="disabled" @click="set(parameter.key,Math.floor(Math.random()*4294967295))">随机</V2Button></div>
    <input v-else :value="modelValue[parameter.key]" :type="['int','float','slider'].includes(parameter.type)?'number':'text'" :min="parameter.min" :max="parameter.max" :step="parameter.step || (parameter.type==='int'?1:'any')" :disabled="disabled" @input="input(parameter,$event)"/>
  </V2Field>
</template>
<style scoped>
.wide-field{grid-column:1/-1}.textarea-wrap{display:grid;gap:6px}.textarea-wrap textarea{width:100%;resize:vertical}.save-prompt-btn{justify-self:end;padding:4px 12px;color:var(--v2-primary);border:1px solid var(--v2-border);border-radius:8px;cursor:pointer}.seed-input{display:grid;grid-template-columns:1fr auto;gap:7px}.parameter-switch{display:flex;align-items:center;gap:9px;min-height:40px}.parameter-switch input{width:auto}
</style>
