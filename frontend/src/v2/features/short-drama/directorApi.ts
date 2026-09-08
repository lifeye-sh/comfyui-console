import { http } from '@/api/client'
import type { RuntimeWorkflow } from '../generation-config/model'
export type DirectorWorkflow = RuntimeWorkflow & {generation_type_id:number;generation_type_name:string;media_type:'image'|'video';mapping:Record<string,string>;modes:string[]}
export type FrameDraft={id:string;kind:'start'|'key'|'end';time:number;prompt:string;workflow_version_id:number|null;params:Record<string,any>;generation_service:'comfyui'|'gemini_image';gemini_provider_id:number|null;gemini_params:Record<string,any>;enabled?:boolean;order?:number}
export type CharacterAssetChoice={character_id:number;image_mode:'primary'|'turnaround';enabled?:boolean;order?:number}
export type ExtraResourceItem={resource_id:number;media_type:'image'|'audio'|'video';label:string;enabled?:boolean;order?:number;filename?:string}
export type AssetChoices={extras:ExtraResourceItem[];characters:CharacterAssetChoice[];location_enabled?:boolean;location_order?:number;prop_orders?:Record<string,number>}
export type DirectorDraft={frames:FrameDraft[];prompt_inputs:Record<string,string>;prompt_input_overrides:string[];prompt_asset_descriptions:Record<string,string>;video_prompt:string;video_workflow_version_id:number|null;video_mode:string;video_params:Record<string,any>;asset_choices:AssetChoices}
export type DirectorTake={id:number;scope:string;take_no:number;is_selected:boolean;stale:boolean;resource_id:number;review_note:string;resource:any;generation_snapshot:any}
export type DirectorAsset={role:string;name:string;entity_id:number;variant_id:number|null;resource_id:number|null;image_mode?:string;enabled?:boolean;check_order?:number;description:string}
export type DirectorExtra={resource_id:number;media_type:'image'|'audio'|'video';label:string;enabled:boolean;order:number;check_order?:number;filename?:string}
export type DirectorShot={id:number;episode_id:number;scene_id:number;scene:string;shot_no:number;title:string;aspect_ratio:string;description:string;action:string;dialogue:string;duration:number;camera:string;revision:number;draft:DirectorDraft;character_ids:number[];location_id:number|null;prop_ids:number[];extras:DirectorExtra[];check_orders:Record<string,number>;assets:DirectorAsset[];takes:DirectorTake[];tasks:Array<{id:number;status:string;scope:string;error:string|null;sync_status:string;sync_error:string|null;workflow_version_id:number|null;generation_service:'comfyui'|'gemini_image';provider_config_id:number|null;mode:string;params:Record<string,any>}>;selected_frames:Record<string,number>}
const base=(project:number)=>`/short-drama/projects/${project}/director-workspace`
const options={baseURL:'/api/v2'}
export const directorApi={
  overview:(p:number,e:number)=>http.get(`${base(p)}/episodes/${e}`,options).then(r=>r.data as {shots:DirectorShot[]}),
  shot:(p:number,s:number)=>http.get(`${base(p)}/shots/${s}`,options).then(r=>r.data as DirectorShot),
  workflows:(p:number)=>http.get(`${base(p)}/workflows`,options).then(r=>r.data as DirectorWorkflow[]),
  bind:(p:number,w:number,mapping:Record<string,string>)=>http.put(`${base(p)}/workflows/${w}/binding`,{mapping},options),
  save:(p:number,s:number,revision:number,draft:DirectorDraft)=>http.put(`${base(p)}/shots/${s}`,{revision,draft},options).then(r=>r.data as DirectorShot),
  updateRefs:(p:number,s:number,body:{character_ids:number[];bindings:Record<string,number|null>;location_id:number|null;prop_ids:number[]})=>http.put(`${base(p)}/shots/${s}/refs`,body,options).then(r=>r.data as DirectorShot),
  compile:(p:number,s:number,body:any)=>http.post(`${base(p)}/shots/${s}/compile`,body,options).then(r=>r.data),
  generate:(p:number,s:number,body:any)=>http.post(`${base(p)}/shots/${s}/generate`,body,options).then(r=>r.data),
  importFrame:(p:number,s:number,scope:string,resource_id:number)=>http.post(`${base(p)}/shots/${s}/frames/import`,{scope,resource_id},options).then(r=>r.data as DirectorShot),
  videoPrompt:(p:number,s:number)=>http.post(`${base(p)}/shots/${s}/video-prompt`,null,options).then(r=>r.data as {prompt:string}),
  adopt:(p:number,t:number)=>http.post(`${base(p)}/takes/${t}/adopt`,{},options),
}
