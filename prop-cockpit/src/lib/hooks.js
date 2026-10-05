import { useCallback, useEffect, useState } from 'react'
import { load, save, KEYS } from './storage.js'
import { DEFAULT_SETTINGS } from './risk.js'
import {
  loadWithMigration, putTrade, deleteTrade, clearTrades,
  getAll, put, del,
} from './db.js'

// Settings persisted to localStorage, merged over defaults so new fields
// added in later versions still get sensible values.
export function useSettings() {
  const [settings, setSettings] = useState(() => ({
    ...DEFAULT_SETTINGS,
    ...load(KEYS.settings, {}),
  }))

  useEffect(() => {
    save(KEYS.settings, settings)
  }, [settings])

  const update = useCallback((patch) => {
    setSettings((s) => ({ ...s, ...patch }))
  }, [])

  const reset = useCallback(() => setSettings({ ...DEFAULT_SETTINGS }), [])

  return { settings, update, reset }
}

// Trade journal backed by IndexedDB (screenshots make records too big for
// localStorage). Loads async on mount, migrating any legacy localStorage data.
export function useTrades() {
  const [trades, setTrades] = useState([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let alive = true
    loadWithMigration().then((list) => {
      if (alive) {
        setTrades(list)
        setLoaded(true)
      }
    })
    return () => {
      alive = false
    }
  }, [])

  const addTrade = useCallback(async (t) => {
    const rec = { id: cryptoId(), ...t }
    setTrades((list) => [...list, rec])
    await putTrade(rec)
    return rec
  }, [])

  const updateTrade = useCallback(async (rec) => {
    setTrades((list) => list.map((t) => (t.id === rec.id ? rec : t)))
    await putTrade(rec)
  }, [])

  const removeTrade = useCallback(async (id) => {
    setTrades((list) => list.filter((t) => t.id !== id))
    await deleteTrade(id)
  }, [])

  const clearAll = useCallback(async () => {
    setTrades([])
    await clearTrades()
  }, [])

  return { trades, addTrade, updateTrade, removeTrade, clearAll, loaded }
}

// Default playbooks seeded on first run (match the journal's original setups).
export const DEFAULT_PLAYBOOKS = [
  'Breakout', 'Trend pullback', 'Range fade', 'Reversal', 'News', 'Scalp',
].map((name, i) => ({
  id: `pb_default_${i}`,
  name,
  description: '',
  rules: [],
}))

// Playbooks (named strategies + rules) in IndexedDB.
export function usePlaybooks() {
  const [playbooks, setPlaybooks] = useState([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let alive = true
    getAll('playbooks').then(async (list) => {
      if (!list.length) {
        // seed defaults once
        for (const pb of DEFAULT_PLAYBOOKS) await put('playbooks', pb)
        list = DEFAULT_PLAYBOOKS
      }
      if (alive) {
        setPlaybooks(list)
        setLoaded(true)
      }
    })
    return () => {
      alive = false
    }
  }, [])

  const savePlaybook = useCallback(async (pb) => {
    const rec = pb.id ? pb : { ...pb, id: cryptoId() }
    setPlaybooks((list) => {
      const i = list.findIndex((p) => p.id === rec.id)
      return i >= 0 ? list.map((p) => (p.id === rec.id ? rec : p)) : [...list, rec]
    })
    await put('playbooks', rec)
    return rec
  }, [])

  const removePlaybook = useCallback(async (id) => {
    setPlaybooks((list) => list.filter((p) => p.id !== id))
    await del('playbooks', id)
  }, [])

  return { playbooks, savePlaybook, removePlaybook, loaded }
}

// Daily notebook entries, keyed by 'YYYY-MM-DD', in IndexedDB.
export function useNotebook() {
  const [entries, setEntries] = useState({}) // day -> entry
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let alive = true
    getAll('notebook').then((list) => {
      if (alive) {
        const map = {}
        for (const e of list) map[e.day] = e
        setEntries(map)
        setLoaded(true)
      }
    })
    return () => {
      alive = false
    }
  }, [])

  const saveEntry = useCallback(async (entry) => {
    setEntries((m) => ({ ...m, [entry.day]: entry }))
    await put('notebook', entry)
  }, [])

  return { entries, saveEntry, loaded }
}

function cryptoId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 't_' + Math.random().toString(36).slice(2) + Date.now().toString(36)
}
