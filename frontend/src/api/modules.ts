import { http } from './client'

export const authApi = {
  login: (username: string, password: string) =>
    http.post('/auth/login', { username, password }).then((r) => r.data),
  me: () => http.get('/auth/me').then((r) => r.data),
}

export const dashboardApi = {
  summary: () => http.get('/dashboard/summary').then((r) => r.data),
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
  saveSelectOptions: (key: string, options: any[], default_value: any) =>
    http.put(`/settings/select-options/${key}`, { options, default_value }).then((r) => r.data),
}

export const userApi = {
  list: () => http.get('/users').then((r) => r.data),
  create: (body: any) => http.post('/users', body).then((r) => r.data),
  patch: (id: number, body: any) => http.patch(`/users/${id}`, body).then((r) => r.data),
}

export const auditApi = {
  list: (params?: any) => http.get('/audit-logs', { params: { limit: 200, ...params } }).then((r) => r.data),
}
