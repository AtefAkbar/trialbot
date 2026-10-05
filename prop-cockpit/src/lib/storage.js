// localStorage-backed persistence.
//
// This replaces the claude.ai-artifact-only `window.storage` API with the
// standard browser localStorage. Same shape as before (get / set with a key),
// but namespaced and JSON-safe, and it degrades gracefully if localStorage is
// unavailable (private mode, quota, SSR) by falling back to an in-memory map.

const NS = 'propCockpit:'

const memoryFallback = new Map()

function hasLocalStorage() {
  try {
    const k = NS + '__probe__'
    window.localStorage.setItem(k, '1')
    window.localStorage.removeItem(k)
    return true
  } catch {
    return false
  }
}

const useLS = typeof window !== 'undefined' && hasLocalStorage()

export function load(key, fallback) {
  try {
    const raw = useLS
      ? window.localStorage.getItem(NS + key)
      : memoryFallback.get(key)
    if (raw == null) return fallback
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function save(key, value) {
  const raw = JSON.stringify(value)
  try {
    if (useLS) window.localStorage.setItem(NS + key, raw)
    else memoryFallback.set(key, raw)
  } catch {
    // Quota or serialization error — keep at least the in-memory copy.
    memoryFallback.set(key, raw)
  }
}

export function remove(key) {
  try {
    if (useLS) window.localStorage.removeItem(NS + key)
    else memoryFallback.delete(key)
  } catch {
    memoryFallback.delete(key)
  }
}

// Storage keys used across the app.
export const KEYS = {
  settings: 'settings',
  trades: 'trades',
}
