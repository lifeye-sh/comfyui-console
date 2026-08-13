export type ResourceItem={id:number;owner_id:number|null;folder_id:number|null;media_type:'image'|'video'|'audio';direction:string;filename:string;mime:string;size:number;width:number|null;height:number|null;duration:number|null;created_at:string}
export type FolderNode={id:number;parent_id:number|null;name:string;folder_type:string;system_key:string|null;resource_count:number;media_types:string[];children:FolderNode[]}
export type FlatFolder=FolderNode&{depth:number}
export function flattenFolders(tree:FolderNode[]):FlatFolder[]{const out:FlatFolder[]=[];const visit=(nodes:FolderNode[],depth=0)=>nodes.forEach(n=>{out.push({...n,depth});visit(n.children||[],depth+1)});visit(tree);return out}
export function localDateKey(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
export function formatSize(bytes:number){if(bytes<1024)return `${bytes} B`;if(bytes<1024**2)return `${(bytes/1024).toFixed(1)} KB`;return `${(bytes/1024**2).toFixed(1)} MB`}
export function formatDuration(seconds:number|null){if(seconds==null)return '—';const m=Math.floor(seconds/60);const s=Math.round(seconds%60);return `${m}:${String(s).padStart(2,'0')}`}
export function mediaLabel(type:string){return type==='image'?'图片':type==='video'?'视频':'音频'}
