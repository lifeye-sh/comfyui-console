let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let currentToken: string | null = null
const subscribedProjects = new Set<number>()

const handlers = new Set<(e: any) => void>()

export function onWsEvent(handler: (e: any) => void) {
  handlers.add(handler)
  return () => handlers.delete(handler)
}

/** 请求浏览器通知权限 */
export function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}

/** 任务完成时弹出浏览器通知 */
function notifyTaskComplete(taskId: number, type: string) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  if (type === 'completed') {
    new Notification('任务完成', { body: `任务 #${taskId} 已成功完成`, icon: '/favicon.ico' })
  } else if (type === 'failed') {
    new Notification('任务失败', { body: `任务 #${taskId} 执行失败`, icon: '/favicon.ico' })
  }
}

function sendRaw(msg: Record<string, unknown>) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg))
  }
}

/** 订阅项目导演频道（服务端校验归属，越权订阅会被拒绝） */
export function subscribeDirector(projectId: number) {
  subscribedProjects.add(projectId)
  sendRaw({ type: 'subscribe', project_id: projectId })
}

export function unsubscribeDirector(projectId: number) {
  subscribedProjects.delete(projectId)
  sendRaw({ type: 'unsubscribe', project_id: projectId })
}

export function connectWs() {
  const token = localStorage.getItem('cc_access_token')
  if (!token || ws) {
    currentToken = token
    return
  }
  currentToken = token

  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${protocol}://${location.host}/ws/events?token=${encodeURIComponent(token)}`)

  ws.onopen = () => {
    // 重连后恢复项目订阅
    for (const projectId of subscribedProjects) {
      sendRaw({ type: 'subscribe', project_id: projectId })
    }
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      handlers.forEach((h) => h(data))
      // 任务完成/失败时弹出通知
      if (data.task_id && (data.type === 'task.completed' || data.type === 'task.failed')) {
        notifyTaskComplete(data.task_id, data.type.replace('task.', ''))
      }
    } catch {
      /* ignore */
    }
  }

  ws.onclose = () => {
    ws = null
    if (reconnectTimer) return
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      connectWs()
    }, 3000)
  }
}

export function disconnectWs() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  subscribedProjects.clear()
  ws?.close()
  ws = null
}
