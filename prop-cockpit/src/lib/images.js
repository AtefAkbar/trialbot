// Screenshot helpers: turn a File or pasted clipboard image into a compressed
// JPEG data URL so a chart screenshot costs ~100-300KB instead of several MB.

const MAX_W = 1600
const QUALITY = 0.82

export async function fileToScreenshot(file) {
  const rawUrl = await readAsDataUrl(file)
  let dataUrl = rawUrl
  try {
    dataUrl = await compress(rawUrl, MAX_W, QUALITY)
  } catch {
    // keep the uncompressed one if canvas fails
  }
  return {
    id: 's_' + Math.random().toString(36).slice(2) + (file.lastModified || file.size || ''),
    name: file.name || 'pasted.png',
    dataUrl,
  }
}

// Pull image files out of a clipboard paste event.
export async function screenshotsFromPaste(e) {
  const items = e.clipboardData?.items || []
  const files = []
  for (const it of items) {
    if (it.kind === 'file' && it.type.startsWith('image/')) {
      const f = it.getAsFile()
      if (f) files.push(f)
    }
  }
  return Promise.all(files.map(fileToScreenshot))
}

export async function screenshotsFromFiles(fileList) {
  const files = [...fileList].filter((f) => f.type.startsWith('image/'))
  return Promise.all(files.map(fileToScreenshot))
}

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(fr.result)
    fr.onerror = () => reject(fr.error)
    fr.readAsDataURL(file)
  })
}

function compress(dataUrl, maxW, quality) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, maxW / img.width)
      const w = Math.round(img.width * scale)
      const h = Math.round(img.height * scale)
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, 0, 0, w, h)
      resolve(canvas.toDataURL('image/jpeg', quality))
    }
    img.onerror = reject
    img.src = dataUrl
  })
}
