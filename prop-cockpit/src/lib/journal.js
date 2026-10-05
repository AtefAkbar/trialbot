// Journal analytics — derives all progress/drawdown/expectancy metrics from
// the raw list of closed trades plus account settings.

// A trade: { id, date (ISO), symbol, direction, pnl (number, net $),
//            rMultiple (optional), note }

export function todayKey(d = new Date()) {
  // Local calendar day, YYYY-MM-DD.
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function dayOf(isoDate) {
  return todayKey(new Date(isoDate))
}

export function computeStats(trades, settings) {
  const sorted = [...trades].sort((a, b) => new Date(a.date) - new Date(b.date))

  const start = settings.startingBalance
  let equity = start
  let peak = start
  let maxDrawdown = 0 // worst peak-to-trough in $
  const equityCurve = [{ i: 0, equity: start, date: null }]

  for (let i = 0; i < sorted.length; i++) {
    equity += sorted[i].pnl
    peak = Math.max(peak, equity)
    maxDrawdown = Math.max(maxDrawdown, peak - equity)
    equityCurve.push({ i: i + 1, equity, date: sorted[i].date })
  }

  const netPnl = equity - start
  const wins = sorted.filter((t) => t.pnl > 0)
  const losses = sorted.filter((t) => t.pnl < 0)
  const n = sorted.length
  const winRate = n ? (wins.length / n) * 100 : 0

  const grossWin = wins.reduce((s, t) => s + t.pnl, 0)
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0))
  const avgWin = wins.length ? grossWin / wins.length : 0
  const avgLoss = losses.length ? grossLoss / losses.length : 0
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0)

  // Expectancy per trade in $.
  const expectancy = n ? netPnl / n : 0

  // Progress to Stage 1 target.
  const targetPct = settings.stageTarget > 0
    ? Math.max(0, Math.min(100, (netPnl / settings.stageTarget) * 100))
    : 0
  const remainingToTarget = settings.stageTarget - netPnl
  const tradesToTarget =
    expectancy > 0 && remainingToTarget > 0
      ? Math.ceil(remainingToTarget / expectancy)
      : (remainingToTarget <= 0 ? 0 : null)

  // Overall drawdown budget: 10% of starting balance.
  const overallBuffer = (start * settings.maxDrawdownPct) / 100
  // Floor equity = start - buffer. Used-up drawdown is start - currentEquity
  // when underwater (relative to start), but the prop rule is peak-based for
  // trailing accounts and static here — we track distance to the hard floor.
  const drawdownFloor = start - overallBuffer
  const overallDdUsed = Math.max(0, start - equity)
  const overallDdRemaining = equity - drawdownFloor

  // Today's numbers.
  const tk = todayKey()
  const todays = sorted.filter((t) => dayOf(t.date) === tk)
  const todayPnl = todays.reduce((s, t) => s + t.pnl, 0)
  const todayLoss = todayPnl < 0 ? -todayPnl : 0
  const dailyRemaining = settings.dailyLossLimit - todayLoss

  // Consecutive losses (most recent streak).
  let streak = 0
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (sorted[i].pnl < 0) streak++
    else break
  }

  // Soft-stop guardrails.
  const softStopHit =
    todayLoss >= settings.softDailyLoss ||
    (streakToday(sorted, tk) >= settings.maxConsecutiveLosses)

  return {
    equity,
    netPnl,
    n,
    wins: wins.length,
    losses: losses.length,
    winRate,
    avgWin,
    avgLoss,
    profitFactor,
    expectancy,
    maxDrawdown,
    equityCurve,
    targetPct,
    remainingToTarget,
    tradesToTarget,
    overallBuffer,
    overallDdUsed,
    overallDdRemaining,
    drawdownFloor,
    todayPnl,
    todayLoss,
    dailyRemaining,
    consecutiveLosses: streak,
    softStopHit,
  }
}

// Per-day aggregation for the calendar heatmap.
// Returns Map<'YYYY-MM-DD', { pnl, count, wins, losses }>.
export function dailyPnl(trades) {
  const m = new Map()
  for (const t of trades) {
    const k = dayOf(t.date)
    const cur = m.get(k) || { pnl: 0, count: 0, wins: 0, losses: 0 }
    cur.pnl += t.pnl
    cur.count += 1
    if (t.pnl > 0) cur.wins += 1
    else if (t.pnl < 0) cur.losses += 1
    m.set(k, cur)
  }
  return m
}

// Derived context for a single trade from optional price fields. Keeps `pnl`
// authoritative (user-entered net) while surfacing R-multiple / stop distance
// when entry+stop(+exit) are provided.
export function deriveTrade(t) {
  const entry = num(t.entry)
  const stop = num(t.stop)
  const exit = num(t.exit)
  const size = num(t.size)
  const dir = t.direction === 'short' ? -1 : 1

  let stopDistPct = null
  let riskPerUnit = null
  if (entry != null && stop != null && entry !== stop) {
    riskPerUnit = Math.abs(entry - stop)
    stopDistPct = (riskPerUnit / entry) * 100
  }

  let rMultiple = t.rMultiple != null ? num(t.rMultiple) : null
  if (rMultiple == null && riskPerUnit && exit != null) {
    rMultiple = (dir * (exit - entry)) / riskPerUnit
  }

  // Suggested net P&L if exit + size given (for the auto-fill convenience).
  let pnlSuggested = null
  if (entry != null && exit != null && size != null) {
    pnlSuggested = dir * (exit - entry) * size - (num(t.fees) || 0)
  }

  // Hold time from entry/exit timestamps, in ms.
  let holdMs = null
  if (t.entryTime && t.exitTime) {
    const ms = new Date(t.exitTime) - new Date(t.entryTime)
    if (Number.isFinite(ms) && ms >= 0) holdMs = ms
  }

  return { stopDistPct, rMultiple, pnlSuggested, holdMs }
}

// Human-readable hold time from milliseconds.
export function fmtHold(ms) {
  if (ms == null) return '—'
  const min = Math.round(ms / 60000)
  if (min < 60) return `${min}m`
  const h = Math.floor(min / 60)
  const m = min % 60
  if (h < 24) return m ? `${h}h ${m}m` : `${h}h`
  const d = Math.floor(h / 24)
  return `${d}d ${h % 24}h`
}

function num(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

// Consecutive losing trades within today's session only.
function streakToday(sorted, tk) {
  const todays = sorted.filter((t) => dayOf(t.date) === tk)
  let s = 0
  for (let i = todays.length - 1; i >= 0; i--) {
    if (todays[i].pnl < 0) s++
    else break
  }
  return s
}
