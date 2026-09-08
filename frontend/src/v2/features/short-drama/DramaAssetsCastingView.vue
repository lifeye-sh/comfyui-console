<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { batchApi, genTypeApi, generationTypeConfigApi, imageProviderApi, resourceApi, settingsApi, shortDramaApi, taskApi, type CharacterVariant, type ImageProvider, type PhaseOneCasting, type ProjectAssetVersion, type WorldCharacter, type WorldLocation, type WorldProp } from '@/api/modules'
import AssetPicker from '@/v2/components/AssetPicker.vue'
import MediaViewer from '@/v2/components/MediaViewer.vue'
import V2Button from '@/v2/components/V2Button.vue'
import type { ResourceItem } from '@/v2/features/assets/model'
import { useResourceThumbs } from '@/v2/features/assets/useResourceThumbs'
import type { TaskOutput } from '@/v2/features/tasks/model'
import MediaParameterField from '@/v2/features/generate/MediaParameterField.vue'
import WorkflowParameterFields from '@/v2/features/generate/WorkflowParameterFields.vue'
import { migrateWorkflowParams, promptParameter, workflowDefaults, workflowPayload, workflowValidation, type SelectSettings } from '@/v2/features/generate/workflowParameters'
import type { RuntimeWorkflow } from '@/v2/features/generation-config/model'
import DramaProjectShell from './DramaProjectShell.vue'

type AssetKind = 'character' | 'variant' | 'location' | 'prop'
type CardKind = Exclude<AssetKind, 'variant'>
type CastingItem = WorldCharacter | WorldLocation | WorldProp
type GenerationPurpose = 'default' | 'character_turnaround'
type GenerationJob = { workflowVersionId?:number|null; parameters?:Record<string,unknown>; id:number; batchId:number; kind:AssetKind; entityId:number; label:string; prompt:string; purpose:GenerationPurpose; service:'comfyui'|'gemini'; references:number[]; size:string; status:string; progress:number; error:string; outputId:number|null; finalized:boolean; finalizing:boolean }
const route = useRoute(); const router = useRouter(); const projectId = computed(() => Number(route.params.projectId)); const episodeId = computed(() => Number(route.query.episode_id) || 0)
const data = ref<PhaseOneCasting | null>(null); const tab = ref<'characters' | 'locations' | 'props'>('characters')
const loading = ref(true); const busy = ref(false); const error = ref(''); const notice = ref('')
const createDialog = ref<CardKind | null>(null)
const createForm = ref({ name: '', description: '', detail: '' })
const wardrobe = ref<WorldCharacter | null>(null); const variant = ref({ name: '', description: '' })
const pickerOpen = ref(false); const pickerTarget = ref<{ kind: AssetKind; id: number; purpose: GenerationPurpose } | null>(null)
const promptEditing = ref(''); const promptDrafts = ref<Record<string, string>>({}); const expandedVersions = ref(''); const generationMonitorExpanded = ref(false)
const imageSize = ref(''); const imageSizeOptions = ref<Array<{label:string;value:string}>>([]); const generationTypes = ref<any[]>([]); const generationTypeId = ref<number | null>(null); const imageProviders = ref<ImageProvider[]>([])
const generationDialog = ref<{kind:AssetKind;id:number;prompt:string;purpose:GenerationPurpose}|null>(null); const generationService = ref<'comfyui'|'gemini'>('gemini'); const generationProviderId = ref<number|null>(null); const generationReferences = ref<number[]>([])
const generationWorkflows = ref<RuntimeWorkflow[]>([])
const generationWorkflowId = ref<number|null>(null)
const generationParams = ref<Record<string,any>>({})
const generationSettings = ref<SelectSettings>({})
const generationWorkflowLoading = ref(false)
const generationWorkflowError = ref('')
let workflowRequest = 0
let workflowParamCache: Record<string,Record<string,any>> = {}
const generationWorkflow = computed(() => generationWorkflows.value.find(w => w.workflow_version_id === generationWorkflowId.value) || null)
const generationSubmitting = ref(false); const generationDialogError = ref(''); const generationTasks = ref<GenerationJob[]>([]); let generationTimer:ReturnType<typeof setInterval>|null=null
const resources = ref<Record<number, ResourceItem>>({}); const { thumbs, load: loadThumbs, clear: clearThumbs } = useResourceThumbs()
const assetPreview = ref<TaskOutput | null>(null)
const defaultTurnaroundTemplate = [
  '【角色三视图资产参考图提示词】',
  '画幅：16:9 横屏，全风格通用角色三视图资产参考图，白底纯色干净背景，次世代 3D / 实拍级全身模型拆解。',
  '排版结构：三栏横向并排展示（左侧：无头全身正面站姿立绘，中侧：无头全身背面站姿立绘，右侧：大比例面部五官头部正侧特写）。',
  '服装与身体材质：{{服装}}。无头全身展示完整服装剪裁与鞋履。',
  '面部特写：{{五官}}{{发型段落}}。神情沉静，发丝与骨相极致清晰。',
  '技术质量：{{技术质量}}。',
  '角色完整设定：{{角色完整设定}}。',
].join('\n')
const turnaroundTemplate=ref(defaultTurnaroundTemplate),turnaroundTemplateDraft=ref(defaultTurnaroundTemplate),turnaroundTemplateEditing=ref(false)
const projectBrief=ref<any>(null)

const allRequired = computed(() => [...(data.value?.characters || []).map(item => ({ label: `角色「${item.name}」`, ready: !!item.primary_resource_id })), ...(data.value?.locations || []).map(item => ({ label: `场景「${item.name}」`, ready: !!item.primary_resource_id }))])
const pendingRequired = computed(() => allRequired.value.filter(item => !item.ready))
const canEnterStoryboard = computed(() => !!data.value && !pendingRequired.value.length && !!episodeId.value)
const totalCount = computed(() => (data.value?.characters.length || 0) + (data.value?.locations.length || 0) + (data.value?.props.length || 0))
const confirmedCount = computed(() => !data.value ? 0 : data.value.characters.filter(item => item.primary_resource_id).length + data.value.locations.filter(item => item.primary_resource_id).length + data.value.props.filter(item => item.resource_id).length)
const selectedGeneration = computed(() => generationTypes.value.find(item => item.id === generationTypeId.value) || null)
const mixedGeneration = computed(() => generationTypes.value.find(item => item.code === 'mixed') || null)
const activeGenerationCount = computed(() => generationTasks.value.filter(item => ['PENDING','DISPATCHING','QUEUED','RUNNING'].includes(item.status) || item.finalizing).length)
const finishedGenerationCount = computed(() => generationTasks.value.filter(item => item.finalized).length)
const currentGenerationJob = computed(() => generationTasks.value.find(item => ['PENDING','DISPATCHING','QUEUED','RUNNING'].includes(item.status) || item.finalizing) || generationTasks.value[0] || null)
function key(kind: AssetKind, id: number) { return `${kind}:${id}` }
function versions(kind: AssetKind, id: number) { return data.value?.asset_versions.filter(item => item.entity_type === kind && item.entity_id === id) || [] }
function currentVersion(kind: AssetKind, id: number) { return versions(kind, id).find(item => item.is_current) || null }
function latestPrompt(kind:AssetKind,id:number,fallback=''){
  const values=versions(kind,id)
  const canonical=values.find(item=>['prompt_edit','skill_asset_prompt'].includes(String(item.generation_snapshot?.purpose||''))&&item.prompt?.trim())
  return canonical?.prompt || values.find(item=>item.prompt?.trim())?.prompt || fallback
}
function turnaroundVersions(kind: 'character'|'variant', id: number) { return versions(kind, id).filter(item => item.generation_snapshot?.purpose === 'asset_turnaround' || item.generation_snapshot?.purpose === 'character_turnaround') }
function latestTurnaroundVersions(kind:'character'|'variant',id:number){return turnaroundVersions(kind,id).filter(item=>item.resource_id).sort((a,b)=>(b.version||0)-(a.version||0)||b.id-a.id).slice(0,1)}
function resourceId(kind: AssetKind, item: CastingItem | CharacterVariant) { return kind === 'prop' ? (item as WorldProp).resource_id : (item as WorldCharacter | WorldLocation | CharacterVariant).primary_resource_id }
function thumb(kind: AssetKind, item: CastingItem | CharacterVariant) { const id = resourceId(kind, item); return id ? thumbs.value[id] : '' }
function previewAsset(kind:AssetKind,item:CastingItem|CharacterVariant){const id=resourceId(kind,item);if(!id)return;const resource=resources.value[id];assetPreview.value={id,filename:resource?.filename||`${assetName(kind,item.id)}.png`,media_type:'image',mime:resource?.mime||'image/png',width:resource?.width,height:resource?.height,duration:null}}
function previewResource(id:number,label:string){const resource=resources.value[id];assetPreview.value={id,filename:resource?.filename||`${label}.png`,media_type:'image',mime:resource?.mime||'image/png',width:resource?.width,height:resource?.height,duration:null}}
function statusLabel(kind: AssetKind, item: CastingItem | CharacterVariant) { return resourceId(kind, item) ? '已确认' : versions(kind, item.id).length ? '待采用' : '待生成' }
function statusTone(kind: AssetKind, item: CastingItem | CharacterVariant) { return resourceId(kind, item) ? 'ready' : versions(kind, item.id).length ? 'candidate' : 'pending' }
const defaultCharacterPose = '白色背景，正面全身照'
const defaultCharacterTechnical = 'high-quality 3D CGI animation, 3d-animation, Pixar/DreamWorks style, subsurface scattering, detailed textures, stylized characters'
function promptSegment(raw: string, index: number, title: string) {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const next = index < 6 ? `(?=\\n\\s*${index + 1}\\.)` : '$'
  return raw.match(new RegExp(`(?:^|\\n)\\s*${index}\\.\\s*${escaped}\\s*[:：]\\s*([\\s\\S]*?)${next}`, 'i'))?.[1]?.trim() || ''
}
function characterPrompt(item: WorldCharacter, raw = item.appearance || '') {
  // V6.5 character prompts are complete production records. Preserve the text
  // exactly instead of destructively converting it to the retired six-line form.
  return raw.trim() || item.appearance?.trim() || item.identity?.trim() || ''
}
function renderTurnaroundTemplate(values:Record<string,string>){return Object.entries(values).reduce((result,[name,value])=>result.split('{{'+name+'}}').join(value),turnaroundTemplate.value)}
function characterTurnaroundPrompt(item: WorldCharacter) {
  const base=characterPrompt(item,promptDrafts.value[key('character',item.id)]||item.appearance||'')
  const clothing=promptSegment(base,4,'Clothing')||'保持角色完整提示词中的服装设定，完整展示服装剪裁、材质、配件与鞋履'
  const face=promptSegment(base,2,'Facial Features')||'保持角色完整提示词中的五官、骨相与身份识别特征'
  const hairstyle=promptSegment(base,3,'Hairstyle')
  const quality=promptSegment(base,6,'Technical Quality')||defaultCharacterTechnical
  return renderTurnaroundTemplate({服装:clothing,五官:face,发型段落:hairstyle?'；发型：'+hairstyle:'',技术质量:quality,角色完整设定:base})
}
function variantTurnaroundPrompt(character:WorldCharacter, variant:CharacterVariant) {
  const base = characterTurnaroundPrompt(character)
  return `${base}\n服装变体锁定：${variant.name}。${variant.wardrobe || variant.description}。${variant.hairstyle ? `发型状态：${variant.hairstyle}。` : ''}${variant.makeup ? `妆容状态：${variant.makeup}。` : ''}\n必须保持人物身份、五官、体型与基础形象一致，仅替换为该服装变体。`
}

async function loadResources() {
  if (!data.value) return
  const ids = new Set<number>()
  data.value.characters.forEach(item => { if (item.primary_resource_id) ids.add(item.primary_resource_id); (item.reference_resource_ids || []).forEach(id => ids.add(id)); item.variants.forEach(value => { if (value.primary_resource_id) ids.add(value.primary_resource_id!); (value.reference_resource_ids || []).forEach(id => ids.add(id)) }) })
  data.value.locations.forEach(item => { if (item.primary_resource_id) ids.add(item.primary_resource_id) }); data.value.props.forEach(item => { if (item.resource_id) ids.add(item.resource_id) }); data.value.asset_versions.forEach(item => { if (item.resource_id) ids.add(item.resource_id) })
  const settled = await Promise.allSettled([...ids].map(id => resourceApi.get(id))); const found: Record<number, ResourceItem> = {}
  settled.forEach(result => { if (result.status === 'fulfilled') found[result.value.id] = result.value }); resources.value = found; clearThumbs(); await loadThumbs(Object.values(found))
}
async function loadTurnaroundTemplate(){try{projectBrief.value=await shortDramaApi.brief(projectId.value);const saved=projectBrief.value?.constraints?.character_turnaround_prompt_template;turnaroundTemplate.value=typeof saved==='string'&&saved.trim()?saved:defaultTurnaroundTemplate;turnaroundTemplateDraft.value=turnaroundTemplate.value}catch(event:any){error.value=event.response?.data?.detail||'三视图通用提示词读取失败'}}
function editTurnaroundTemplate(){turnaroundTemplateDraft.value=turnaroundTemplate.value;turnaroundTemplateEditing.value=true}
function restoreTurnaroundTemplate(){turnaroundTemplateDraft.value=defaultTurnaroundTemplate}
async function saveTurnaroundTemplate(){if(!projectBrief.value||!turnaroundTemplateDraft.value.trim()||busy.value)return;busy.value=true;error.value='';try{const b=projectBrief.value;projectBrief.value=await shortDramaApi.saveBrief(projectId.value,{genre:b.genre,audience:b.audience,tone:b.tone,platform:b.platform,aspect_ratio:b.aspect_ratio,episode_count:b.episode_count,episode_duration:b.episode_duration,quality_tier:b.quality_tier,visual_style:b.visual_style,constraints:{...(b.constraints||{}),character_turnaround_prompt_template:turnaroundTemplateDraft.value.trim()},lock_version:b.lock_version});turnaroundTemplate.value=turnaroundTemplateDraft.value.trim();turnaroundTemplateEditing.value=false;notice.value='三视图通用提示词已保存'}catch(event:any){error.value=event.response?.data?.detail||'三视图通用提示词保存失败'}finally{busy.value=false}}
async function load() {
  loading.value = true; error.value = ''
  try {
    data.value = await shortDramaApi.phaseOneCasting(projectId.value)
    data.value.characters.forEach(item => { promptDrafts.value[key('character', item.id)] = latestPrompt('character',item.id,item.appearance || item.identity) }); data.value.locations.forEach(item => { promptDrafts.value[key('location', item.id)] = latestPrompt('location',item.id,item.description) }); data.value.props.forEach(item => { promptDrafts.value[key('prop', item.id)] = latestPrompt('prop',item.id,item.description || item.appearance) })
    if (wardrobe.value) wardrobe.value = data.value.characters.find(item => item.id === wardrobe.value?.id) || null
    await loadResources()
  } catch (event: any) { error.value = event.response?.data?.detail || '角色与场景加载失败' } finally { loading.value = false }
}
async function loadGenerationTypes() { try { const [types,providers,maintained]=await Promise.all([genTypeApi.list({ enabled: true }),imageProviderApi.list().catch(()=>[] as ImageProvider[]),settingsApi.getSelectOptions()]); generationSettings.value = maintained || {}; generationTypes.value = types.filter((item: any) => item.media_type === 'image'); generationTypeId.value = generationTypes.value.find(item => item.code === 't2i')?.id || generationTypes.value[0]?.id || null; imageProviders.value=providers.filter(item=>item.enabled); generationProviderId.value=(imageProviders.value.find(item=>item.is_default)||imageProviders.value[0])?.id||null; const sizeSetting=maintained?.image_size; imageSizeOptions.value=Array.isArray(sizeSetting?.options)?sizeSetting.options.map((item:any)=>({label:String(item.label),value:String(item.value)})):[]; const preferred=String(sizeSetting?.default_value||''); imageSize.value=imageSizeOptions.value.some(item=>item.value===preferred)?preferred:(imageSizeOptions.value[0]?.value||''); if(!generationProviderId.value)generationService.value='comfyui' } catch { generationTypes.value = []; imageProviders.value=[]; imageSizeOptions.value=[] } }
function characterPayload(item: WorldCharacter, patch: Record<string, unknown> = {}) { return { name: item.name, aliases: item.aliases, identity: item.identity, age_appearance: item.age_appearance, appearance: item.appearance, personality: item.personality, relationships: item.relationships, negative_traits: item.negative_traits, source_references: item.source_references, reference_resource_ids: item.reference_resource_ids, primary_resource_id: item.primary_resource_id, status: item.status, ...patch } }
function variantPayload(item:CharacterVariant,patch:Record<string,unknown>={}){return{name:item.name,description:item.description,wardrobe:item.wardrobe,hairstyle:item.hairstyle,makeup:item.makeup,primary_resource_id:item.primary_resource_id,reference_resource_ids:item.reference_resource_ids,source_references:item.source_references,status:item.status,version:item.version,is_default:item.is_default,...patch}}
function locationPayload(item: WorldLocation, patch: Record<string, unknown> = {}) { return { name: item.name, description: item.description, spatial_layout: item.spatial_layout, time_weather: item.time_weather, lighting: item.lighting, color_palette: item.color_palette, fixed_objects: item.fixed_objects, source_references: item.source_references, reference_resource_ids: item.reference_resource_ids, primary_resource_id: item.primary_resource_id, status: item.status, ...patch } }
function propPayload(item: WorldProp, patch: Record<string, unknown> = {}) { return { name: item.name, description: item.description, appearance: item.appearance, appearance_scope: item.appearance_scope, owner_character_id: item.owner_character_id, continuity_note: item.continuity_note, source_references: item.source_references, reference_resource_ids: item.reference_resource_ids, resource_id: item.resource_id, status: item.status, ...patch } }
async function setConfirmed(kind: CardKind, id: number, adoptedResourceId?: number | null) {
  if (!data.value) return
  // data.value still contains the pre-adoption resource ID here. Preserve the
  // newly adopted ID while confirming, otherwise this update clears the image.
  if (kind === 'character') { const item = data.value.characters.find(value => value.id === id); if (item) await shortDramaApi.updateWorldItem(projectId.value, 'characters', id, characterPayload(item, { status: 'confirmed', primary_resource_id: adoptedResourceId ?? item.primary_resource_id })) }
  else if (kind === 'location') { const item = data.value.locations.find(value => value.id === id); if (item) await shortDramaApi.updateWorldItem(projectId.value, 'locations', id, locationPayload(item, { status: 'confirmed', primary_resource_id: adoptedResourceId ?? item.primary_resource_id })) }
  else { const item = data.value.props.find(value => value.id === id); if (item) await shortDramaApi.updateWorldItem(projectId.value, 'props', id, propPayload(item, { status: 'confirmed', resource_id: adoptedResourceId ?? item.resource_id })) }
}
async function chooseAsset(items: ResourceItem[]) {
  const target = pickerTarget.value; const selected = items[0]; if (!target || !selected) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const turnaround = target.purpose === 'character_turnaround'
    const item = await shortDramaApi.createProjectAssetVersion(projectId.value, target.kind, target.id, {
      resource_id: selected.id,
      prompt: turnaround ? '从素材库关联角色三视图' : promptDrafts.value[key(target.kind, target.id)] || '从素材库采用',
      generation_snapshot: { purpose: turnaround ? 'character_turnaround' : 'default', source: selected.direction === 'output' ? 'generated' : 'upload', filename: selected.filename },
    })
    if (turnaround) {
      if (target.kind === 'character') {
        const character = data.value?.characters.find(value => value.id === target.id)
        if (character) await shortDramaApi.updateWorldItem(projectId.value, 'characters', character.id, characterPayload(character, { reference_resource_ids: [...new Set([...(character.reference_resource_ids || []), selected.id])] }))
      } else if (target.kind === 'variant') {
        for (const character of data.value?.characters || []) {
          const variant = character.variants.find(value => value.id === target.id)
          if (variant) { await shortDramaApi.updateCharacterVariant(projectId.value, character.id, variant.id, variantPayload(variant, { reference_resource_ids: [...new Set([...(variant.reference_resource_ids || []), selected.id])] })); break }
        }
      }
      notice.value = '已从素材库关联三视图「' + selected.filename + '」'
    } else {
      await shortDramaApi.adoptProjectAssetVersion(projectId.value, item.id)
      if (target.kind !== 'variant') await setConfirmed(target.kind, target.id, selected.id)
      notice.value = '已采用素材「' + selected.filename + '」'
    }
    await load()
  } catch (event: any) { error.value = event.response?.data?.detail || '采用素材失败' } finally { busy.value = false; pickerOpen.value = false; pickerTarget.value = null }
}
function openPicker(kind: AssetKind, id: number) { pickerTarget.value = { kind, id, purpose: 'default' }; pickerOpen.value = true }
function openTurnaroundPicker(kind:'character'|'variant',id:number){pickerTarget.value={kind,id,purpose:'character_turnaround'};pickerOpen.value=true}
async function adopt(version: ProjectAssetVersion) { busy.value = true; error.value = ''; try { await shortDramaApi.adoptProjectAssetVersion(projectId.value, version.id); if (version.entity_type !== 'variant') await setConfirmed(version.entity_type, version.entity_id, version.resource_id); notice.value = `已采用 v${version.version}`; await load() } catch (event: any) { error.value = event.response?.data?.detail || '采用版本失败' } finally { busy.value = false } }
function assetName(kind:AssetKind,id:number){if(!data.value)return `${kind} #${id}`;if(kind==='character')return data.value.characters.find(item=>item.id===id)?.name||`角色 #${id}`;if(kind==='location')return data.value.locations.find(item=>item.id===id)?.name||`场景 #${id}`;if(kind==='prop')return data.value.props.find(item=>item.id===id)?.name||`道具 #${id}`;for(const character of data.value.characters){const variant=character.variants.find(item=>item.id===id);if(variant)return `${character.name} · ${variant.name}`}return `服装变体 #${id}`}
function generate(kind: AssetKind, id: number, prompt: string, purpose:GenerationPurpose='default') { if (!prompt.trim()) { promptEditing.value = key(kind, id); notice.value = '请先补充视觉提示词'; return } workflowParamCache={};generationWorkflows.value=[];generationWorkflowId.value=null;generationParams.value={};generationDialog.value={kind,id,prompt,purpose};generationReferences.value=[];generationDialogError.value='';generationService.value=generationProviderId.value?'gemini':'comfyui' }
function generateCharacterTurnaround(item: WorldCharacter) { generate('character', item.id, characterTurnaroundPrompt(item), 'character_turnaround'); generationReferences.value = item.primary_resource_id ? [item.primary_resource_id] : [] }
function generateVariantTurnaround(character:WorldCharacter,item:CharacterVariant){generate('variant',item.id,variantTurnaroundPrompt(character,item),'character_turnaround');generationReferences.value=[character.primary_resource_id,item.primary_resource_id].filter((id):id is number=>!!id)}
async function copyGenerationPrompt(){if(!generationDialog.value)return;try{await navigator.clipboard.writeText(generationService.value==='comfyui'?currentComfyPrompt():generationDialog.value.prompt);notice.value='三视图提示词已复制'}catch{generationDialogError.value='浏览器未允许复制，请在提示词输入框中手动复制'}}
function currentComfyPrompt() {
  const field = promptParameter(generationWorkflow.value?.parameters || [])
  return field ? String(generationParams.value[field.key] || '') : generationDialog.value?.prompt || ''
}
function seedWorkflow(workflow: RuntimeWorkflow) {
  const params = workflowDefaults(workflow, generationSettings.value)
  const field = promptParameter(workflow.parameters)
  if (field) params[field.key] = generationDialog.value?.prompt || ''
  let cursor = 0
  for (const input of workflow.parameters.filter(p => p.type === 'image')) {
    if (input.multiple && generationReferences.value.length > cursor) { params[input.key] = generationReferences.value.slice(cursor); cursor = generationReferences.value.length }
    else if (generationReferences.value[cursor]) params[input.key] = generationReferences.value[cursor++]
  }
  return params
}
async function loadGenerationWorkflows() {
  const request = ++workflowRequest
  generationDialogError.value=''
  if (generationDialog.value && generationWorkflow.value) generationDialog.value.prompt = currentComfyPrompt()
  generationWorkflows.value=[]; generationWorkflowId.value=null; generationParams.value={}; workflowParamCache={}
  generationWorkflowError.value=''; generationWorkflowLoading.value=false
  if (!generationDialog.value || generationService.value !== 'comfyui' || !generationTypeId.value) return
  generationWorkflowLoading.value=true
  try {
    const active = await generationTypeConfigApi.active(generationTypeId.value)
    if (request !== workflowRequest) return
    generationWorkflows.value = active.workflows || []
    const workflow = generationWorkflows.value.find(w => w.is_default) || generationWorkflows.value[0]
    if (workflow) { generationWorkflowId.value=workflow.workflow_version_id; generationParams.value=seedWorkflow(workflow) }
    else generationWorkflowError.value='此生图类型没有可用工作流，请先在生成类型配置中绑定工作流。'
  } catch (event:any) {
    if (request === workflowRequest) generationWorkflowError.value=event.response?.data?.detail || '工作流加载失败，请重试'
  } finally { if (request === workflowRequest) generationWorkflowLoading.value=false }
}
function switchGenerationWorkflow(event: Event) {
  const nextId=Number((event.target as HTMLSelectElement).value)||null
  const next=generationWorkflows.value.find(w=>w.workflow_version_id===nextId)
  if (!next || nextId===generationWorkflowId.value) return
  generationDialogError.value=''
  const previous=generationWorkflow.value
  if (previous) workflowParamCache[String(previous.workflow_version_id)]=JSON.parse(JSON.stringify(generationParams.value))
  const values={...seedWorkflow(next),...migrateWorkflowParams(previous?.parameters||[],next.parameters,generationParams.value),...workflowParamCache[String(nextId)]}
  // Positive prompt fields can have different names across workflows.
  const oldPrompt=promptParameter(previous?.parameters||[]); const newPrompt=promptParameter(next.parameters)
  if (oldPrompt && newPrompt && !workflowParamCache[String(nextId)]) values[newPrompt.key]=generationParams.value[oldPrompt.key]
  generationWorkflowId.value=nextId; generationParams.value=values
}
function applyGenerationScheme(event: Event) {
  const id=(event.target as HTMLSelectElement).value
  const scheme=generationWorkflow.value?.parameter_schemes?.find(s=>String(s.id)===id)
  if (scheme) generationParams.value={...generationParams.value,...scheme.params,__scheme:id}
}
watch([generationDialog,generationTypeId,generationService],()=>void loadGenerationWorkflows())
async function submitGeneration() {
  const target=generationDialog.value
  if (!target || generationSubmitting.value) return
  const service=generationService.value
  const generationType=service==='gemini'?mixedGeneration.value:selectedGeneration.value
  generationDialogError.value=''
  if (!generationType) { generationDialogError.value=service==='gemini'?'请先启用“混合生图”生成类型':'请选择 ComfyUI 图片生成类型'; return }
  if (service==='gemini' && !generationProviderId.value) { generationDialogError.value='没有可用的 Gemini Image 提供方'; return }
  if (service==='gemini' && (!target.prompt.trim() || !imageSizeOptions.value.some(item=>item.value===imageSize.value))) { generationDialogError.value='请填写提示词并选择系统维护项中的图片尺寸'; return }
  const workflow=generationWorkflow.value
  if (service==='comfyui') {
    if (generationWorkflowLoading.value || !workflow || generationWorkflowError.value) { generationDialogError.value=generationWorkflowError.value || '请选择可用工作流'; return }
    const validation=workflowValidation(workflow.parameters,generationParams.value)
    if (validation) { generationDialogError.value=validation; return }
  }
  const assetContext={project_id:projectId.value,entity_type:target.kind,entity_id:target.id,purpose:target.purpose}
  const params:Record<string,any> = service==='gemini'
    ? {prompt:target.prompt,reference_resource_ids:[...generationReferences.value],size:imageSize.value,__execution_provider:'gemini_image',__provider_config_id:generationProviderId.value,__asset_context:assetContext}
    : {...workflowPayload(workflow!.parameters,generationParams.value),__asset_context:assetContext}
  const workflowVersionId=service==='comfyui'?workflow!.workflow_version_id:null
  const refs:number[]=service==='gemini'?[...generationReferences.value]:workflow!.parameters.filter(p=>p.type==='image').flatMap(p=>params[p.key]||[]).map(Number).filter(Boolean)
  const size=service==='gemini'?imageSize.value:params.size?String(params.size):params.width&&params.height?`${params.width}x${params.height}`:'工作流默认'
  const prompt=service==='gemini'?target.prompt:currentComfyPrompt()
  generationSubmitting.value=true
  try {
    const batch=await batchApi.create({name:`${target.kind}-${target.id}-${new Date().toLocaleString()}`,generation_type_id:generationType.id,rows:[{row_no:0,generation_type_id:generationType.id,workflow_version_id:workflowVersionId,params}]})
    const submitted=await batchApi.submit(batch.id); const tasks=await batchApi.rows(batch.id)
    if (!submitted.enqueued || !tasks[0]) throw new Error(tasks[0]?.error || '任务未能进入队列')
    generationTasks.value.unshift({id:tasks[0].id,batchId:batch.id,kind:target.kind,entityId:target.id,label:target.purpose==='character_turnaround'?`${assetName(target.kind,target.id)} · 三视图`:assetName(target.kind,target.id),prompt,purpose:target.purpose,service,references:refs,size,workflowVersionId,parameters:params,status:tasks[0].status,progress:5,error:'',outputId:null,finalized:false,finalizing:false})
    generationDialog.value=null; notice.value=`已添加「${assetName(target.kind,target.id)}」图片生成任务`;startGenerationPoll()
  } catch (event:any) { generationDialogError.value=event.response?.data?.detail||event.message||'生成任务创建失败' }
  finally { generationSubmitting.value=false }
}
function startGenerationPoll(){if(!generationTimer)generationTimer=setInterval(()=>void pollGenerationTasks(),1000);void pollGenerationTasks()}
function stopGenerationPoll(){if(generationTimer){clearInterval(generationTimer);generationTimer=null}}
async function pollGenerationJob(job:GenerationJob){if(job.finalized||job.finalizing||['FAILED','CANCELLED'].includes(job.status))return;try{const [task,events]=await Promise.all([taskApi.get(job.id),taskApi.events(job.id)]);job.status=task.status;job.error=task.error||'';job.progress=Math.max(job.progress,...events.map((event:any)=>Number(event.progress||0)));if(task.status==='SUCCESS'){job.finalizing=true;const outputs=await taskApi.outputs(job.id);const output=outputs.find((item:any)=>item.media_type==='image');if(!output)throw new Error('任务完成但没有图片输出');job.outputId=output.id;await load();let version=data.value?.asset_versions.find(item=>item.source_task_id===job.id&&item.entity_type===job.kind&&item.entity_id===job.entityId);if(!version)version=await shortDramaApi.createProjectAssetVersion(projectId.value,job.kind,job.entityId,{resource_id:output.id,source_task_id:job.id,prompt:job.prompt,generation_snapshot:{provider:job.service,size:job.size,purpose:job.purpose,reference_resource_ids:job.references,workflow_version_id:job.workflowVersionId,params:job.parameters}});if(job.purpose==='character_turnaround'){if(job.kind==='character'){const character=data.value?.characters.find(item=>item.id===job.entityId);if(character)await shortDramaApi.updateWorldItem(projectId.value,'characters',character.id,characterPayload(character,{reference_resource_ids:[...new Set([...(character.reference_resource_ids||[]),output.id])]}))}else if(job.kind==='variant'){for(const character of data.value?.characters||[]){const item=character.variants.find(value=>value.id===job.entityId);if(item){await shortDramaApi.updateCharacterVariant(projectId.value,character.id,item.id,variantPayload(item,{reference_resource_ids:[...new Set([...(item.reference_resource_ids||[]),output.id])]}));break}}}notice.value=`「${job.label}」生成完成，已自动关联并可在三视图中查看`}else if(version){await shortDramaApi.adoptProjectAssetVersion(projectId.value,version.id);if(version.entity_type!=='variant')await setConfirmed(version.entity_type,version.entity_id,output.id);notice.value=`「${job.label}」图片生成完成并已自动采用`}job.progress=100;job.finalized=true;job.finalizing=false;await load()}}catch(event:any){job.finalizing=false;job.status='FAILED';job.error=event.response?.data?.detail||event.message||'任务状态读取失败'}}
async function pollGenerationTasks(){await Promise.all(generationTasks.value.map(pollGenerationJob));if(!activeGenerationCount.value)stopGenerationPoll()}
function closeGenerationDialog(){if(generationSubmitting.value)return;generationDialog.value=null;generationDialogError.value=''}
function dismissGenerationTask(id:number){generationTasks.value=generationTasks.value.filter(item=>item.id!==id)}
function generationStatusLabel(job:GenerationJob){if(job.finalizing)return '正在采用';return ({PENDING:'等待中',DISPATCHING:'提交中',QUEUED:'排队中',RUNNING:'生成中',SUCCESS:'已完成',FAILED:'失败',CANCELLED:'已取消'} as Record<string,string>)[job.status]||job.status}
async function savePrompt(kind: CardKind, item: CastingItem) {
  busy.value = true; error.value = ''; let value = promptDrafts.value[key(kind, item.id)]?.trim() || ''
  if (kind === 'character') { value = characterPrompt(item as WorldCharacter, value); promptDrafts.value[key(kind, item.id)] = value }
  try { await shortDramaApi.createProjectAssetVersion(projectId.value,kind,item.id,{prompt:value,generation_snapshot:{purpose:'prompt_edit',director_skill:'short-drama-director@6.5'}}); promptEditing.value = ''; notice.value = '生成提示词已保存为新版本，业务描述保持不变'; await load() }
  catch (event: any) { error.value = event.response?.data?.detail || '提示词保存失败' } finally { busy.value = false }
}
async function removeItem(kind: CardKind, item: CastingItem) { if (!window.confirm(`删除“${item.name}”？已被镜头引用的实体将无法删除。`)) return; busy.value = true; error.value = ''; try { const endpoint = kind === 'character' ? 'characters' : kind === 'location' ? 'locations' : 'props'; await shortDramaApi.deleteWorldItem(projectId.value, endpoint, item.id); notice.value = `已删除“${item.name}”`; await load() } catch (event: any) { error.value = event.response?.data?.detail || '删除失败，请先处理关联镜头' } finally { busy.value = false } }
function copyName(kind: CardKind, source: string) {
  const items = kind === 'character' ? data.value?.characters : kind === 'location' ? data.value?.locations : data.value?.props
  const names = new Set((items || []).map(item => item.name))
  let name = `${source} 副本`, index = 2
  while (names.has(name)) name = `${source} 副本 ${index++}`
  return name
}
async function copyItem(kind: CardKind, item: CastingItem) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const copied = await shortDramaApi.copyProjectAsset(projectId.value, kind, item.id)
    await load()
    notice.value = `已复制${createLabel(kind)}“${item.name}”为“${copied.name}”；图片与素材版本未复制`
  } catch (event: any) {
    const detail = event.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((value:any) => value.msg).join('；') : `复制${createLabel(kind)}失败`
  } finally { busy.value = false }
}

function openCreate(kind: CardKind) {
  createDialog.value = kind
  createForm.value = { name: '', description: '', detail: '' }
  error.value = ''; notice.value = ''
}
function createLabel(kind: CardKind) { return kind === 'character' ? '角色' : kind === 'location' ? '场景' : '道具' }
async function submitCreate() {
  const kind = createDialog.value
  const name = createForm.value.name.trim()
  const description = createForm.value.description.trim()
  if (!kind || !name || !description || busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const endpoint = kind === 'character' ? 'characters' : kind === 'location' ? 'locations' : 'props'
    const common = { name, source_references: [], reference_resource_ids: [], status: 'draft' }
    const payload = kind === 'character'
      ? { ...common, aliases: [], identity: createForm.value.detail.trim(), age_appearance: '', appearance: description, personality: '', relationships: {}, negative_traits: [], primary_resource_id: null }
      : kind === 'location'
        ? { ...common, description, spatial_layout: createForm.value.detail.trim(), time_weather: '', lighting: '', color_palette: [], fixed_objects: [], primary_resource_id: null }
        : { ...common, description, appearance: description, appearance_scope: createForm.value.detail.trim(), owner_character_id: null, continuity_note: '', resource_id: null }
    const created = await shortDramaApi.createWorldItem(projectId.value, endpoint, payload)
    createDialog.value = null
    await load()
    notice.value = `已新增${createLabel(kind)}“${created.name}”，可继续生成图片或从素材库选择`
  } catch (event: any) { error.value = event.response?.data?.detail || `新增${createLabel(kind)}失败` } finally { busy.value = false }
}
async function addVariant() { if (!wardrobe.value || !variant.value.name.trim() || !variant.value.description.trim()) return; busy.value = true; error.value = ''; try { const created = await shortDramaApi.createCharacterVariant(projectId.value, wardrobe.value.id, { ...variant.value, wardrobe: '', hairstyle: '', makeup: '', primary_resource_id: null, reference_resource_ids: [], source_references: [], status: 'draft', version: wardrobe.value.variants.length + 1, is_default: false }); variant.value = { name: '', description: '' }; await load(); notice.value = `服装变体“${created.name}”已创建，请生成或选择图片` } catch (event: any) { error.value = event.response?.data?.detail || '服装变体创建失败' } finally { busy.value = false } }
async function removeVariant(item: CharacterVariant) { if (!wardrobe.value || item.is_default || !window.confirm(`删除服装变体“${item.name}”？`)) return; busy.value = true; error.value = ''; try { await shortDramaApi.deleteCharacterVariant(projectId.value, wardrobe.value.id, item.id); await load(); notice.value = '服装变体已删除' } catch (event: any) { error.value = event.response?.data?.detail || '该变体可能已被镜头引用，无法删除' } finally { busy.value = false } }
async function enterStoryboard() {
  if (!episodeId.value) { error.value = '请先选择分集'; return }
  busy.value = true; error.value = ''
  try {
    await shortDramaApi.confirmAssetAtlas(projectId.value, episodeId.value)
    await router.push('/v2/drama/projects/'+projectId.value+'/episodes/'+episodeId.value+'/spatial')
  } catch (event: any) { error.value = event.response?.data?.detail || '资产图册未通过 V6.5 门禁' }
  finally { busy.value = false }
}

onMounted(() => { void Promise.all([load(), loadGenerationTypes(), loadTurnaroundTemplate()]) });onUnmounted(stopGenerationPoll)
</script>

<template>
  <DramaProjectShell active="assets" page-title="数字资产包与资产图册" :save-state="busy ? '处理中…' : error ? '操作失败' : notice || '已保存'" :save-tone="error ? 'error' : 'normal'">
    <template #actions><button class="shell-action" @click="router.push('/v2/assets')">◇ 素材库</button></template>
    <div class="assets-page">
      <div v-if="loading" class="page-state">正在加载角色与场景…</div>
      <div v-else-if="!data" class="page-state error-state"><b>{{ error || '角色与场景加载失败' }}</b><button @click="load">重新加载</button></div>
      <template v-else>
        <header class="asset-toolbar"><div class="heading"><small>P2 · DIGITAL ASSET PACKAGE</small><h1>数字资产包与资产图册</h1><p>按 CHR / SCN / PRP 稳定键锁定角色、场景和连续性道具。资产图册是后续分镜的唯一事实源。</p></div><label><span>ComfyUI 默认类型</span><select v-model.number="generationTypeId" :disabled="generationSubmitting"><option v-if="!generationTypes.length" :value="null">图片生成未配置</option><option v-for="item in generationTypes" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span>Gemini 默认图片尺寸（维护项）</span><select v-model="imageSize"><option v-if="!imageSizeOptions.length" value="">未维护图片尺寸</option><option v-for="option in imageSizeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label><div class="binding" :class="{ ok: !!generationProviderId }"><span>Gemini Image</span><b>{{ generationProviderId ? '可用' : '未配置' }}</b></div></header>
        <section class="stage-summary"><nav aria-label="资产分类"><button :class="{ active: tab === 'characters' }" @click="tab = 'characters'">角色 {{ data.characters.length }}</button><button :class="{ active: tab === 'locations' }" @click="tab = 'locations'">场景 {{ data.locations.length }}</button><button :class="{ active: tab === 'props' }" @click="tab = 'props'">道具 {{ data.props.length }}</button></nav><span>{{ confirmedCount }}/{{ totalCount }} 已采用</span><span v-if="pendingRequired.length" class="gate-warning">还需确认 {{ pendingRequired.length }} 项</span><button class="add-asset" :disabled="busy" @click="openCreate(tab === 'characters' ? 'character' : tab === 'locations' ? 'location' : 'prop')">＋ 新增{{ tab === 'characters' ? '角色' : tab === 'locations' ? '场景' : '道具' }}</button><V2Button variant="primary" :disabled="!canEnterStoryboard" :title="pendingRequired.map(item => item.label).join('、')" @click="enterStoryboard">锁定资产图册并进入空间分镜 →</V2Button></section>
        <section v-if="tab==='characters'" class="turnaround-template-bar"><div><b>角色三视图通用提示词</b><span>统一控制所有角色及服装变体的三视图排版、画幅和质量要求</span></div><button class="template-edit" @click="editTurnaroundTemplate">✎ 编辑三视图通用提示词</button></section>
        <section v-if="generationTasks.length" class="generation-monitor" :class="{collapsed:!generationMonitorExpanded}" aria-label="图片生成任务监控"><header><div><small>AI IMAGE TASKS</small><h2>图片生成任务</h2><span class="monitor-current" :title="currentGenerationJob?.label">{{ currentGenerationJob ? `当前：${currentGenerationJob.label}` : '暂无任务' }}</span></div><div class="monitor-actions"><span>{{ activeGenerationCount }} 处理中 · {{ finishedGenerationCount }} 已完成 · 共 {{ generationTasks.length }} 项</span><button type="button" :aria-expanded="generationMonitorExpanded" @click="generationMonitorExpanded=!generationMonitorExpanded">{{ generationMonitorExpanded?'收起':'展开' }} {{ generationMonitorExpanded?'⌃':'⌄' }}</button></div></header><div v-if="generationMonitorExpanded" class="generation-job-list"><article v-for="job in generationTasks" :key="job.id" :class="{failed:job.status==='FAILED',done:job.finalized}"><img v-if="job.outputId" :src="resourceApi.fileUrl(job.outputId)" :alt="job.label"><div v-else class="job-icon">✣</div><div class="job-copy"><div><b>{{ job.label }}</b><small>#{{ job.id }} · {{ job.service==='gemini'?'Gemini':'ComfyUI' }} · {{ job.size }}</small></div><div class="progress"><i :style="{width:`${job.progress}%`}"/></div><p v-if="job.error">{{ job.error }}</p></div><span class="job-status">{{ generationStatusLabel(job) }} · {{ Math.round(job.progress) }}%</span><button v-if="job.finalized||['FAILED','CANCELLED'].includes(job.status)" aria-label="移除任务记录" @click="dismissGenerationTask(job.id)">×</button></article></div></section>
        <div v-if="notice || error" class="notice" :class="{ error: !!error }">{{ error || notice }}</div>

        <section v-if="tab === 'characters'" class="asset-grid">
          <article v-for="item in data.characters" :key="item.id" class="asset-card">
            <div class="character-head"><button class="media portrait" :disabled="!item.primary_resource_id" @click="previewAsset('character', item)"><img v-if="thumb('character', item)" :src="thumb('character', item)" :alt="item.name"><span v-else>{{ item.primary_resource_id ? '图片加载中' : '尚无角色形象' }}</span><i v-if="item.primary_resource_id">✓</i></button><div class="character-main"><div class="title-row"><div><h2>{{ item.name }}</h2><p>角色形象由提示词与当前采用图锁定</p></div><span class="status" :class="statusTone('character', item)">{{ statusLabel('character', item) }}</span></div><button class="wide" @click="wardrobe = item">♙ 服装变体 <small>{{ item.variants.length }}</small></button><div class="turnaround-card-actions"><button class="wide" @click="generateCharacterTurnaround(item)">▦ 生成角色三视图</button><button class="wide" @click="editTurnaroundTemplate">✎ 编辑通用提示词</button></div><div class="media-actions"><button @click="generate('character', item.id, promptDrafts[key('character', item.id)] || '')">✣ {{ item.primary_resource_id ? '重新生成' : '生成' }}</button><button @click="openPicker('character', item.id)">⇧ 上传/素材库</button></div></div></div>
            <section class="turnaround-gallery"><header><div><b>角色三视图</b><small>{{ latestTurnaroundVersions('character',item.id).length ? '已关联 · 显示当前图' : '尚未关联' }}</small></div><button class="turnaround-pick" :disabled="busy" @click="openTurnaroundPicker('character',item.id)">◇ 从素材库选择</button></header><div v-if="latestTurnaroundVersions('character',item.id).length"><button v-for="value in latestTurnaroundVersions('character',item.id)" :key="value.id" :disabled="!value.resource_id" @click="value.resource_id && previewResource(value.resource_id, item.name+'三视图')"><img v-if="value.resource_id" :src="thumbs[value.resource_id]" :alt="item.name+'三视图 v'+value.version"><span>查看 v{{ value.version }}</span></button></div><p v-else>尚未关联三视图，可生成或从素材库选择。</p></section>
            <div class="version-strip"><span>当前 {{ currentVersion('character', item.id) ? `v${currentVersion('character', item.id)?.version}` : '无采用版本' }}</span><button v-if="versions('character', item.id).length" @click="expandedVersions = expandedVersions === key('character', item.id) ? '' : key('character', item.id)">素材版本 {{ versions('character', item.id).length }}⌄</button></div><div v-if="expandedVersions === key('character', item.id)" class="versions"><button v-for="value in versions('character', item.id)" :key="value.id" :class="{ current: value.is_current }" :disabled="!value.resource_id || busy" @click="adopt(value)">v{{ value.version }} · {{ value.is_current ? '当前采用' : '采用' }}</button></div><section class="prompt"><header><b>▣ 角色提示词</b><button @click="promptEditing = key('character', item.id)">✎ 编辑</button></header><textarea v-if="promptEditing === key('character', item.id)" v-model="promptDrafts[key('character', item.id)]" rows="9"/><p v-else>{{ promptDrafts[key('character', item.id)] || '未设置提示词，点击编辑按钮添加视觉描述。' }}</p><div v-if="promptEditing === key('character', item.id)" class="edit-actions"><button @click="promptEditing = ''">取消</button><button class="primary" :disabled="busy" @click="savePrompt('character', item)">保存提示词</button></div></section><div class="card-actions"><button class="primary" :disabled="!promptDrafts[key('character', item.id)]" @click="generate('character', item.id, promptDrafts[key('character', item.id)] || '')">✣ 重新生成图片</button><button @click="openPicker('character', item.id)">◇ 从素材库替换</button><button :disabled="busy" @click="copyItem('character', item)">⧉ 复制角色</button><button class="danger" @click="removeItem('character', item)">删除角色</button></div>
          </article>
        </section>

        <section v-else-if="tab === 'locations'" class="asset-grid">
          <article v-for="item in data.locations" :key="item.id" class="asset-card compact-card">
            <button class="media landscape" :disabled="!item.primary_resource_id" @click="previewAsset('location', item)"><img v-if="thumb('location', item)" :src="thumb('location', item)" :alt="item.name"><span v-else>⌖<small>{{ item.primary_resource_id ? '图片加载中' : '生成或上传场景图片' }}</small></span><i v-if="item.primary_resource_id">✓</i></button>
            <div class="card-copy"><div class="title-row"><div><h2>{{ item.name }}</h2><p>{{ item.description || item.spatial_layout || '场景描述待补充' }}</p></div><span>{{ item.time_weather || '时间待定' }}</span></div>
              <div class="version-strip"><span class="status" :class="statusTone('location', item)">{{ statusLabel('location', item) }}</span><button v-if="versions('location', item.id).length" @click="expandedVersions = expandedVersions === key('location', item.id) ? '' : key('location', item.id)">素材版本 {{ versions('location', item.id).length }}⌄</button></div>
              <div v-if="expandedVersions === key('location', item.id)" class="versions"><button v-for="value in versions('location', item.id)" :key="value.id" :class="{ current: value.is_current }" :disabled="!value.resource_id" @click="adopt(value)">v{{ value.version }} · {{ value.is_current ? '当前' : '采用' }}</button></div>
              <section class="prompt"><header><b>▣ 场景提示词</b><button @click="promptEditing = key('location', item.id)">✎ 编辑</button></header><textarea v-if="promptEditing === key('location', item.id)" v-model="promptDrafts[key('location', item.id)]" rows="8"/><p v-else>{{ promptDrafts[key('location', item.id)] || '未设置提示词，点击编辑按钮添加视觉描述。' }}</p><div v-if="promptEditing === key('location', item.id)" class="edit-actions"><button @click="promptEditing = ''">取消</button><button class="primary" @click="savePrompt('location', item)">保存提示词</button></div></section>
              <div class="split-actions"><button :disabled="!promptDrafts[key('location', item.id)]" @click="generate('location', item.id, promptDrafts[key('location', item.id)] || '')">✣ {{ item.primary_resource_id ? '重新生成' : '生成' }}</button><button @click="openPicker('location', item.id)">⇧ 上传图片</button></div><button class="library" @click="openPicker('location', item.id)">◇ 从素材库选择/替换</button><button class="library" :disabled="busy" @click="copyItem('location', item)">⧉ 复制场景</button><button class="danger full" @click="removeItem('location', item)">删除场景</button>
            </div>
          </article>
        </section>
        <section v-else class="asset-grid">
          <article v-for="item in data.props" :key="item.id" class="asset-card compact-card">
            <button class="media landscape prop-media" :disabled="!item.resource_id" @click="previewAsset('prop', item)"><img v-if="thumb('prop', item)" :src="thumb('prop', item)" :alt="item.name"><span v-else>◇<small>{{ item.resource_id ? '图片加载中' : '生成或上传道具图片' }}</small></span><i v-if="item.resource_id">✓</i></button>
            <div class="card-copy"><div class="title-row"><div><h2>{{ item.name }}</h2><p>{{ item.description || item.appearance || '道具描述待补充' }}</p></div><span>{{ item.appearance_scope || '其他' }}</span></div><p v-if="item.continuity_note" class="continuity">连贯性：{{ item.continuity_note }}</p>
              <div class="version-strip"><span class="status" :class="statusTone('prop', item)">{{ statusLabel('prop', item) }}</span><button v-if="versions('prop', item.id).length" @click="expandedVersions = expandedVersions === key('prop', item.id) ? '' : key('prop', item.id)">素材版本 {{ versions('prop', item.id).length }}⌄</button></div>
              <div v-if="expandedVersions === key('prop', item.id)" class="versions"><button v-for="value in versions('prop', item.id)" :key="value.id" :class="{ current: value.is_current }" :disabled="!value.resource_id" @click="adopt(value)">v{{ value.version }} · {{ value.is_current ? '当前' : '采用' }}</button></div>
              <section class="prompt"><header><b>▣ 道具提示词</b><button @click="promptEditing = key('prop', item.id)">✎ 编辑</button></header><textarea v-if="promptEditing === key('prop', item.id)" v-model="promptDrafts[key('prop', item.id)]" rows="7"/><p v-else>{{ promptDrafts[key('prop', item.id)] || '未设置提示词，点击编辑按钮添加视觉描述。' }}</p><div v-if="promptEditing === key('prop', item.id)" class="edit-actions"><button @click="promptEditing = ''">取消</button><button class="primary" @click="savePrompt('prop', item)">保存提示词</button></div></section>
              <div class="split-actions"><button :disabled="!promptDrafts[key('prop', item.id)]" @click="generate('prop', item.id, promptDrafts[key('prop', item.id)] || '')">✣ {{ item.resource_id ? '重新生成' : '生成' }}</button><button @click="openPicker('prop', item.id)">⇧ 上传图片</button></div><button class="library" @click="openPicker('prop', item.id)">◇ 从素材库选择/替换</button><button class="library" :disabled="busy" @click="copyItem('prop', item)">⧉ 复制道具</button><button class="danger full" @click="removeItem('prop', item)">删除道具</button>
            </div>
          </article>
        </section>
      </template>

      <div v-if="createDialog" class="modal" role="dialog" aria-modal="true" :aria-label="'新增'+createLabel(createDialog)" @click.self="createDialog=null"><section class="create-dialog"><header><div><small>NEW ASSET</small><h2>新增{{ createLabel(createDialog) }}</h2></div><button aria-label="关闭" @click="createDialog=null">×</button></header><div class="create-form"><label><span>{{ createLabel(createDialog) }}名称</span><input v-model="createForm.name" maxlength="160" :placeholder="createDialog==='character'?'例如：苏沐橙':createDialog==='location'?'例如：化妆间':'例如：珍珠耳钉'" autofocus></label><label><span>{{ createDialog==='character'?'角色完整提示词':createDialog==='location'?'场景完整提示词':'道具完整提示词' }}</span><textarea v-model="createForm.description" rows="9" :placeholder="createDialog==='character'?'填写五官、发型、服装、体态和风格等合并描述':createDialog==='location'?'填写空间、天气、灯光、固定物和视觉风格等合并描述':'填写外观、材质、尺寸、状态和一致性要求'"></textarea></label><label><span>{{ createDialog==='character'?'身份说明（选填）':createDialog==='location'?'空间布局（选填）':'道具分类（选填）' }}</span><textarea v-if="createDialog!=='prop'" v-model="createForm.detail" rows="3"/><input v-else v-model="createForm.detail" placeholder="例如：随身道具"></label></div><footer><button @click="createDialog=null">取消</button><button class="primary" :disabled="busy||!createForm.name.trim()||!createForm.description.trim()" @click="submitCreate">{{busy?'新增中…':'确认新增'}}</button></footer></section></div>
      <div v-if="wardrobe" class="modal" role="dialog" aria-modal="true" aria-label="服装变体" @click.self="wardrobe = null"><section class="wardrobe-dialog"><header><div class="wardrobe-person"><span><img v-if="thumb('character', wardrobe)" :src="thumb('character', wardrobe)" :alt="wardrobe.name"></span><div><h2>{{ wardrobe.name }}</h2><small>LOOKS & VARIATIONS</small></div></div><button aria-label="关闭" @click="wardrobe = null">×</button></header><div class="wardrobe-grid"><section class="base"><h3>♙ BASE APPEARANCE</h3><div class="base-panel"><button class="base-image" :disabled="!wardrobe.primary_resource_id" @click="previewAsset('character', wardrobe)"><img v-if="thumb('character', wardrobe)" :src="thumb('character', wardrobe)" :alt="wardrobe.name"><span v-else>基础造型待生成</span><i>DEFAULT</i></button><p>{{ wardrobe.appearance || wardrobe.identity || '角色基础形象以提示词和当前采用图为准' }}</p><div class="turnaround-actions"><button class="turnaround-action" @click="generateCharacterTurnaround(wardrobe)">▦ 生成基础形象三视图</button><button class="turnaround-action" @click="openTurnaroundPicker('character',wardrobe.id)">◇ 从素材库选择</button></div><div v-if="latestTurnaroundVersions('character',wardrobe.id).length" class="turnaround-mini"><button v-for="value in latestTurnaroundVersions('character',wardrobe.id)" :key="value.id" :disabled="!value.resource_id" @click="value.resource_id && previewResource(value.resource_id, `${wardrobe.name}三视图`)"><img v-if="value.resource_id" :src="thumbs[value.resource_id]"><span>查看 v{{ value.version }}</span></button></div></div></section><section class="variations"><h3>♙ CHARACTER LOOKS</h3><article v-for="item in wardrobe.variants.filter(value => !value.is_default)" :key="item.id"><button class="variant-image" :disabled="!item.primary_resource_id" @click="previewAsset('variant', item)"><img v-if="thumb('variant', item)" :src="thumb('variant', item)" :alt="item.name"><span v-else>无图片</span></button><div><b>{{ item.name }}</b><p>{{ item.description }}</p><small>{{ statusLabel('variant', item) }} · {{ versions('variant', item.id).length }} 个版本</small><div><button @click="generate('variant', item.id, latestPrompt('variant',item.id,item.description))">生成形象</button><button @click="generateVariantTurnaround(wardrobe, item)">生成三视图</button><button @click="openTurnaroundPicker('variant',item.id)">选择三视图</button><button @click="openPicker('variant', item.id)">上传/素材库</button></div><div v-if="latestTurnaroundVersions('variant',item.id).length" class="turnaround-mini"><button v-for="value in latestTurnaroundVersions('variant',item.id)" :key="value.id" :disabled="!value.resource_id" @click="value.resource_id && previewResource(value.resource_id, `${wardrobe.name}${item.name}三视图`)"><img v-if="value.resource_id" :src="thumbs[value.resource_id]"><span>查看 v{{ value.version }}</span></button></div></div><button class="remove-variant" aria-label="删除变体" @click="removeVariant(item)">×</button></article><p v-if="!wardrobe.variants.some(value => !value.is_default)" class="empty-variation">还没有服装变体，请在下方创建。</p><div class="new"><input v-model="variant.name" placeholder="变体名称，例如：格子衫"><textarea v-model="variant.description" placeholder="造型完整描述（服装、发型、妆容和状态合并填写）"></textarea><V2Button variant="primary" :disabled="busy || !variant.name.trim() || !variant.description.trim()" @click="addVariant">＋ 添加服装变体</V2Button></div></section></div></section></div>
      <div v-if="turnaroundTemplateEditing" class="modal" role="dialog" aria-modal="true" aria-label="编辑三视图通用提示词" @click.self="turnaroundTemplateEditing=false"><section class="template-dialog"><header><div><small>CHARACTER TURNAROUND TEMPLATE</small><h2>三视图通用提示词</h2></div><button aria-label="关闭" @click="turnaroundTemplateEditing=false">×</button></header><p v-pre>支持变量：{{服装}}、{{五官}}、{{发型段落}}、{{技术质量}}、{{角色完整设定}}。</p><textarea v-model="turnaroundTemplateDraft" rows="16"/><footer><button @click="restoreTurnaroundTemplate">恢复默认</button><button @click="turnaroundTemplateEditing=false">取消</button><button class="primary" :disabled="busy||!turnaroundTemplateDraft.trim()" @click="saveTurnaroundTemplate">{{busy?'保存中…':'保存模板'}}</button></footer></section></div>
      <div v-if="generationDialog" class="modal" role="dialog" aria-modal="true" aria-label="图片生成" @click.self="closeGenerationDialog"><section class="generation-dialog"><header><div><small>IMAGE GENERATION</small><h2>{{ generationDialog.purpose==='character_turnaround'?'生成角色三视图':`生成${generationDialog.kind==='character'?'角色':generationDialog.kind==='location'?'场景':generationDialog.kind==='variant'?'服装变体':'道具'}图片` }}</h2></div><button aria-label="关闭" @click="closeGenerationDialog">×</button></header><div class="generation-form"><div class="service-field"><span>生成服务</span><div class="service-options"><button :class="{active:generationService==='gemini'}" :disabled="!generationProviderId||generationSubmitting" @click="generationService='gemini'">Gemini Image<small>支持 0～多张参考图</small></button><button :class="{active:generationService==='comfyui'}" :disabled="generationSubmitting" @click="generationService='comfyui'">ComfyUI<small>{{ selectedGeneration?.name||'未配置工作流' }}</small></button></div></div><label v-if="generationService==='gemini'"><span>Gemini 提供方</span><select v-model.number="generationProviderId" :disabled="generationSubmitting"><option v-for="provider in imageProviders" :key="provider.id" :value="provider.id">{{ provider.name }} · {{ provider.model }}</option></select></label><template v-if="generationService==='gemini'"><label><span>图片尺寸（来自系统维护项）</span><select v-model="imageSize" :disabled="generationSubmitting"><option v-if="!imageSizeOptions.length" value="">未维护图片尺寸</option><option v-for="option in imageSizeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label><label class="wide-field"><span>参考图片（可不添加，可多选）</span><MediaParameterField v-model="generationReferences" media-type="image" :multiple="true" :disabled="generationSubmitting" /></label><label class="wide-field"><span>提示词 <button v-if="generationDialog.purpose==='character_turnaround'" type="button" @click="copyGenerationPrompt">复制提示词</button></span><textarea v-model="generationDialog.prompt" rows="8" :disabled="generationSubmitting"/></label></template>
      <template v-else>
        <label><span>ComfyUI 生图类型</span><select v-model.number="generationTypeId" :disabled="generationSubmitting"><option v-if="!generationTypes.length" :value="null">暂无图片生成类型</option><option v-for="type in generationTypes" :key="type.id" :value="type.id">{{ type.name }}</option></select></label>
        <label><span>工作流</span><select :value="generationWorkflowId" :disabled="generationSubmitting||generationWorkflowLoading||!generationWorkflows.length" @change="switchGenerationWorkflow"><option :value="null" disabled>{{ generationWorkflowLoading?'正在加载工作流…':'请选择工作流' }}</option><option v-for="workflow in generationWorkflows" :key="workflow.workflow_version_id" :value="workflow.workflow_version_id">{{ workflow.name }} · v{{ workflow.version }}{{ workflow.is_default?'（默认）':'' }}</option></select></label>
        <p v-if="generationWorkflowLoading" class="generation-hint">正在读取与外部生图页面相同的工作流配置…</p>
        <p v-if="generationWorkflowError" class="generation-error">{{ generationWorkflowError }} <button :disabled="generationSubmitting" @click="loadGenerationWorkflows">重试</button></p>
        <template v-if="generationWorkflow && !generationWorkflowLoading">
          <label v-if="generationWorkflow.parameter_schemes?.length"><span>参数方案</span><select :value="generationParams.__scheme || ''" :disabled="generationSubmitting" @change="applyGenerationScheme"><option value="">自定义</option><option v-for="scheme in generationWorkflow.parameter_schemes" :key="scheme.id" :value="scheme.id">{{ scheme.name }}</option></select></label>
          <WorkflowParameterFields :key="generationWorkflowId!" v-model="generationParams" :parameters="generationWorkflow.parameters" :settings="generationSettings" :disabled="generationSubmitting" />
        </template>
      </template><p v-if="generationDialog.purpose==='character_turnaround'" class="generation-hint">已按技能模板填入三栏角色资产参考图提示词；任务完成后加入角色参考素材，不覆盖当前角色主图。</p><p v-if="generationDialogError" class="generation-error">{{ generationDialogError }}</p></div><footer><button @click="closeGenerationDialog">取消</button><button class="primary" :disabled="generationSubmitting || (generationService==='gemini' ? !generationDialog.prompt.trim()||!imageSize : generationWorkflowLoading||!generationWorkflow||!!generationWorkflowError)" @click="submitGeneration">{{ generationSubmitting?'正在添加…':'添加生成任务' }}</button></footer></section></div>
      <AssetPicker :open="pickerOpen" media-type="image" @close="pickerOpen = false" @select="chooseAsset"/>
      <MediaViewer :open="!!assetPreview" :output="assetPreview" @close="assetPreview = null"/>
    </div>
  </DramaProjectShell>
</template>

<style scoped>
.add-asset{margin-left:auto;min-height:38px;padding:0 14px;color:#684d2d;background:#fff8ed;border:1px solid #d8c09f;border-radius:8px;cursor:pointer;font-weight:650}.add-asset:disabled{opacity:.55}.stage-summary .add-asset+.v2-button{margin-left:0}.create-dialog{width:min(620px,100%);max-height:92vh;overflow:auto;color:#302a23;background:#fbfaf7;border-radius:16px}.create-dialog>header{height:70px;padding:0 22px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e5dfd6}.create-dialog h2{margin:3px 0 0}.create-dialog header small{color:#a58b67;font:9px ui-monospace,monospace;letter-spacing:.12em}.create-dialog header button{font-size:27px;background:none;border:0}.create-form{padding:22px;display:grid;gap:15px}.create-form label{display:grid;gap:7px}.create-form label span{color:#776e63;font-size:11px}.create-form input,.create-form textarea{width:100%;padding:10px;box-sizing:border-box;color:#302a23;background:#fff;border:1px solid #ded7cd;border-radius:8px;font:12px/1.6 inherit}.create-form textarea{resize:vertical}.create-dialog>footer{padding:14px 22px;display:flex;justify-content:flex-end;gap:8px;border-top:1px solid #e5dfd6}.create-dialog>footer button{min-width:96px;min-height:38px;border:1px solid #d9d1c6;border-radius:8px}
.assets-page{min-height:calc(100vh - 64px);padding:24px 28px 54px;color:#29251f;background:#fbfaf7;box-sizing:border-box}.shell-action{height:36px;padding:0 14px;color:#443d34;background:#fff;border:1px solid #dcd5ca;border-radius:8px;cursor:pointer}.page-state{min-height:65vh;display:grid;place-items:center;color:#7f766a}.error-state{align-content:center;gap:14px;color:#a43f3a}.asset-toolbar{display:grid;grid-template-columns:minmax(300px,1fr) 220px auto auto;align-items:end;gap:14px}.heading small{color:#a58b67;font:10px ui-monospace,monospace;letter-spacing:.14em}.heading h1{margin:5px 0 3px;font-size:29px}.heading p{margin:0;color:#7e756a;font-size:13px}.asset-toolbar label{display:grid;gap:6px}.asset-toolbar label span{color:#8b8175;font-size:10px}.asset-toolbar select{height:40px;padding:0 10px;color:#302a23;background:#fff;border:1px solid #ded7cd;border-radius:8px}.binding{height:40px;padding:0 12px;display:flex;align-items:center;gap:6px;color:#8a8176;background:#f1eee8;border:1px solid #ded7cd;border-radius:8px;box-sizing:border-box}.binding.ok b{color:#28875c}.ratio{height:40px;padding:3px;display:flex;background:#eeeae3;border:1px solid #ded7cd;border-radius:8px}.ratio button{padding:0 10px;color:#72695e;background:transparent;border:0;border-radius:6px;cursor:pointer}.ratio button.active{color:#fff;background:#a98455}.stage-summary{margin:22px 0 20px;padding-right:8px;min-height:58px;display:flex;align-items:center;gap:14px;background:#f4f1eb;border:1px solid #e2dcd2;border-radius:10px}.stage-summary nav{height:58px;display:flex}.stage-summary nav button{padding:0 20px;color:#70675d;background:none;border:0;border-bottom:2px solid transparent;cursor:pointer;font-weight:650}.stage-summary nav button.active{color:#241f19;border-color:#a98455}.stage-summary>span{color:#8a8176;font-size:12px}.stage-summary .gate-warning{color:#ad6b34}.stage-summary .v2-button{margin-left:auto}.turnaround-template-bar{margin:-10px 0 18px;padding:12px 14px;display:flex;align-items:center;justify-content:space-between;gap:14px;background:#fff8ed;border:1px solid #ddc8aa;border-radius:10px}.turnaround-template-bar>div{display:grid;gap:3px}.turnaround-template-bar span{color:#806f59;font-size:11px}.template-edit{min-height:34px;padding:6px 10px;color:#654d31;background:#fff;border:1px solid #d9c5a8;border-radius:7px;cursor:pointer}.notice{margin:-8px 0 16px;padding:10px 13px;color:#347354;background:#edf7f0;border:1px solid #cfe7d6;border-radius:8px;font-size:12px}.notice.error{color:#a43f3a;background:#fff0ef;border-color:#edcbc7}.asset-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;align-items:start}.asset-card{overflow:hidden;background:#fff;border:1px solid #dfd8ce;border-radius:14px;box-shadow:0 7px 20px rgba(75,58,36,.05)}.character-head{padding:16px;display:grid;grid-template-columns:minmax(130px,42%) 1fr;gap:14px}.media{position:relative;overflow:hidden;display:grid;place-items:center;color:#9c9388;background:#f2efe9;border:0;cursor:pointer}.media img{width:100%;height:100%;object-fit:cover}.media>i{position:absolute;right:8px;top:8px;width:27px;height:27px;display:grid;place-items:center;color:#fff;background:#b89463;border-radius:7px;font-style:normal}.media.portrait{min-height:160px;border-radius:10px}.media.landscape{width:100%;height:220px}.media>span{display:grid;place-items:center;gap:7px;font-size:30px}.media>span small{font-size:11px}.title-row{display:flex;justify-content:space-between;gap:10px}.title-row h2{margin:0;font-size:18px}.title-row p{margin:5px 0;color:#7c7368;font-size:12px;line-height:1.4}.title-row>span{height:max-content;padding:5px 7px;color:#7e756a;background:#f5f2ed;border-radius:6px;font-size:10px}.status{padding:5px 7px;border-radius:6px;font-size:10px}.status.ready{color:#287650;background:#e9f5ed}.status.candidate{color:#a2662b;background:#fff3df}.status.pending{color:#8b8175;background:#f0ede8}.wide,.media-actions button,.versions button{min-height:34px;color:#494139;background:#f7f4ef;border:1px solid #ded7cd;border-radius:7px;cursor:pointer}.wide{width:100%;margin:9px 0}.turnaround-card-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}.turnaround-card-actions .wide{font-size:11px}.media-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}.version-strip{padding:0 16px 10px;display:flex;align-items:center;justify-content:space-between;color:#8c8378;font-size:11px}.version-strip button{color:#786e63;background:none;border:0;cursor:pointer}.versions{margin:0 16px 10px;display:flex;gap:6px;flex-wrap:wrap}.versions button.current{color:#287650;background:#edf7f0;border-color:#cce5d4}.prompt{margin:0 16px 14px;border-top:1px solid #ece7df}.prompt header{padding:12px 0 8px;display:flex;justify-content:space-between}.prompt header button{background:none;border:0}.prompt>p,.prompt>textarea{width:100%;min-height:150px;margin:0;padding:11px;box-sizing:border-box;color:#665e55;background:#f4f1ec;border:1px solid #e2dcd3;border-radius:8px;font:11px/1.65 ui-monospace,monospace;white-space:pre-wrap;overflow:auto}.edit-actions{margin-top:8px;display:flex;justify-content:flex-end;gap:7px}.card-actions{padding:0 16px 16px;display:grid;gap:8px}.card-actions button,.edit-actions button{min-height:34px;border:1px solid #ded7cd;border-radius:7px}.primary{color:#fff!important;background:#211e1a!important}.danger{color:#bb3f3a!important;background:#fff!important;border-color:#edcbc7!important}.card-copy{padding:15px}.continuity{padding:8px 10px;background:#f7f2e9;font-size:11px}.modal{position:fixed;inset:0;z-index:1100;padding:20px;display:grid;place-items:center;background:rgba(33,28,22,.64)}.wardrobe-dialog{width:min(980px,100%);max-height:92vh;overflow:auto;background:#fbfaf7;border-radius:18px}.wardrobe-dialog>header{height:70px;padding:0 24px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e5dfd6}.wardrobe-dialog>header>button{font-size:27px;background:none;border:0}.wardrobe-person{display:flex;gap:11px;align-items:center}.wardrobe-person>span{width:38px;height:38px;overflow:hidden;border-radius:50%}.wardrobe-person img,.base-image img,.variant-image img{width:100%;height:100%;object-fit:cover}.wardrobe-person h2{margin:0}.wardrobe-person small{font:9px ui-monospace,monospace}.wardrobe-grid{padding:24px;display:grid;grid-template-columns:1fr 1fr;gap:28px}.wardrobe-grid h3{color:#756d63;font:11px ui-monospace,monospace}.base-panel,.variations>article,.new{padding:14px;background:#fff;border:1px solid #e2dcd3;border-radius:12px}.base-image{width:100%;height:300px;position:relative;overflow:hidden;border:0;border-radius:9px}.base-image i{position:absolute;left:8px;top:8px;padding:5px 8px;color:#fff;background:#332c25;border-radius:5px}.base-panel>p{max-height:210px;overflow:auto;font:11px/1.65 ui-monospace,monospace}.variations{display:grid;align-content:start;gap:11px}.variations>article{position:relative;display:grid;grid-template-columns:92px 1fr;gap:12px}.variant-image{width:92px;height:108px;border:0}.variations article p{margin:5px 0;font-size:11px}.variations article div div{display:flex;gap:8px}.remove-variant{position:absolute;right:8px;top:7px;border:0;background:none}.new{display:grid;gap:9px}.new input,.new textarea{padding:10px;border:1px solid #ded7cd;border-radius:8px}.new textarea{min-height:80px}@media(max-width:1250px){.asset-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.asset-toolbar{grid-template-columns:1fr 210px auto}}@media(max-width:820px){.assets-page{padding:18px 14px}.asset-toolbar,.asset-grid,.wardrobe-grid{grid-template-columns:1fr}.stage-summary{flex-wrap:wrap}.stage-summary nav{width:100%}.stage-summary nav button{flex:1}.character-head{grid-template-columns:135px 1fr}}@media(max-width:520px){.character-head{grid-template-columns:1fr}.media.portrait{height:250px}}
.split-actions{margin-bottom:8px;display:grid;grid-template-columns:1fr 1fr;gap:7px}.split-actions button,.library,.full{min-height:34px;color:#494139;background:#f7f4ef;border:1px solid #ded7cd;border-radius:7px;cursor:pointer}.library,.full{width:100%;margin-bottom:8px}.compact-card .version-strip{padding:5px 0 10px}.compact-card .versions{margin:0 0 10px}.compact-card .prompt{margin:0 0 13px}.compact-card .prompt>p{min-height:110px;max-height:180px}
.template-dialog{width:min(760px,100%);max-height:92vh;overflow:auto;padding:22px;color:#302a23;background:#fbfaf7;border-radius:16px;box-sizing:border-box}.template-dialog>header{display:flex;align-items:center;justify-content:space-between}.template-dialog h2{margin:4px 0}.template-dialog header small{color:#a58b67;font:9px ui-monospace,monospace;letter-spacing:.12em}.template-dialog header button{font-size:26px;background:none;border:0}.template-dialog>p{color:#776e63;font-size:12px;line-height:1.7}.template-dialog>textarea{width:100%;min-height:360px;padding:12px;box-sizing:border-box;color:#302a23;background:#fff;caret-color:#302a23;border:1px solid #ded7cd;border-radius:8px;font:12px/1.65 ui-monospace,monospace}.template-dialog>footer{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}.template-dialog>footer button{min-height:36px;padding:7px 13px;border:1px solid #d9d1c6;border-radius:7px}.generation-dialog{--v2-text:#302a23;--v2-text-subtle:#82776a;--v2-border:#ded7cd;--v2-surface-soft:#f4f1eb;--v2-primary:#8a6438;width:min(760px,100%);max-height:92vh;overflow:auto;color:#302a23;background:#fbfaf7;border-radius:18px}.generation-dialog>header{height:72px;padding:0 24px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e5dfd6}.generation-dialog>header h2{margin:3px 0 0}.generation-dialog>header small{color:#a58b67;font:9px ui-monospace,monospace;letter-spacing:.12em}.generation-dialog>header button{font-size:27px;background:none;border:0}.generation-form{padding:22px 24px;display:grid;grid-template-columns:1fr 1fr;gap:16px}.generation-form>label,.service-field{display:grid;align-content:start;gap:7px}.generation-form>label>span,.service-field>span{color:#776e63;font-size:11px}.generation-form>label>span button{float:right;padding:2px 7px;color:#765b38;background:#f6ede1;border:1px solid #d8c2a5;border-radius:5px;cursor:pointer}.generation-form select,.generation-form textarea{width:100%;padding:10px;box-sizing:border-box;color:#302a23;background:#fff;border:1px solid #ded7cd;border-radius:8px}.generation-form .wide-field,.generation-error,.generation-hint{grid-column:1/-1}.generation-hint{margin:0;padding:9px 11px;color:#6f604d;background:#f5efe6;border-radius:7px;font-size:11px}.generation-error{margin:0;padding:10px 12px;color:#a43f3a;background:#fff0ef;border:1px solid #edcbc7;border-radius:8px;font-size:12px}.service-options{display:grid;grid-template-columns:1fr 1fr;gap:8px}.service-options button{padding:10px;display:grid;gap:3px;color:#62594f;text-align:left;background:#fff;border:1px solid #ded7cd;border-radius:9px}.service-options button.active{color:#6f4e27;background:#f6ede1;border-color:#b99567}.service-options small{font-size:9px}.progress{height:7px;margin-top:10px;overflow:hidden;background:#ddd6cc;border-radius:10px}.progress i{height:100%;display:block;background:#a98455;transition:width .25s}.generation-dialog>footer{padding:14px 24px;display:flex;justify-content:flex-end;gap:8px;border-top:1px solid #e5dfd6}.generation-dialog>footer button{min-width:100px;min-height:38px;border:1px solid #d9d1c6;border-radius:8px}
.generation-form :deep(.field-label){color:#776e63}.generation-form :deep(input:not([type=checkbox])),.generation-form :deep(select),.generation-form :deep(textarea){color:#302a23;background:#fff;border-color:#ded7cd}.generation-form :deep(input[type=checkbox]){width:auto}.generation-form :deep(.v2-field small){color:#82776a}@media(max-width:600px){.generation-form{grid-template-columns:1fr}}
.generation-monitor{margin:-6px 0 14px;padding:9px 11px;background:#fff;border:1px solid #ddd6cc;border-radius:10px;box-shadow:0 4px 12px rgba(75,58,36,.04)}.generation-monitor>header{min-height:28px;display:flex;align-items:center;justify-content:space-between;gap:12px}.generation-monitor>header>div:first-child{display:flex;align-items:baseline;gap:8px;min-width:0}.generation-monitor>header small{color:#a58b67;font:8px ui-monospace,monospace;letter-spacing:.1em;white-space:nowrap}.generation-monitor>header h2{margin:0;font-size:13px;white-space:nowrap}.monitor-current{min-width:0;overflow:hidden;color:#6f665c;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.monitor-actions{display:flex;align-items:center;gap:7px;flex:0 0 auto}.monitor-actions>span{padding:3px 7px;color:#7d5e35;background:#f7efe3;border-radius:6px;font-size:9px;white-space:nowrap}.monitor-actions>button{height:24px;padding:0 7px;color:#665c50;background:#f4f1eb;border:1px solid #ddd6cc;border-radius:5px;font-size:9px;cursor:pointer}.generation-monitor.collapsed{margin-bottom:10px;padding-top:7px;padding-bottom:7px}.generation-job-list{max-height:420px;margin-top:8px;padding:2px;display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px;overflow:auto}.generation-job-list article{position:relative;min-height:132px;padding:9px;display:grid;grid-template-columns:58px minmax(0,1fr);grid-template-rows:auto auto;align-items:start;gap:8px;background:#f7f4ef;border:1px solid #e2dcd3;border-radius:9px}.generation-job-list article.done{background:#eff7f1;border-color:#cfe4d4}.generation-job-list article.failed{background:#fff1f0;border-color:#eccdca}.generation-job-list article>img,.job-icon{width:58px;height:58px;object-fit:cover;background:#ebe6de;border-radius:7px}.job-icon{display:grid;place-items:center;color:#9b835f;font-size:15px}.job-copy{min-width:0}.job-copy>div:first-child{display:flex;align-items:baseline;gap:7px;min-width:0}.job-copy b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.job-copy small{color:#8b8175;font-size:8px;white-space:nowrap}.job-copy p{margin:3px 0 0;overflow:hidden;color:#9a423e;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.generation-job-list .progress{height:3px;margin-top:5px}.job-status{grid-column:1/-1;padding:5px 7px;color:#6e6255;background:#eee8df;border-radius:5px;font-size:9px;text-align:center;white-space:nowrap}.generation-job-list article>button{position:absolute;right:4px;top:4px;width:22px;height:22px;color:#80766a;background:rgba(255,255,255,.82);border:0;border-radius:5px;font-size:15px}.generation-job-list article>button:hover{background:#e6dfd5}@media(max-width:700px){.generation-job-list{max-height:190px}.generation-job-list article{grid-template-columns:32px minmax(0,1fr) auto}.generation-job-list article>img,.job-icon{width:32px;height:32px}.job-status{grid-column:auto}.generation-job-list article>button{position:absolute;right:3px;top:3px}.generation-monitor>header small{display:none}.monitor-current{max-width:180px}.monitor-actions>span{display:none}}
.turnaround-gallery{margin:0 16px 12px;padding:11px;background:#f6f2eb;border:1px solid #e0d7ca;border-radius:10px}.turnaround-gallery header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.turnaround-gallery header>div{display:grid;gap:2px}.turnaround-gallery header small{color:#8b8175}.turnaround-gallery>p{margin:5px 0;color:#8b8175;font-size:11px}.turnaround-pick{padding:5px 8px;color:#654d31;background:#fff;border:1px solid #d9c5a8;border-radius:6px;cursor:pointer}.turnaround-gallery>div,.turnaround-mini{display:flex!important;gap:8px!important;overflow:auto}.turnaround-gallery>div>button,.turnaround-mini button{position:relative;flex:0 0 128px;height:76px;padding:0;overflow:hidden;background:#ece6dc;border:1px solid #d9cfbf;border-radius:8px}.turnaround-gallery>div img,.turnaround-mini img{width:100%;height:100%;object-fit:cover}.turnaround-gallery>div button span,.turnaround-mini button span{position:absolute;left:5px;bottom:5px;padding:3px 6px;color:#fff;background:rgba(34,29,23,.76);border-radius:4px;font-size:9px}.turnaround-actions{display:grid!important;grid-template-columns:1fr 1fr;gap:8px!important}.turnaround-action{width:100%;min-height:35px;color:#5d4a32;background:#f7efe3;border:1px solid #d9c5a8;border-radius:7px}.turnaround-mini{margin-top:8px}.turnaround-mini button{flex-basis:96px;height:62px}
</style>
