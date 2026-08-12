/** 前端图片压缩工具：超过阈值时按比例压缩，返回 Blob。 */

export async function compressImage(
  file: File,
  maxSize = 5 * 1024 * 1024,
  maxDim = 2048,
  quality = 0.85,
): Promise<Blob> {
  // 非图片或小文件直接返回
  if (!file.type.startsWith('image/') || file.size <= maxSize) {
    return file
  }

  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)

      let { width, height } = img
      if (width > maxDim || height > maxDim) {
        const ratio = Math.min(maxDim / width, maxDim / height)
        width = Math.round(width * ratio)
        height = Math.round(height * ratio)
      }

      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0, width, height)

      canvas.toBlob(
        (blob) => {
          if (blob) resolve(blob)
          else reject(new Error('压缩失败'))
        },
        'image/jpeg',
        quality,
      )
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('图片加载失败'))
    }
    img.src = url
  })
}

/** 分片上传大文件（简单实现：分块 PUT，后端暂用单次接收，预留扩展）。 */
export async function uploadChunked(
  url: string,
  file: File | Blob,
  chunkSize = 2 * 1024 * 1024,
  headers: Record<string, string> = {},
): Promise<void> {
  // 当前后端不支持分片合并，此处仅做前端分块读取模拟。
  // 后续可扩展为：分块上传 → 合并接口。
  const total = Math.ceil(file.size / chunkSize)
  for (let i = 0; i < total; i++) {
    const start = i * chunkSize
    const end = Math.min(start + chunkSize, file.size)
    const _chunk = file.slice(start, end)
    // 预留：实际分片上传接口
    // await fetch(`${url}?chunk=${i}&total=${total}`, { method: 'PUT', body: chunk, headers })
  }
}