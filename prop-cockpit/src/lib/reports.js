// Tradezella-style analytics engine. Pure functions over the trade list,
// reusing deriveTrade / dailyPnl / dayOf from journal.js.

import { deriveTrade, dailyPnl, dayOf } from './journal.js'

// The playbook/setup name for a trade (back-compat with old `setup` field).
export const playbookOf = (t) => t.playbook || t.setup || 'Unassigned'
// Timestamp used for time-of-day analysis: entryTime if present, else date.
const whenOf = (t) => new Date(t.entryTime || t.date)

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

// --- Filtering ---
export function filterTrades(trades, f = {}) {
  return trades.filter((t) => {
    if (f.from && dayOf(t.date) < f.from) return false
    if (f.to && dayOf(t.date) > f.to) return false
    if (f.symbol && !(t.symbol || '').toUpperCase().includes(f.symbol.toUpperCase())) return false
    if (f.side && f.side !== 'all' && (t.direction || 'long') !== f.side) return false
    if (f.playbook && f.playbook !== 'all' && playbookOf(t) !== f.playbook) return false
    if (f.tag && f.tag !== 'all' && !(t.tags || []).includes(f.tag)) return false
    return true
  })
}

export function hasActiveFilter(f = {}) {
  return !!(
    f.from || f.to || f.symbol ||
    (f.side && f.side !== 'all') ||
    (f.playbook && f.playbook !== 'all') ||
    (f.tag && f.tag !== 'all')
  )
}

// All distinct tags across trades (for the filter dropdown).
export function allTags(trades) {
  const s = new Set()
  for (const t of trades) for (const tag of t.tags || []) s.add(tag)
  return [...s].sort()
}

// --- Grouped breakdown ---
// keyFn(t) -> string | string[] (arrays fan a trade into multiple buckets, e.g. tags)
export function breakdown(trades, keyFn) {
  const m = new Map()
  for (const t of trades) {
    const keys = keyFn(t)
    for (const k of Array.isArray(keys) ? keys : [keys]) {
      if (k == null || k === '') continue
      const cur = m.get(k) || { key: k, pnl: 0, count: 0, wins: 0, losses: 0 }
      cur.pnl += t.pnl
      cur.count += 1
      if (t.pnl > 0) cur.wins += 1
      else if (t.pnl < 0) cur.losses += 1
      m.set(k, cur)
    }
  }
  return [...m.values()].map((b) => ({
    ...b,
    winRate: b.count ? (b.wins / b.count) * 100 : 0,
  }))
}

export const byWeekday = (trades) => {
  const rows = breakdown(trades, (t) => WEEKDAYS[whenOf(t).getDay()])
  return WEEKDAYS.map((d) => rows.find((r) => r.key === d) || { key: d, pnl: 0, count: 0, wins: 0, losses: 0, winRate: 0 })
}
export const byHour = (trades) => {
  const rows = breakdown(trades, (t) => String(whenOf(t).getHours()).padStart(2, '0'))
  return Array.from({ length: 24 }, (_, h) => {
    const k = String(h).padStart(2, '0')
    return rows.find((r) => r.key === k) || { key: k, pnl: 0, count: 0, wins: 0, losses: 0, winRate: 0 }
  })
}
export const bySymbol = (trades) => breakdown(trades, (t) => t.symbol || '—').sort((a, b) => b.pnl - a.pnl)
export const byPlaybook = (trades) => breakdown(trades, playbookOf).sort((a, b) => b.pnl - a.pnl)
export const bySide = (trades) => breakdown(trades, (t) => (t.direction === 'short' ? 'Short' : 'Long'))
export const byTag = (trades) => breakdown(trades, (t) => t.tags || []).sort((a, b) => b.pnl - a.pnl)

// --- Series for charts ---
export function cumulativePnl(trades) {
  const sorted = [...trades].sort((a, b) => new Date(a.date) - new Date(b.date))
  let cum = 0
  return sorted.map((t, i) => {
    cum += t.pnl
    return { i: i + 1, cum, pnl: t.pnl, date: t.date }
  })
}

export function dailyBars(trades) {
  const map = dailyPnl(trades)
  return [...map.entries()]
    .map(([day, v]) => ({ day, pnl: v.pnl, count: v.count }))
    .sort((a, b) => (a.day < b.day ? -1 : 1))
}

// --- Advanced stats ---
export function advancedStats(trades) {
  const n = trades.length
  const wins = trades.filter((t) => t.pnl > 0)
  const losses = trades.filter((t) => t.pnl < 0)
  const pnls = trades.map((t) => t.pnl)
  const largestWin = wins.length ? Math.max(...wins.map((t) => t.pnl)) : 0
  const largestLoss = losses.length ? Math.min(...losses.map((t) => t.pnl)) : 0

  // Consecutive streaks (chronological).
  const sorted = [...trades].sort((a, b) => new Date(a.date) - new Date(b.date))
  let maxW = 0, maxL = 0, curW = 0, curL = 0
  for (const t of sorted) {
    if (t.pnl > 0) { curW++; curL = 0 }
    else if (t.pnl < 0) { curL++; curW = 0 }
    else { curW = 0; curL = 0 }
    maxW = Math.max(maxW, curW)
    maxL = Math.max(maxL, curL)
  }

  const rs = trades.map((t) => deriveTrade(t).rMultiple).filter((r) => r != null)
  const avgR = rs.length ? rs.reduce((s, r) => s + r, 0) / rs.length : null

  const holds = trades.map((t) => deriveTrade(t).holdMs).filter((h) => h != null)
  const avgHoldMs = holds.length ? holds.reduce((s, h) => s + h, 0) / holds.length : null

  const totalFees = trades.reduce((s, t) => s + (Number(t.fees) || 0), 0)

  const days = dailyPnl(trades)
  const dayVals = [...days.values()]
  const winningDays = dayVals.filter((d) => d.pnl > 0).length
  const losingDays = dayVals.filter((d) => d.pnl < 0).length
  const avgDailyPnl = dayVals.length
    ? dayVals.reduce((s, d) => s + d.pnl, 0) / dayVals.length
    : 0

  return {
    n,
    largestWin,
    largestLoss,
    maxConsecWins: maxW,
    maxConsecLosses: maxL,
    avgR,
    avgHoldMs,
    totalFees,
    tradingDays: dayVals.length,
    winningDays,
    losingDays,
    avgDailyPnl,
  }
}

// --- Zella-style performance score (0-100 composite over 6 axes) ---
export function performanceScore(trades, stats, settings) {
  const clamp = (v) => Math.max(0, Math.min(100, v))

  // stats = output of computeStats (winRate, profitFactor, avgWin, avgLoss,
  // netPnl, maxDrawdown). settings for the drawdown buffer.
  const winScore = clamp((stats.winRate / 60) * 100)
  const pf = stats.profitFactor === Infinity ? 3 : stats.profitFactor
  const pfScore = clamp((pf / 2) * 100)
  const wlRatio = stats.avgLoss > 0 ? stats.avgWin / stats.avgLoss : (stats.avgWin > 0 ? 3 : 0)
  const wlScore = clamp((wlRatio / 2) * 100)
  const recovery = stats.maxDrawdown > 0 ? stats.netPnl / stats.maxDrawdown : (stats.netPnl > 0 ? 3 : 0)
  const recoveryScore = clamp((recovery / 3) * 100)

  const adv = advancedStats(trades)
  const consistency = adv.tradingDays ? (adv.winningDays / adv.tradingDays) * 100 : 0
  const consistencyScore = clamp(consistency)

  const buffer = (settings.startingBalance * settings.maxDrawdownPct) / 100 || 1
  const ddScore = clamp(100 - (stats.maxDrawdown / buffer) * 100)

  const axes = [
    { name: 'Win %', score: Math.round(winScore) },
    { name: 'Profit Factor', score: Math.round(pfScore) },
    { name: 'Win/Loss', score: Math.round(wlScore) },
    { name: 'Recovery', score: Math.round(recoveryScore) },
    { name: 'Consistency', score: Math.round(consistencyScore) },
    { name: 'Drawdown', score: Math.round(ddScore) },
  ]
  const overall = Math.round(axes.reduce((s, a) => s + a.score, 0) / axes.length)
  return { overall, axes }
}
