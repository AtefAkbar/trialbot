// Risk framework — all the math from the agreed spec lives here so the
// scanner, position calculator, and journal share one source of truth.

// Default account + risk configuration. Everything is overridable in Settings
// and persisted to localStorage.
export const DEFAULT_SETTINGS = {
  startingBalance: 5000,      // prop account start
  maxDrawdownPct: 10,         // overall: 10% = $500 buffer
  dailyLossLimit: 200,        // hard daily floor ($4,800 = -$200)
  stageTarget: 400,           // Stage 1 profit target (8%)
  riskPerTradePct: 1.0,       // 0.5–1.5% of account per trade
  stopMultiplier: 1.5,        // stop distance = range% × this
  // Self-imposed "soft" daily stop — buffer, not brinkmanship.
  softDailyLoss: 110,         // stop after ~$100–120 lost in a day
  maxConsecutiveLosses: 2,    // …or after 2 losses in a row
}

// The four asset zones, keyed by 24h range %.
export const ZONES = [
  { key: 'quiet', label: 'QUIET',  color: '#7d7d7d', min: 0,    max: 1.5,
    note: 'Not enough movement to hit a target same-day.', tradeable: false, sizeFactor: 0 },
  { key: 'sweet', label: 'SWEET',  color: '#00d15f', min: 1.5,  max: 8,
    note: 'Most BTC/ETH-tier majors land here.', tradeable: true, sizeFactor: 1 },
  { key: 'hot',   label: 'ELEV',   color: '#ff9800', min: 8,    max: 15,
    note: 'Tradeable but size down and widen the stop.', tradeable: true, sizeFactor: 0.5 },
  { key: 'wild',  label: 'WILD',   color: '#ff3b30', min: 15,   max: Infinity,
    note: 'Meme coins / small caps — avoid for this account.', tradeable: false, sizeFactor: 0 },
]

export function classifyZone(rangePct) {
  if (rangePct == null || Number.isNaN(rangePct)) return null
  return ZONES.find((z) => rangePct >= z.min && rangePct < z.max) || ZONES[ZONES.length - 1]
}

// Risk dollars for a given account equity.
export function riskDollars(settings, equity) {
  const base = equity ?? settings.startingBalance
  return (base * settings.riskPerTradePct) / 100
}

// Position sizing from the spec:
//   stop distance % = range% × multiplier
//   position notional = risk$ / (stop distance % / 100)
//   leverage = position notional / account equity
//
// `sizeFactor` lets elevated zones automatically size down.
export function sizePosition({ rangePct, settings, equity, sizeFactor = 1 }) {
  const eq = equity ?? settings.startingBalance
  const stopDistancePct = rangePct * settings.stopMultiplier
  const risk = riskDollars(settings, eq) * sizeFactor
  const notional = stopDistancePct > 0 ? risk / (stopDistancePct / 100) : 0
  const leverage = eq > 0 ? notional / eq : 0
  return {
    stopDistancePct,
    riskDollars: risk,
    notional,
    leverage,
  }
}

// Manual position calc — user supplies entry, stop, and risk$ directly.
export function calcFromStop({ entry, stop, riskDollars: risk, equity }) {
  const stopDistance = Math.abs(entry - stop)
  const stopDistancePct = entry > 0 ? (stopDistance / entry) * 100 : 0
  const units = stopDistance > 0 ? risk / stopDistance : 0
  const notional = units * entry
  const leverage = equity > 0 ? notional / equity : 0
  return { stopDistance, stopDistancePct, units, notional, leverage }
}

export function fmtUSD(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function fmtCompactUSD(n) {
  if (n == null || Number.isNaN(n)) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}

export function fmtPct(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return '—'
  return `${n.toFixed(digits)}%`
}

export function fmtNum(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}
