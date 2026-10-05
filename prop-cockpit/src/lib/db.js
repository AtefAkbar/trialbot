// IndexedDB store for journal data — trades, playbooks, and daily notebook
// entries. Trades carry screenshots (data URLs) which would blow past
// localStorage's ~5MB cap fast; IndexedDB handles tens of MB comfortably.
// Falls back to localStorage per-store if IndexedDB is unavailable.

import { load, save } from './storage.js'

const DB_NAME = 'propCockpit'
const VERSION = 2

// store name -> keyPath
const STORES = {
  trades: 'id',
  playbooks: 'id',
  notebook: 'day',
}

const hasIDB = typeof indexedDB !== 'undefined'

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      for (const [name, keyPath] of Object.entries(STORES)) {
        if (!db.objectStoreNames.contains(name)) {
          db.createObjectStore(name, { keyPath })
        }
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function txStore(store, mode, fn) {
  return openDB().then(
    (db) =>
      new Promise((resolve, reject) => {
        const t = db.transaction(store, mode)
        const os = t.objectStore(store)
        let result
        Promise.resolve(fn(os)).then((r) => (result = r))
        t.oncomplete = () => resolve(result)
        t.onerror = () => reject(t.error)
        t.onabort = () => reject(t.error)
      }),
  )
}

function reqPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

// localStorage fallback key per store.
const lsKey = (store) => store

// --- Generic store API ---
export async function getAll(store) {
  if (!hasIDB) return load(lsKey(store), [])
  try {
    return await txStore(store, 'readonly', (os) => reqPromise(os.getAll()))
  } catch {
    return load(lsKey(store), [])
  }
}

export async function put(store, rec) {
  if (!hasIDB) return saveAllLS(store, (list) => upsert(list, rec, STORES[store]))
  try {
    await txStore(store, 'readwrite', (os) => os.put(rec))
  } catch {
    saveAllLS(store, (list) => upsert(list, rec, STORES[store]))
  }
}

export async function del(store, key) {
  const kp = STORES[store]
  if (!hasIDB) return saveAllLS(store, (list) => list.filter((r) => r[kp] !== key))
  try {
    await txStore(store, 'readwrite', (os) => os.delete(key))
  } catch {
    saveAllLS(store, (list) => list.filter((r) => r[kp] !== key))
  }
}

export async function clear(store) {
  if (!hasIDB) return save(lsKey(store), [])
  try {
    await txStore(store, 'readwrite', (os) => os.clear())
  } catch {
    save(lsKey(store), [])
  }
}

export async function bulkPut(store, recs) {
  if (!hasIDB) return save(lsKey(store), recs)
  try {
    await txStore(store, 'readwrite', (os) => {
      for (const r of recs) os.put(r)
    })
  } catch {
    save(lsKey(store), recs)
  }
}

// --- Trade-specific wrappers (back-compat with existing callers) ---
export const allTrades = () => getAll('trades')
export const putTrade = (t) => put('trades', t)
export const deleteTrade = (id) => del('trades', id)
export const clearTrades = () => clear('trades')

// One-time migration: if IndexedDB trades are empty but legacy localStorage
// trades exist, import them. Returns the resulting trade list.
export async function loadWithMigration() {
  const idbTrades = await allTrades()
  if (idbTrades.length) return idbTrades
  const legacy = load('trades', [])
  if (hasIDB && legacy.length) await bulkPut('trades', legacy)
  return legacy
}

// --- localStorage fallback helpers ---
function upsert(list, rec, kp) {
  const i = list.findIndex((r) => r[kp] === rec[kp])
  if (i >= 0) list[i] = rec
  else list.push(rec)
  return list
}
function saveAllLS(store, mutate) {
  const list = load(lsKey(store), [])
  save(lsKey(store), mutate(list))
}
