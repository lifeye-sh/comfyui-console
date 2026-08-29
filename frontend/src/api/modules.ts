import { http } from './client'

export const authApi = {
  login: (username: string, password: string) =>
    http.post('/auth/login', { username, password }).then((r) => r.data),
  me: () => http.get('/auth/me').then((r) => r.data),
}

export const dashboardApi = {
  summary: () => http.get('/dashboard/summary').then((r) => r.data),
}

export type ShortDramaStatus = {
  enabled: boolean
  version: '2.1'
  stage: 'foundation' | 'document_import' | 'screenplay' | 'world_setting' | 'storyboard' | 'production'
  capabilities: {
    projects: boolean
    story_import: boolean
    story_bible: boolean
    storyboard: boolean
    task_bridge: boolean
    screenplay: boolean
    world_setting: boolean
    ai_adaptation: boolean
  }
}

export type ShortDramaProject = {
  id: number
  owner_id: number
  name: string
  synopsis: string
  source_type: 'idea' | 'outline' | 'script' | 'novel'
  status: string
  stage: string
  cover_resource_id: number | null
  settings: Record<string, unknown>
  lock_version: number
  deleted_at: string | null
  created_at: string
  updated_at: string
}

export type ShortDramaBrief = {
  id: number
  owner_id: number
  project_id: number
  genre: string
  audience: string
  tone: string
  platform: string
  aspect_ratio: string
  episode_count: number
  episode_duration: number
  quality_tier: 'draft' | 'standard' | 'final'
  visual_style: string
  constraints: Record<string, unknown>
  lock_version: number
  created_at: string
  updated_at: string
}

export type ShortDramaProjectSummary = ShortDramaProject & {
  episode_count: number
  scene_count: number
  shot_count: number
}

export type ShortDramaOverview = {
  project: ShortDramaProject
  brief: ShortDramaBrief
  episode_count: number
  scene_count: number
  shot_count: number
  take_count: number
  selected_take_count: number
  creative_job_count: number
  active_job_count: number
}

export type ShortDramaDocument = {
  id: number
  owner_id: number
  project_id: number
  resource_id: number
  filename: string
  source_format: 'txt' | 'docx' | 'epub'
  title: string
  encoding: string | null
  status: string
  total_chapters: number
  total_paragraphs: number
  total_chars: number
  error: string | null
  created_at: string
  updated_at: string
}

export type CreativeJobLog = { time: string; level: string; message: string }

export type CreativeJob = {
  id: number
  owner_id: number
  project_id: number | null
  job_type: string
  status: string
  progress: number
  input_payload: Record<string, unknown>
  output_payload: Record<string, unknown>
  logs: CreativeJobLog[]
  error: string | null
  retries: number
  heartbeat_at: string | null
  started_at: string | null
  finished_at: string | null
  cancelled_at: string | null
  parent_job_id: number | null
  provider_config_id: number | null
  prompt_template_id: number | null
  model: string | null
  token_usage: { input_tokens?: number; output_tokens?: number; total_tokens?: number }
  estimated_cost: number
  created_at: string
  updated_at: string
}

export type SourceParagraph = { id: number; paragraph_index: number; text: string; char_count: number; source_locator: string }
export type SourceChapter = { id: number; number: number; title: string | null; char_count: number; paragraphs: SourceParagraph[] }
export type SourceContent = { document: ShortDramaDocument; chapters: SourceChapter[] }
export type AIProvider = {id:number;name:string;provider:string;base_url:string;model:string;api_key_hint:string;enabled:boolean;is_default:boolean;timeout_seconds:number;max_tokens:number;created_at:string;updated_at:string}
export type ImageProvider = {id:number;name:string;provider:'gemini_web2api'|'gemini_proxy';base_url:string;model:string;api_key_hint:string;enabled:boolean;is_default:boolean;timeout_seconds:number;max_concurrency:number;created_at:string;updated_at:string}
export type NovelAnalysis = {id:number;owner_id:number;project_id:number;document_id:number;generation_record_id:number|null;version:number;status:string;chapter_start:number;chapter_end:number;content:Record<string,any>;validation_errors:Array<Record<string,any>>;confirmed_at:string|null;created_at:string;updated_at:string}

export type AdaptationOption = {
  key: string
  label: string
  description: string
  metrics: { episode_count: number; source_chapters: number; pace_ratio: number }
  episodes: Array<Record<string, unknown>>
}
export type AdaptationCandidate = {
  id: number; owner_id: number; project_id: number; document_id: number
  chapter_start: number; chapter_end: number; status: string
  options: AdaptationOption[]; validation_errors: Array<Record<string, unknown>>
  confirmed_option: string | null; confirmed_version_id: number | null
  created_at: string; updated_at: string
}
export type ScreenplayElement = { type: 'action' | 'dialogue' | 'narration' | 'transition'; text: string; speaker?: string }
export type SourceReference = { document_id: number; chapter_number: number; paragraph_start: number; paragraph_end: number }
export type DramaScene = {
  id: number; owner_id: number; episode_id: number; scene_no: string; heading: string
  location_name: string; time_of_day: string; interior_exterior: string; content: string
  elements: ScreenplayElement[]; source_references: SourceReference[]; character_ids: number[]; location_id: number | null; purpose: string
  target_duration: number; sort_order: number; status: string; lock_version: number
  created_at: string; updated_at: string
}
export type DramaEpisode = {
  id: number; owner_id: number; project_id: number; number: number; title: string; synopsis: string
  target_duration: number; core_conflict: string; emotional_arc: string; opening_hook: string; ending_hook: string; is_locked: boolean
  sort_order: number; status: string; lock_version: number
  created_at: string; updated_at: string; scenes: DramaScene[]
}
export type ScreenplayRevisionCandidate = {
  id:number;owner_id:number;project_id:number;episode_id:number;generation_record_id:number|null;base_lock_version:number
  status:string;instruction:string;content:Record<string,any>;validation_errors:Array<Record<string,any>>
  confirmed_version_id:number|null;confirmed_at:string|null;created_at:string;updated_at:string
}
export type Screenplay = { project: ShortDramaProject; episodes: DramaEpisode[]; current_version_id: number | null; draft_changed: boolean }
export type StoryVersion = {
  id: number; owner_id: number; project_id: number; parent_version_id: number | null; version: number
  name: string; source: string; summary: string; content: Record<string, any>; is_current: boolean
  created_at: string; updated_at: string
}
export type WorldCandidate = {
  id: number; owner_id: number; project_id: number; story_version_id: number | null; status: string
  payload: Record<string, any>; conflicts: Array<Record<string, any>>; confirmed_at: string | null
  created_at: string; updated_at: string
}
export type WorldCharacter = {
  id: number; owner_id: number; project_id: number; name: string; aliases: string[]; identity: string
  age_appearance: string; appearance: string; personality: string; relationships: Record<string, any>
  negative_traits: string[]; source_references: SourceReference[]; reference_resource_ids: number[]
  primary_resource_id: number | null; status: 'draft' | 'confirmed'; variants: CharacterVariant[]; created_at: string; updated_at: string
}
export type CharacterVariant = { id: number; owner_id: number; character_id: number; name: string; description: string; wardrobe: string; hairstyle: string; makeup: string; primary_resource_id: number|null; reference_resource_ids: number[]; source_references: SourceReference[]; status:'draft'|'confirmed';version:number;is_default:boolean;created_at: string; updated_at: string }
export type WorldLocation = {
  id: number; owner_id: number; project_id: number; name: string; description: string; spatial_layout: string
  time_weather: string; lighting: string; color_palette: string[]; fixed_objects: string[]
  source_references: SourceReference[]; reference_resource_ids: number[]; primary_resource_id: number | null
  status: 'draft' | 'confirmed'; created_at: string; updated_at: string
}
export type WorldProp = {
  id: number; owner_id: number; project_id: number; name: string; description: string; appearance: string
  appearance_scope: string; owner_character_id: number | null; continuity_note: string
  source_references: SourceReference[]; reference_resource_ids: number[]; resource_id: number | null
  status: 'draft' | 'confirmed'; created_at: string; updated_at: string
}
export type WorldRelationship = {
  id: number; owner_id: number; project_id: number; source_character_id: number; target_character_id: number
  relationship_type: string; description: string; source_references: SourceReference[]
  status: 'draft' | 'confirmed'; created_at: string; updated_at: string
}
export type WorldOverview = { characters: WorldCharacter[]; locations: WorldLocation[]; props: WorldProp[]; relationships: WorldRelationship[] }
export type DramaShot = {
  id:number;owner_id:number;scene_id:number;source_story_version_id:number|null;shot_no:number;sort_order:number
  purpose:string;visual_description:string;action:string;expression:string;dialogue:string;character_ids:number[]
  location_id:number|null;prop_ids:number[];mood:string;shot_size:string;camera_angle:string;camera_movement:string
  composition:string;transition:string;duration:number;first_frame_resource_id:number|null;last_frame_resource_id:number|null
  pose_resource_id:number|null;reference_video_resource_id:number|null;reference_audio_resource_id:number|null
  reference_resource_ids:number[];status:'draft'|'ready';production_settings:Record<string,any>;lock_version:number
  created_at:string;updated_at:string
}
export type StoryboardScene = {scene:DramaScene;shots:DramaShot[];shot_duration:number;target_duration:number;duration_delta:number;blockers:string[]}
export type StoryboardEpisode = {episode:DramaEpisode;scenes:StoryboardScene[]}
export type Storyboard = {project:ShortDramaProject;episodes:StoryboardEpisode[];total_shots:number;ready_shots:number;total_duration:number}
export type StoryboardCandidate = {id:number;owner_id:number;project_id:number;scene_id:number;story_version_id:number;status:string;payload:{shots:Array<Record<string,any>>;target_duration:number;existing_shots:number};validation_warnings:Array<{code:string;message:string}>;confirmed_mode:string|null;confirmed_at:string|null;created_at:string;updated_at:string}
export type CompiledShotTask = {shot_id:number;generation_type_id:number;generation_type_name:string;media_type:'image'|'video'|'audio';workflow_version_id:number;workflow_name:string;params:Record<string,any>;prompt:string;input_resource_ids:number[];validation_errors:Array<{path:string;code:string;message:string}>;validation_warnings:Array<{path:string;code:string;message:string}>}
export type ShotTaskLink = {id:number;owner_id:number;shot_id:number;task_id:number;take_id:number|null;purpose:string;status:string;idempotency_key:string;output_payload:Record<string,any>;sync_error:string|null;sync_attempts:number;next_retry_at:string|null;created_at:string;updated_at:string}
export type DramaTake = {id:number;owner_id:number;shot_id:number;resource_id:number;source_task_id:number|null;take_no:number;status:string;is_selected:boolean;generation_snapshot:Record<string,any>;review_note:string;resource:{id:number;filename:string;media_type:'image'|'video'|'audio';mime:string;width:number|null;height:number|null;duration:number|null;size:number};created_at:string;updated_at:string}
export type ShotProduction = {shot:DramaShot;tasks:Array<{link:ShotTaskLink;task_status:string;task_error:string|null;generation_type_id:number|null;workflow_version_id:number|null;params:Record<string,any>;created_at:string}>;takes:DramaTake[]}
export type EpisodeScript = {episode_id:number;project_id:number;title:string;mode:'novel'|'storyboard';text:string;settings:Record<string,any>;script_revision:number;lock_version:number;updated_at:string;diagnostics:{gates:Array<Record<string,any>>;dialogues:Array<Record<string,any>>;suggestions:Array<Record<string,any>>;summary:Record<string,number>;all_rules_are_advisory:boolean}}
export type ScriptManifest = {id:number;owner_id:number;project_id:number;episode_id:number;version:number;status:string;source_script_revision:number;mode:'novel'|'storyboard';summary:string;total_duration:number;content:{story_summary:string;scenes:Array<Record<string,any>>;characters:Array<Record<string,any>>;locations:Array<Record<string,any>>;props:Array<Record<string,any>>};validation_errors:Array<{severity:'p0'|'p1'|'p2';path:string;message:string;actionable?:boolean;action?:string;action_label?:string;action_payload?:Record<string,any>}>;lock_version:number;confirmed_at:string|null;created_at:string;updated_at:string}
export type ProjectAssetVersion = {id:number;owner_id:number;project_id:number;entity_type:'character'|'variant'|'location'|'prop';entity_id:number;version:number;resource_id:number|null;source_task_id:number|null;status:string;is_current:boolean;prompt:string;generation_snapshot:Record<string,any>;created_at:string;updated_at:string}
export type PhaseOneCasting = {characters:WorldCharacter[];locations:WorldLocation[];props:WorldProp[];asset_versions:ProjectAssetVersion[]}

export const shortDramaApi = {
  status: () => http.get('/short-drama/status', { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaStatus),
  projects: (params?: Record<string, unknown>) => http.get('/short-drama/projects', { baseURL: '/api/v2', params }).then((r) => r.data as { items: ShortDramaProjectSummary[]; total: number; page: number; page_size: number }),
  createProject: (body: Record<string, unknown>) => http.post('/short-drama/projects', body, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaProject),
  quickCreateProject: (body: Record<string, unknown>) => http.post('/short-drama/projects/quick-create', body, { baseURL: '/api/v2' }).then((r) => r.data as {project:ShortDramaProject;episode_id:number}),
  project: (id: number) => http.get(`/short-drama/projects/${id}`, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaProject),
  patchProject: (id: number, body: Record<string, unknown>) => http.patch(`/short-drama/projects/${id}`, body, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaProject),
  deleteProject: (id: number) => http.delete(`/short-drama/projects/${id}`, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaProject),
  restoreProject: (id: number) => http.post(`/short-drama/projects/${id}/restore`, null, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaProject),
  brief: (id: number) => http.get(`/short-drama/projects/${id}/brief`, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaBrief),
  saveBrief: (id: number, body: Record<string, unknown>) => http.put(`/short-drama/projects/${id}/brief`, body, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaBrief),
  overview: (id: number) => http.get(`/short-drama/projects/${id}/overview`, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaOverview),
  episodeScript: (projectId:number,episodeId:number) => http.get(`/short-drama/projects/${projectId}/episodes/${episodeId}/script`,{baseURL:'/api/v2'}).then(r=>r.data as EpisodeScript),
  saveEpisodeScript: (projectId:number,episodeId:number,body:Record<string,unknown>) => http.patch(`/short-drama/projects/${projectId}/episodes/${episodeId}/script`,body,{baseURL:'/api/v2'}).then(r=>r.data as EpisodeScript),
  generateScriptManifest: (projectId:number,episodeId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/episodes/${episodeId}/manifests/generate`,body,{baseURL:'/api/v2'}).then(r=>r.data as CreativeJob),
  scriptManifests: (projectId:number,episodeId:number) => http.get(`/short-drama/projects/${projectId}/episodes/${episodeId}/manifests`,{baseURL:'/api/v2'}).then(r=>r.data as ScriptManifest[]),
  saveScriptManifest: (projectId:number,episodeId:number,manifestId:number,body:Record<string,unknown>) => http.patch(`/short-drama/projects/${projectId}/episodes/${episodeId}/manifests/${manifestId}`,body,{baseURL:'/api/v2'}).then(r=>r.data as ScriptManifest),
  confirmScriptManifest: (projectId:number,episodeId:number,manifestId:number) => http.post(`/short-drama/projects/${projectId}/episodes/${episodeId}/manifests/${manifestId}/confirm`,null,{baseURL:'/api/v2'}).then(r=>r.data as ScriptManifest),
  phaseOneCasting: (projectId:number) => http.get(`/short-drama/projects/${projectId}/casting`,{baseURL:'/api/v2'}).then(r=>r.data as PhaseOneCasting),
  createProjectAssetVersion: (projectId:number,entityType:string,entityId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/assets/${entityType}/${entityId}/versions`,body,{baseURL:'/api/v2'}).then(r=>r.data as ProjectAssetVersion),
  adoptProjectAssetVersion: (projectId:number,versionId:number) => http.post(`/short-drama/projects/${projectId}/asset-versions/${versionId}/adopt`,null,{baseURL:'/api/v2'}).then(r=>r.data as ProjectAssetVersion),
  bindShotCharacter: (projectId:number,shotId:number,body:Record<string,unknown>) => http.put(`/short-drama/projects/${projectId}/shots/${shotId}/character-binding`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  documents: (id: number) => http.get(`/short-drama/projects/${id}/documents`, { baseURL: '/api/v2' }).then((r) => r.data as ShortDramaDocument[]),
  importDocument: (id: number, file: File, onProgress?: (percent: number) => void) => {
    const body = new FormData()
    body.append('file', file)
    return http.post(`/short-drama/projects/${id}/imports`, body, {
      baseURL: '/api/v2',
      onUploadProgress: (event) => {
        if (event.total) onProgress?.(Math.round((event.loaded / event.total) * 100))
      },
    }).then((r) => r.data as { document: ShortDramaDocument; job: CreativeJob })
  },
  jobs: (params?: Record<string, unknown>) => http.get('/short-drama/jobs', { baseURL: '/api/v2', params }).then((r) => r.data as { items: CreativeJob[]; total: number; page: number; page_size: number }),
  job: (id: number) => http.get(`/short-drama/jobs/${id}`, { baseURL: '/api/v2' }).then((r) => r.data as CreativeJob),
  cancelJob: (id: number) => http.post(`/short-drama/jobs/${id}/cancel`, null, { baseURL: '/api/v2' }).then((r) => r.data as CreativeJob),
  retryJob: (id: number) => http.post(`/short-drama/jobs/${id}/retry`, null, { baseURL: '/api/v2' }).then((r) => r.data as CreativeJob),
  aiProviders: () => http.get('/short-drama/ai/providers', { baseURL: '/api/v2' }).then(r=>r.data as AIProvider[]),
  createAIProvider: (body:Record<string,unknown>) => http.post('/short-drama/ai/providers',body,{baseURL:'/api/v2'}).then(r=>r.data as AIProvider),
  updateAIProvider: (id:number,body:Record<string,unknown>) => http.put(`/short-drama/ai/providers/${id}`,body,{baseURL:'/api/v2'}).then(r=>r.data as AIProvider),
  deleteAIProvider: (id:number) => http.delete(`/short-drama/ai/providers/${id}`,{baseURL:'/api/v2'}),
  testAIProvider: (id:number) => http.post(`/short-drama/ai/providers/${id}/test`,null,{baseURL:'/api/v2'}).then(r=>r.data as {ok:boolean;model:string;latency_ms:number}),
  // AI 提示词模板管理
  promptTemplates: (code?:string) => http.get(`/short-drama/ai/prompt-templates`,{baseURL:'/api/v2',params:code?{code}:{}}).then(r=>r.data as Array<{id:number;code:string;name:string;version:number;system_prompt:string;user_prompt:string;enabled:boolean;created_at:string}>),
  updatePromptTemplate: (id:number,body:Record<string,unknown>) => http.put(`/short-drama/ai/prompt-templates/${id}`,body,{baseURL:'/api/v2'}).then(r=>r.data as {id:number;code:string;name:string;version:number;system_prompt:string;user_prompt:string}),
  // AI 调用日志
  aiRecords: (projectId:number,params?:Record<string,unknown>) => http.get(`/short-drama/projects/${projectId}/ai/records`,{baseURL:'/api/v2',params}).then(r=>r.data as Array<{id:number;operation:string;model:string;status:string;input_tokens:number;output_tokens:number;total_tokens:number;estimated_cost:number;duration_ms:number;error:string|null;request_snapshot:Record<string,unknown>;response_snapshot:Record<string,unknown>;created_at:string;finished_at:string|null}>),
  analyzeNovel: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/ai/analyze`,body,{baseURL:'/api/v2'}).then(r=>r.data as CreativeJob),
  novelAnalyses: (projectId:number) => http.get(`/short-drama/projects/${projectId}/ai/analyses`,{baseURL:'/api/v2'}).then(r=>r.data as NovelAnalysis[]),
  confirmNovelAnalysis: (projectId:number,analysisId:number) => http.post(`/short-drama/projects/${projectId}/ai/analyses/${analysisId}/confirm`,null,{baseURL:'/api/v2'}).then(r=>r.data as NovelAnalysis),
  generateAIAdaptation: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/ai/adaptation`,body,{baseURL:'/api/v2'}).then(r=>r.data as CreativeJob),
  sourceContent: (projectId: number, documentId: number, params?: Record<string, unknown>) => http.get(`/short-drama/projects/${projectId}/documents/${documentId}/content`, { baseURL: '/api/v2', params }).then((r) => r.data as SourceContent),
  createCandidate: (projectId: number, body: Record<string, unknown>) => http.post(`/short-drama/projects/${projectId}/adaptation-candidates`, body, { baseURL: '/api/v2' }).then((r) => r.data as AdaptationCandidate),
  candidates: (projectId: number) => http.get(`/short-drama/projects/${projectId}/adaptation-candidates`, { baseURL: '/api/v2' }).then((r) => r.data as AdaptationCandidate[]),
  confirmCandidate: (projectId: number, candidateId: number, body: Record<string, unknown>) => http.post(`/short-drama/projects/${projectId}/adaptation-candidates/${candidateId}/confirm`, body, { baseURL: '/api/v2' }).then((r) => r.data as StoryVersion),
  screenplay: (projectId: number) => http.get(`/short-drama/projects/${projectId}/screenplay`, { baseURL: '/api/v2' }).then((r) => r.data as Screenplay),
  createEpisode: (projectId: number, body: Record<string, unknown>) => http.post(`/short-drama/projects/${projectId}/episodes`, body, { baseURL: '/api/v2' }).then((r) => r.data as DramaEpisode),
  patchEpisode: (projectId: number, episodeId: number, body: Record<string, unknown>) => http.patch(`/short-drama/projects/${projectId}/episodes/${episodeId}`, body, { baseURL: '/api/v2' }).then((r) => r.data as DramaEpisode),
  generateEpisodeScreenplay: (projectId:number,episodeId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/episodes/${episodeId}/ai/generate`,body,{baseURL:'/api/v2'}).then(r=>r.data as CreativeJob),
  episodeScreenplayCandidates: (projectId:number,episodeId:number) => http.get(`/short-drama/projects/${projectId}/episodes/${episodeId}/ai/candidates`,{baseURL:'/api/v2'}).then(r=>r.data as ScreenplayRevisionCandidate[]),
  confirmEpisodeScreenplayCandidate: (projectId:number,episodeId:number,candidateId:number) => http.post(`/short-drama/projects/${projectId}/episodes/${episodeId}/ai/candidates/${candidateId}/confirm`,null,{baseURL:'/api/v2'}).then(r=>r.data as StoryVersion),
  deleteEpisode: (projectId: number, episodeId: number) => http.delete(`/short-drama/projects/${projectId}/episodes/${episodeId}`, { baseURL: '/api/v2' }),
  createScene: (projectId: number, episodeId: number, body: Record<string, unknown>) => http.post(`/short-drama/projects/${projectId}/episodes/${episodeId}/scenes`, body, { baseURL: '/api/v2' }).then((r) => r.data as DramaScene),
  patchScene: (projectId: number, sceneId: number, body: Record<string, unknown>) => http.patch(`/short-drama/projects/${projectId}/scenes/${sceneId}`, body, { baseURL: '/api/v2' }).then((r) => r.data as DramaScene),
  deleteScene: (projectId: number, sceneId: number) => http.delete(`/short-drama/projects/${projectId}/scenes/${sceneId}`, { baseURL: '/api/v2' }),
  reorderScreenplay: (projectId: number, body: Record<string, unknown>) => http.put(`/short-drama/projects/${projectId}/screenplay/reorder`, body, { baseURL: '/api/v2' }).then((r) => r.data as Screenplay),
  createVersion: (projectId: number, name: string) => http.post(`/short-drama/projects/${projectId}/versions`, { name }, { baseURL: '/api/v2' }).then((r) => r.data as StoryVersion),
  versions: (projectId: number) => http.get(`/short-drama/projects/${projectId}/versions`, { baseURL: '/api/v2' }).then((r) => r.data as { items: StoryVersion[] }),
  version: (projectId: number, versionId: number) => http.get(`/short-drama/projects/${projectId}/versions/${versionId}`, { baseURL: '/api/v2' }).then((r) => r.data as StoryVersion),
  renameVersion: (projectId: number, versionId: number, name: string) => http.patch(`/short-drama/projects/${projectId}/versions/${versionId}`, { name }, { baseURL: '/api/v2' }).then((r) => r.data as StoryVersion),
  restoreVersion: (projectId: number, versionId: number) => http.post(`/short-drama/projects/${projectId}/versions/${versionId}/restore`, null, { baseURL: '/api/v2' }).then((r) => r.data as StoryVersion),
  extractWorld: (projectId: number) => http.post(`/short-drama/projects/${projectId}/world-candidates`, null, { baseURL: '/api/v2' }).then((r) => r.data as WorldCandidate),
  confirmWorld: (projectId: number, candidateId: number, skipExisting = true) => http.post(`/short-drama/projects/${projectId}/world-candidates/${candidateId}/confirm`, { skip_existing: skipExisting }, { baseURL: '/api/v2' }).then((r) => r.data as WorldCandidate),
  world: (projectId: number) => http.get(`/short-drama/projects/${projectId}/world`, { baseURL: '/api/v2' }).then((r) => r.data as WorldOverview),
  createWorldItem: (projectId: number, kind: 'characters'|'locations'|'props'|'relationships', body: Record<string, unknown>) => http.post(`/short-drama/projects/${projectId}/${kind}`, body, { baseURL: '/api/v2' }).then((r) => r.data),
  updateWorldItem: (projectId: number, kind: 'characters'|'locations'|'props'|'relationships', itemId: number, body: Record<string, unknown>) => http.put(`/short-drama/projects/${projectId}/${kind}/${itemId}`, body, { baseURL: '/api/v2' }).then((r) => r.data),
  deleteWorldItem: (projectId: number, kind: 'characters'|'locations'|'props'|'relationships', itemId: number) => http.delete(`/short-drama/projects/${projectId}/${kind}/${itemId}`, { baseURL: '/api/v2' }),
  createCharacterVariant: (projectId: number, characterId: number, body: Record<string, unknown>) => http.post(`/short-drama/projects/${projectId}/characters/${characterId}/variants`, body, { baseURL: '/api/v2' }).then((r) => r.data as CharacterVariant),
  updateCharacterVariant: (projectId: number, characterId: number, variantId: number, body: Record<string, unknown>) => http.put(`/short-drama/projects/${projectId}/characters/${characterId}/variants/${variantId}`, body, { baseURL: '/api/v2' }).then((r) => r.data as CharacterVariant),
  deleteCharacterVariant: (projectId: number, characterId: number, variantId: number) => http.delete(`/short-drama/projects/${projectId}/characters/${characterId}/variants/${variantId}`, { baseURL: '/api/v2' }),
  resourceUsages: (resourceId: number) => http.get(`/short-drama/resources/${resourceId}/usages`, { baseURL: '/api/v2' }).then((r) => r.data as { resource_id: number; usages: Array<Record<string, unknown>> }),
  storyboard: (projectId:number) => http.get(`/short-drama/projects/${projectId}/storyboard`,{baseURL:'/api/v2'}).then(r=>r.data as Storyboard),
  createShotCandidate: (projectId:number,sceneId:number,storyVersionId?:number|null) => http.post(`/short-drama/projects/${projectId}/scenes/${sceneId}/shot-candidates`,{story_version_id:storyVersionId||null},{baseURL:'/api/v2'}).then(r=>r.data as StoryboardCandidate),
  confirmShotCandidate: (projectId:number,candidateId:number,mode:'replace_drafts'|'append') => http.post(`/short-drama/projects/${projectId}/shot-candidates/${candidateId}/confirm`,{mode},{baseURL:'/api/v2'}).then(r=>r.data as StoryboardCandidate),
  createShot: (projectId:number,sceneId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/scenes/${sceneId}/shots`,body,{baseURL:'/api/v2'}).then(r=>r.data as DramaShot),
  updateShot: (projectId:number,shotId:number,body:Record<string,unknown>) => http.put(`/short-drama/projects/${projectId}/shots/${shotId}`,body,{baseURL:'/api/v2'}).then(r=>r.data as DramaShot),
  deleteShot: (projectId:number,shotId:number) => http.delete(`/short-drama/projects/${projectId}/shots/${shotId}`,{baseURL:'/api/v2'}),
  copyShot: (projectId:number,shotId:number) => http.post(`/short-drama/projects/${projectId}/shots/${shotId}/copy`,null,{baseURL:'/api/v2'}).then(r=>r.data as DramaShot),
  splitShot: (projectId:number,shotId:number,splitRatio=.5) => http.post(`/short-drama/projects/${projectId}/shots/${shotId}/split`,{split_ratio:splitRatio},{baseURL:'/api/v2'}).then(r=>r.data as DramaShot[]),
  mergeShots: (projectId:number,shotIds:number[]) => http.post(`/short-drama/projects/${projectId}/shots/merge`,{shot_ids:shotIds},{baseURL:'/api/v2'}).then(r=>r.data as DramaShot),
  reorderShots: (projectId:number,sceneId:number,shotIds:number[]) => http.put(`/short-drama/projects/${projectId}/scenes/${sceneId}/shots/reorder`,{shot_ids:shotIds},{baseURL:'/api/v2'}).then(r=>r.data as DramaShot[]),
  bulkPatchShots: (projectId:number,body:Record<string,unknown>) => http.patch(`/short-drama/projects/${projectId}/shots/bulk`,body,{baseURL:'/api/v2'}).then(r=>r.data as DramaShot[]),
  compileProduction: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/production/compile`,body,{baseURL:'/api/v2'}).then(r=>r.data as CompiledShotTask[]),
  createProductionTasks: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/production/tasks`,body,{baseURL:'/api/v2'}).then(r=>r.data as {batch_id:number|null;created_task_ids:number[];existing_task_ids:number[];links:ShotTaskLink[];submitted:boolean}),
  shotProduction: (projectId:number,shotId:number) => http.get(`/short-drama/projects/${projectId}/shots/${shotId}/production`,{baseURL:'/api/v2'}).then(r=>r.data as ShotProduction),
  reconcileProductionTask: (projectId:number,taskId:number) => http.post(`/short-drama/projects/${projectId}/tasks/${taskId}/reconcile`,null,{baseURL:'/api/v2'}).then(r=>r.data as DramaTake[]),
  selectTake: (projectId:number,takeId:number,selected=true) => http.post(`/short-drama/projects/${projectId}/takes/${takeId}/${selected?'select':'unselect'}`,null,{baseURL:'/api/v2'}).then(r=>r.data as DramaTake),
  reviewTake: (projectId:number,takeId:number,review_note:string) => http.patch(`/short-drama/projects/${projectId}/takes/${takeId}/review`,{review_note},{baseURL:'/api/v2'}).then(r=>r.data as DramaTake),
  deleteTake: (projectId:number,takeId:number) => http.delete(`/short-drama/projects/${projectId}/takes/${takeId}`,{baseURL:'/api/v2'}),
  regenerateTake: (projectId:number,takeId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/takes/${takeId}/regenerate`,body,{baseURL:'/api/v2'}).then(r=>r.data as {task_id:number;link:ShotTaskLink}),
  // ---- V3 导演前期 ----
  directorWorkflow: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/workflow-runs`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorCreateWorkflow: (projectId:number) => http.post(`/short-drama/projects/${projectId}/director/workflow-runs`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorAdvance: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/workflow-runs/advance`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorSetGate: (projectId:number,step:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/workflow-runs/gates/${step}`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorIdentities: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/stable-identities`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorAllocateIdentity: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/stable-identities`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorRetireIdentity: (projectId:number,identityId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/stable-identities/${identityId}/retire`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorSubmitApproval: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/approvals`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApprovals: (projectId:number,params?:Record<string,unknown>) => http.get(`/short-drama/projects/${projectId}/director/approvals`,{baseURL:'/api/v2',params}).then(r=>r.data),
  directorApprove: (projectId:number,approvalId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/approvals/${approvalId}/approve`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorReject: (projectId:number,approvalId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/approvals/${approvalId}/reject`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  // V3 故事台账
  directorGenerateLedger: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/ledgers/generate`,body,{baseURL:'/api/v2'}).then(r=>r.data as CreativeJob),
  directorLedgers: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/ledgers`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorLedgerDetail: (projectId:number,ledgerId:number) => http.get(`/short-drama/projects/${projectId}/director/ledgers/${ledgerId}`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApproveLedger: (projectId:number,ledgerId:number) => http.post(`/short-drama/projects/${projectId}/director/ledgers/${ledgerId}/approve`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorCreateDecision: (projectId:number,ledgerId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/ledgers/${ledgerId}/decisions`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorResolveDecision: (projectId:number,decisionId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/ledger-decisions/${decisionId}/resolve`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  // V3 场景台账
  directorSyncSceneLedgers: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/scene-ledgers/sync`,body,{baseURL:'/api/v2'}).then(r=>r.data as {aligned:number;created:number;retired:number}),
  directorSceneLedgers: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/scene-ledgers`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorSceneLedgerDetail: (projectId:number,stableKey:string) => http.get(`/short-drama/projects/${projectId}/director/scene-ledgers/${stableKey}`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorContinuityFacts: (projectId:number,params?:Record<string,unknown>) => http.get(`/short-drama/projects/${projectId}/director/continuity-facts`,{baseURL:'/api/v2',params}).then(r=>r.data),
  directorAddContinuityFact: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/continuity-facts`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorResolveFact: (projectId:number,factId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/continuity-facts/${factId}/resolve`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorTraceCharacter: (projectId:number,characterKey:string) => http.get(`/short-drama/projects/${projectId}/director/characters/${characterKey}/trace`,{baseURL:'/api/v2'}).then(r=>r.data),
  // V3 风格圣经
  directorStyleBibles: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/style-bibles`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorCreateStyleBible: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/style-bibles`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorDeriveStyleBible: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/style-bibles/derive`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApproveStyleBible: (projectId:number,styleId:number) => http.post(`/short-drama/projects/${projectId}/director/style-bibles/${styleId}/approve`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorCheckpointB: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/checkpoint-b`,{baseURL:'/api/v2'}).then(r=>r.data as {passed:boolean;reason?:string;style_id?:number;palette_id?:number}),
  // V3 锚点
  directorCharacterAnchors: (projectId:number,params?:Record<string,unknown>) => http.get(`/short-drama/projects/${projectId}/director/character-anchors`,{baseURL:'/api/v2',params}).then(r=>r.data),
  directorCreateCharAnchor: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/character-anchors`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApproveCharAnchor: (projectId:number,anchorId:number) => http.post(`/short-drama/projects/${projectId}/director/character-anchors/${anchorId}/approve`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorPropAnchors: (projectId:number,params?:Record<string,unknown>) => http.get(`/short-drama/projects/${projectId}/director/prop-anchors`,{baseURL:'/api/v2',params}).then(r=>r.data),
  directorCreatePropAnchor: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/prop-anchors`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApprovePropAnchor: (projectId:number,anchorId:number) => http.post(`/short-drama/projects/${projectId}/director/prop-anchors/${anchorId}/approve`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorCheckpointC: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/checkpoint-c`,{baseURL:'/api/v2'}).then(r=>r.data as {passed:boolean;reason:string;character_total:number;character_approved:number;character_pending:number;prop_total:number;prop_approved:number;prop_pending:number}),
  // V3 空间资产
  directorSpatialPlans: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/spatial-plans`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorCreateSpatialPlan: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/spatial-plans`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApproveSpatialPlan: (projectId:number,planId:number) => http.post(`/short-drama/projects/${projectId}/director/spatial-plans/${planId}/approve`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorLocationViews: (projectId:number,planId:number) => http.get(`/short-drama/projects/${projectId}/director/spatial-plans/${planId}/views`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorCreateLocationView: (projectId:number,planId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/spatial-plans/${planId}/views`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApproveLocationView: (projectId:number,viewId:number) => http.post(`/short-drama/projects/${projectId}/director/location-views/${viewId}/approve`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  // V3 依赖图
  directorBuildDependencyGraph: (projectId:number) => http.post(`/short-drama/projects/${projectId}/director/dependency-graph/build`,null,{baseURL:'/api/v2'}).then(r=>r.data as {ok:boolean;edges:number}),
  directorDependencies: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/dependencies`,{baseURL:'/api/v2'}).then(r=>r.data as Array<{id:number;downstream_type:string;downstream_ref:string;upstream_type:string;upstream_ref:string;dependency_type:string}>),
  // V3 Stale 记录
  directorStaleRecords: (projectId:number,status?:string) => http.get(`/short-drama/projects/${projectId}/director/stale-records`,{baseURL:'/api/v2',params:{status}}).then(r=>r.data as Array<{id:number;asset_type:string;asset_ref:string;stale_reason:string;detail:string;status:string;resolution:string}>),
  directorResolveStale: (projectId:number,staleId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/stale-records/${staleId}/resolve`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  // V3 Manifest
  directorBuildManifest: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/manifests`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorManifests: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/manifests`,{baseURL:'/api/v2'}).then(r=>r.data as Array<Record<string,unknown>>),
  directorManifestDetail: (projectId:number,manifestId:number) => http.get(`/short-drama/projects/${projectId}/director/manifests/${manifestId}`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApproveManifest: (projectId:number,manifestId:number) => http.post(`/short-drama/projects/${projectId}/director/manifests/${manifestId}/approve`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  // V3 审计
  directorCreateAuditRun: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/audit-runs`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  directorAuditRuns: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/audit-runs`,{baseURL:'/api/v2'}).then(r=>r.data as Array<Record<string,unknown>>),
  directorAuditRunDetail: (projectId:number,runId:number) => http.get(`/short-drama/projects/${projectId}/director/audit-runs/${runId}`,{baseURL:'/api/v2'}).then(r=>r.data),
  directorRunRuleAudit: (projectId:number,runId:number) => http.post(`/short-drama/projects/${projectId}/director/audit-runs/${runId}/run-rules`,null,{baseURL:'/api/v2'}).then(r=>r.data as {ok:boolean;rule_issues:number}),
  directorRunLLMAudit: (projectId:number,runId:number) => http.post(`/short-drama/projects/${projectId}/director/audit-runs/${runId}/run-llm`,null,{baseURL:'/api/v2'}).then(r=>r.data as {ok:boolean;llm_issues:number}),
  directorFinishAudit: (projectId:number,runId:number) => http.post(`/short-drama/projects/${projectId}/director/audit-runs/${runId}/finish`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorWaiveIssue: (projectId:number,issueId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/audit-issues/${issueId}/waive`,body,{baseURL:'/api/v2'}).then(r=>r.data),
  // V3 检测缺口
  directorDetectedGaps: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/detected-gaps`,{baseURL:'/api/v2'}).then(r=>r.data as Array<Record<string,unknown>>),
  // V3 Manifest 编译（第 8 轮）
  directorCompileManifestPreview: (projectId:number,manifestId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/manifests/${manifestId}/compile-preview`,body,{baseURL:'/api/v2'}).then(r=>r.data as {manifest_id:number;manifest_version:number;intents:Array<Record<string,unknown>>;total:number;error_count:number;ok_count:number}),
  directorCreateTasksFromManifest: (projectId:number,manifestId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/manifests/${manifestId}/create-tasks`,body,{baseURL:'/api/v2'}).then(r=>r.data as {manifest_id:number;batch_id:number|null;created:number;reused:number;submitted:boolean}),
  directorManifestTaskLinks: (projectId:number,manifestId:number) => http.get(`/short-drama/projects/${projectId}/director/manifests/${manifestId}/task-links`,{baseURL:'/api/v2'}).then(r=>r.data as Array<{id:number;manifest_item_id:number;asset_stable_key:string|null;task_id:number;task_status:string|null;task_error:string|null;output_resource_id:number|null;take_id:number|null;link_status:string;sync_error:string}>),
  directorRefreshManifestStatus: (projectId:number,manifestId:number) => http.post(`/short-drama/projects/${projectId}/director/manifests/${manifestId}/refresh-status`,null,{baseURL:'/api/v2'}).then(r=>r.data as {manifest_id:number;changed_items:number;summary:Record<string,unknown>}),
  // V3 导演对话/建议/提案（第 9 轮）
  directorContextSnapshot: (projectId:number,purpose:string) => http.get(`/short-drama/projects/${projectId}/director/context-snapshot`,{baseURL:'/api/v2',params:{purpose}}).then(r=>r.data),
  directorGuidance: (projectId:number) => http.post(`/short-drama/projects/${projectId}/director/guidance`,null,{baseURL:'/api/v2'}).then(r=>r.data as {suggestions:Array<{kind:string;title:string;detail:string;severity:string}>;revision_hash:string}),
  directorConversations: (projectId:number) => http.get(`/short-drama/projects/${projectId}/director/conversations`,{baseURL:'/api/v2'}).then(r=>r.data as Array<{id:number;title:string;status:string}>),
  directorCreateConversation: (projectId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/conversations`,body,{baseURL:'/api/v2'}).then(r=>r.data as {id:number;title:string}),
  directorConversationDetail: (projectId:number,conversationId:number) => http.get(`/short-drama/projects/${projectId}/director/conversations/${conversationId}`,{baseURL:'/api/v2'}).then(r=>r.data as {id:number;title:string;messages:Array<{id:number;role:string;content:string;revision_hash:string;created_at:string}>}),
  directorSendChat: (projectId:number,conversationId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/conversations/${conversationId}/messages`,body,{baseURL:'/api/v2'}).then(r=>r.data as {id:number;role:string;content:string;revision_hash:string}),
  directorProposals: (projectId:number,statusFilter?:string) => http.get(`/short-drama/projects/${projectId}/director/action-proposals`,{baseURL:'/api/v2',params:statusFilter?{status_filter:statusFilter}:{}}).then(r=>r.data as Array<{id:number;action_type:string;action_desc:string;target_type:string;target_ref:string;revision_current:boolean;title:string;rationale:string;changes:Array<{field:string;before:string;after:string}>;impact_refs:string[];status:string;apply_error:string;dismissed_reason:string}>),
  directorGenerateProposals: (projectId:number) => http.post(`/short-drama/projects/${projectId}/director/action-proposals/generate`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorApplyProposal: (projectId:number,proposalId:number) => http.post(`/short-drama/projects/${projectId}/director/action-proposals/${proposalId}/apply`,null,{baseURL:'/api/v2'}).then(r=>r.data),
  directorDismissProposal: (projectId:number,proposalId:number,body:Record<string,unknown>) => http.post(`/short-drama/projects/${projectId}/director/action-proposals/${proposalId}/dismiss`,body,{baseURL:'/api/v2'}).then(r=>r.data),
}

export const imageProviderApi = {
  list: () => http.get('/image-providers', { baseURL: '/api/v2' }).then(r => r.data as ImageProvider[]),
  create: (body:Record<string,unknown>) => http.post('/image-providers',body,{baseURL:'/api/v2'}).then(r=>r.data as ImageProvider),
  update: (id:number,body:Record<string,unknown>) => http.put(`/image-providers/${id}`,body,{baseURL:'/api/v2'}).then(r=>r.data as ImageProvider),
  remove: (id:number) => http.delete(`/image-providers/${id}`,{baseURL:'/api/v2'}).then(r=>r.data),
  test: (id:number) => http.post(`/image-providers/${id}/test`,null,{baseURL:'/api/v2'}).then(r=>r.data as {ok:boolean;model:string;model_available:boolean;latency_ms:number}),
}

export const nodeApi = {
  list: () => http.get('/nodes').then((r) => r.data),
  create: (body: any) => http.post('/nodes', body).then((r) => r.data),
  probe: (id: number) => http.post(`/nodes/${id}/probe`).then((r) => r.data),
}

export const runtimeApi = {
  dispatcher: () => http.get('/runtime/dispatcher').then((r) => r.data),
  release: (taskId: number) => http.post(`/runtime/tasks/${taskId}/release`).then((r) => r.data),
  resubmit: (taskId: number) => http.post(`/runtime/tasks/${taskId}/resubmit`).then((r) => r.data),
}

export const workflowApi = {
  list: (params?: any) =>
    http.get('/workflows', { params }).then((r) => r.data),
  create: (body: any) => http.post('/workflows', body).then((r) => r.data),
  update: (id: number, body: any) => http.patch(`/workflows/${id}`, body).then((r) => r.data),
  addVersion: (id: number, body: any) =>
    http.post(`/workflows/${id}/versions`, body).then((r) => r.data),
  getVersionDetail: (workflowId: number, versionId: number) =>
    http.get(`/workflows/${workflowId}/versions/${versionId}/detail`).then((r) => r.data),
  updateVersion: (workflowId: number, versionId: number, body: any) =>
    http.patch(`/workflows/${workflowId}/versions/${versionId}`, body).then((r) => r.data),
  parse: (api_json: any, generation_type_code?: string, parameters?: any[]) =>
    http.post('/workflows/parse', { api_json, generation_type_code, parameters }).then((r) => r.data),
  test: (workflowId: number, versionId: number, body: any) =>
    http.post(`/workflows/${workflowId}/versions/${versionId}/test`, body).then((r) => r.data),
  remove: (id: number) => http.delete(`/workflows/${id}`),
}

export const genTypeApi = {
  list: (params?: any) => http.get('/generation-types', { params }).then((r) => r.data),
  menu: () => http.get('/generation-types/menu').then((r) => r.data),
  patch: (id: number, body: any) => http.patch(`/generation-types/${id}`, body).then((r) => r.data),
  setDefault: (id: number, workflow_version_id: number) =>
    http.patch(`/generation-types/${id}/default-workflow`, { workflow_version_id }).then((r) => r.data),
  motionTransferSchemes: () => http.get('/generation-types/motion-transfer/parameter-schemes').then((r) => r.data),
  saveMotionTransferSchemes: (schemes: any[]) =>
    http.put('/generation-types/motion-transfer/parameter-schemes', { schemes }).then((r) => r.data),
}

export const generationTypeConfigApi = {
  active: (typeId: number) => http.get(`/generation-types/${typeId}/config`, { baseURL: '/api/v2' }).then((r) => r.data),
  draft: (typeId: number) => http.get(`/generation-types/${typeId}/config/draft`, { baseURL: '/api/v2' }).then((r) => r.data),
  saveDraft: (typeId: number, config: Record<string, unknown>) =>
    http.put(`/generation-types/${typeId}/config/draft`, { config }, { baseURL: '/api/v2' }).then((r) => r.data),
  validate: (typeId: number, config: Record<string, unknown>) =>
    http.post(`/generation-types/${typeId}/config/validate`, { config }, { baseURL: '/api/v2' }).then((r) => r.data),
  publish: (typeId: number) => http.post(`/generation-types/${typeId}/config/publish`, null, { baseURL: '/api/v2' }).then((r) => r.data),
  versions: (typeId: number) => http.get(`/generation-types/${typeId}/config/versions`, { baseURL: '/api/v2' }).then((r) => r.data),
  diff: (typeId: number, fromVersionId: number, toVersionId: number) =>
    http.get(`/generation-types/${typeId}/config/diff`, { baseURL: '/api/v2', params: { from_version_id: fromVersionId, to_version_id: toVersionId } }).then((r) => r.data),
  rollback: (typeId: number, sourceVersionId: number) =>
    http.post(`/generation-types/${typeId}/config/rollback`, { source_version_id: sourceVersionId }, { baseURL: '/api/v2' }).then((r) => r.data),
  deactivate: (typeId: number) => http.post(`/generation-types/${typeId}/config/deactivate`, null, { baseURL: '/api/v2' }).then((r) => r.data),
  remove: (typeId: number) => http.delete(`/generation-types/${typeId}`, { baseURL: '/api/v2' }),
}

export const batchApi = {
  create: (body: any) => http.post('/batches', body).then((r) => r.data),
  list: (params?: any) => http.get('/batches', { params }).then((r) => r.data),
  get: (id: number) => http.get(`/batches/${id}`).then((r) => r.data),
  rows: (id: number) => http.get(`/batches/${id}/rows`).then((r) => r.data),
  status: (id: number) => http.get(`/batches/${id}/status`).then((r) => r.data),
  submit: (id: number) => http.post(`/batches/${id}/submit`).then((r) => r.data),
  cancel: (id: number) => http.post(`/batches/${id}/cancel`).then((r) => r.data),
  retryFailed: (id: number) => http.post(`/batches/${id}/retry-failed`).then((r) => r.data),
  importCsv: (id: number, file: File, params: any) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post(`/batches/${id}/import`, fd, { params }).then((r) => r.data)
  },
  saveTemplate: (id: number) => http.post(`/batches/${id}/save-template`).then((r) => r.data),
}

export const taskApi = {
  list: (params?: any) => http.get('/tasks', { params: { limit: 200, ...params } }).then((r) => r.data),
  count: (params?: any) => http.get('/tasks/count', { params }).then((r) => r.data as { total: number }),
  outputSummaries: (taskIds: number[]) => http.get('/tasks/output-summaries', { params: { task_ids: taskIds.join(',') } }).then((r) => r.data),
  get: (id: number) => http.get(`/tasks/${id}`).then((r) => r.data),
  events: (id: number) => http.get(`/tasks/${id}/events`).then((r) => r.data),
  cancel: (id: number) => http.post(`/tasks/${id}/cancel`).then((r) => r.data),
  retry: (id: number) => http.post(`/tasks/${id}/retry`).then((r) => r.data),
  regenerate: (id: number) => http.post(`/tasks/${id}/regenerate`).then((r) => r.data),
  execute: (id: number, params: Record<string, unknown>) => http.post(`/tasks/${id}/execute`, { params }).then((r) => r.data),
  delete: (id: number) => http.delete(`/tasks/${id}`),
  bulk: (task_ids: number[], action: 'delete' | 'cancel' | 'retry' | 'regenerate') =>
    http.post('/tasks/bulk/action', { task_ids, action }).then((r) => r.data),
  outputs: (id: number) => http.get(`/tasks/${id}/outputs`).then((r) => r.data),
  recheck: (id: number) => http.post(`/tasks/${id}/recheck`).then((r) => r.data),
}

export const resourceApi = {
  list: (params?: any) => http.get('/resources', { params }).then((r) => r.data),
  upload: (file: File, media_type = 'image', direction = 'input') => {
    const fd = new FormData()
    fd.append('file', file)
    return http
      .post('/resources', fd, {
        params: { media_type, direction },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },
  thumbUrl: (id: number) => `/api/v1/resources/${id}/thumb`,
  fileUrl: (id: number) => `/api/v1/resources/${id}/file`,
  generationInfo: (id: number) => http.get(`/resources/${id}/generation-info`).then((r) => r.data),
  get: (id: number) => http.get(`/resources/${id}`).then((r) => r.data),
  recycle: () => http.get('/resources/recycle/list').then((r) => r.data),
  restore: (id: number) => http.post(`/resources/${id}/restore`).then((r) => r.data),
  extractFrames: (id: number, params: { timestamps?: string; interval?: number }) =>
    http.post(`/resources/${id}/frames`, null, { params }).then((r) => r.data),
  delete: (id: number) => http.delete(`/resources/${id}`),
  move: (id: number, folder_id: number | null) => http.post(`/resources/${id}/move`, { folder_id }).then((r) => r.data),
  batchMove: (resource_ids: number[], folder_id: number | null) =>
    http.post('/resources/batch-move', { resource_ids, folder_id }).then((r) => r.data),
  batchDelete: (resource_ids: number[]) =>
    http.post('/resources/batch-delete', { resource_ids }).then((r) => r.data),
  batchPurge: (resource_ids: number[]) =>
    http.post('/resources/batch-purge', { resource_ids }).then((r) => r.data),
  trimVideo: (id: number, start: number, end: number) =>
    http.post(`/resources/${id}/trim`, { start, end }).then((r) => r.data),
  mergeVideos: (resource_ids: number[]) =>
    http.post('/resources/merge', { resource_ids }).then((r) => r.data),
}

export const resourceFolderApi = {
  tree: () => http.get('/resource-folders/tree').then((r) => r.data),
  create: (body: any) => http.post('/resource-folders', body).then((r) => r.data),
  patch: (id: number, body: any) => http.patch(`/resource-folders/${id}`, body).then((r) => r.data),
  delete: (id: number) => http.delete(`/resource-folders/${id}`).then((r) => r.data),
}

export const promptApi = {
  listCategories: () => http.get('/prompt-categories').then((r) => r.data),
  createCategory: (name: string) => http.post('/prompt-categories', { name }).then((r) => r.data),
  list: (params?: any) => http.get('/prompts', { params }).then((r) => r.data),
  create: (body: any) => http.post('/prompts', body).then((r) => r.data),
  patch: (id: number, body: any) => http.patch(`/prompts/${id}`, body).then((r) => r.data),
  remove: (id: number) => http.delete(`/prompts/${id}`),
}

export const settingsApi = {
  list: () => http.get('/settings').then((r) => r.data),
  patch: (body: any) => http.patch('/settings', body).then((r) => r.data),
  getSelectOptions: () => http.get('/settings/select-options').then((r) => r.data),
  createSelectOptionProject: (label: string, value_type: 'string' | 'number') =>
    http.post('/settings/select-options', { label, value_type }).then((r) => r.data),
  saveSelectOptions: (key: string, options: any[], default_value: any) =>
    http.put(`/settings/select-options/${key}`, { options, default_value }).then((r) => r.data),
  deleteSelectOptionProject: (key: string) => http.delete(`/settings/select-options/${key}`),
}

export const userApi = {
  list: () => http.get('/users').then((r) => r.data),
  create: (body: any) => http.post('/users', body).then((r) => r.data),
  patch: (id: number, body: any) => http.patch(`/users/${id}`, body).then((r) => r.data),
}

export const auditApi = {
  list: (params?: any) => http.get('/audit-logs', { params: { limit: 200, ...params } }).then((r) => r.data),
}
