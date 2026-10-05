import { useMemo, useState } from 'react'
import { dailyPnl, todayKey } from '../lib/journal.js'
import { filterTrades } from '../lib/reports.js'
import { fmtUSD, fmtCompactUSD } from '../lib/risk.js'
import { Card } from './ui.jsx'
import FilterBar from './FilterBar.jsx'

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const DOW = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']

function keyOf(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

// rgba color for a P&L value, scaled against the period's max magnitude.
function cellColor(pnl, maxAbs) {
  if (pnl == null) return { bg: '#0a0a0a', bd: '#1c1c1c' }
  if (pnl === 0) return { bg: '#141414', bd: '#2a2a2a' }
  const t = Math.min(1, Math.abs(pnl) / (maxAbs || 1))
  const a = 0.14 + 0.66 * t
  return pnl > 0
    ? { bg: `rgba(0,209,95,${a})`, bd: 'rgba(0,209,95,0.5)' }
    : { bg: `rgba(255,59,48,${a})`, bd: 'rgba(255,59,48,0.5)' }
}

export default function Calendar({ trades, filter, setFilter, onSelectDay }) {
  const shown = useMemo(() => filterTrades(trades, filter || {}), [trades, filter])
  const days = useMemo(() => dailyPnl(shown), [shown])

  const now = new Date()
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() })

  function shift(delta) {
    setYm(({ y, m }) => {
      const nm = m + delta
      return { y: y + Math.floor(nm / 12), m: ((nm % 12) + 12) % 12 }
    })
  }

  // ---- Monthly grid ----
  const month = useMemo(() => {
    const { y, m } = ym
    const first = new Date(y, m, 1)
    const startPad = first.getDay()
    const daysInMonth = new Date(y, m + 1, 0).getDate()
    const cells = []
    for (let i = 0; i < startPad; i++) cells.push(null)
    let total = 0, winDays = 0, lossDays = 0, tradeCount = 0, maxAbs = 0
    for (let d = 1; d <= daysInMonth; d++) {
      const rec = days.get(keyOf(y, m, d)) || null
      if (rec) {
        total += rec.pnl
        tradeCount += rec.count
        if (rec.pnl > 0) winDays++
        else if (rec.pnl < 0) lossDays++
        maxAbs = Math.max(maxAbs, Math.abs(rec.pnl))
      }
      cells.push({ d, rec })
    }
    while (cells.length % 7) cells.push(null)
    return { cells, total, winDays, lossDays, tradeCount, maxAbs }
  }, [ym, days])

  // ---- Yearly contribution strip (trailing ~53 weeks) ----
  const year = useMemo(() => {
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const start = new Date(end)
    start.setDate(start.getDate() - 7 * 52 - end.getDay())
    const weeks = []
    let maxAbs = 0
    let cur = new Date(start)
    while (cur <= end) {
      const week = []
      for (let i = 0; i < 7; i++) {
        const k = keyOf(cur.getFullYear(), cur.getMonth(), cur.getDate())
        const rec = days.get(k) || null
        if (rec) maxAbs = Math.max(maxAbs, Math.abs(rec.pnl))
        week.push({ key: k, date: new Date(cur), rec })
        cur.setDate(cur.getDate() + 1)
      }
      weeks.push(week)
    }
    return { weeks, maxAbs }
  }, [ym, days])

  const tk = todayKey()

  return (
    <div className="space-y-2">
      {setFilter && <FilterBar trades={trades} filter={filter} setFilter={setFilter} />}

      {/* Yearly heatmap strip */}
      <Card title="TRADE MAP · TRAILING 12 MONTHS">
        <div className="overflow-x-auto">
          <div className="flex gap-[3px]">
            {year.weeks.map((week, wi) => (
              <div key={wi} className="flex flex-col gap-[3px]">
                {week.map((cell) => {
                  const c = cellColor(cell.rec?.pnl ?? null, year.maxAbs)
                  const isToday = cell.key === tk
                  return (
                    <div
                      key={cell.key}
                      title={`${cell.key}${cell.rec ? ` · ${fmtUSD(cell.rec.pnl)} · ${cell.rec.count} trades` : ' · no trades'}`}
                      className="h-3 w-3"
                      style={{ background: c.bg, border: `1px solid ${isToday ? '#ff9800' : c.bd}` }}
                    />
                  )
                })}
              </div>
            ))}
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2 text-[10px] uppercase text-bbg-dim">
          <span>LOSS</span>
          <span className="h-3 w-3" style={{ background: 'rgba(255,59,48,0.7)' }} />
          <span className="h-3 w-3" style={{ background: 'rgba(255,59,48,0.3)' }} />
          <span className="h-3 w-3" style={{ background: '#141414' }} />
          <span className="h-3 w-3" style={{ background: 'rgba(0,209,95,0.3)' }} />
          <span className="h-3 w-3" style={{ background: 'rgba(0,209,95,0.7)' }} />
          <span>PROFIT</span>
        </div>
      </Card>

      {/* Monthly calendar */}
      <Card
        title={`P&L CALENDAR · ${MONTHS[ym.m]} ${ym.y}`}
        right={
          <div className="flex items-center gap-1">
            <button onClick={() => shift(-1)} className="border border-bbg-border bg-black px-2 py-0.5 text-[11px] text-bbg-amber2 hover:bg-bbg-head">◀</button>
            <button onClick={() => setYm({ y: now.getFullYear(), m: now.getMonth() })} className="border border-bbg-border bg-black px-2 py-0.5 text-[10px] uppercase text-bbg-amber2 hover:bg-bbg-head">TODAY</button>
            <button onClick={() => shift(1)} className="border border-bbg-border bg-black px-2 py-0.5 text-[11px] text-bbg-amber2 hover:bg-bbg-head">▶</button>
          </div>
        }
      >
        {/* Month summary */}
        <div className="mb-2 flex flex-wrap gap-4 border-b border-bbg-grid pb-2 text-[11px] uppercase">
          <span className="text-bbg-dim">NET <span className={`tnum font-bold ${month.total >= 0 ? 'text-bbg-green' : 'text-bbg-red'}`}>{month.total >= 0 ? '+' : ''}{fmtUSD(month.total)}</span></span>
          <span className="text-bbg-dim">GREEN DAYS <span className="tnum font-bold text-bbg-green">{month.winDays}</span></span>
          <span className="text-bbg-dim">RED DAYS <span className="tnum font-bold text-bbg-red">{month.lossDays}</span></span>
          <span className="text-bbg-dim">TRADES <span className="tnum font-bold text-bbg-text">{month.tradeCount}</span></span>
        </div>

        {/* Weekday header */}
        <div className="grid grid-cols-7 gap-1">
          {DOW.map((d) => (
            <div key={d} className="pb-1 text-center text-[10px] font-bold uppercase text-bbg-amber">{d}</div>
          ))}
          {month.cells.map((cell, i) => {
            if (!cell) return <div key={i} className="min-h-[64px] border border-transparent" />
            const c = cellColor(cell.rec?.pnl ?? null, month.maxAbs)
            const isToday = keyOf(ym.y, ym.m, cell.d) === tk
            const dayKey = keyOf(ym.y, ym.m, cell.d)
            return (
              <div
                key={i}
                onClick={() => onSelectDay?.(dayKey)}
                title={onSelectDay ? 'Open notebook for this day' : undefined}
                className={`min-h-[64px] p-1 ${onSelectDay ? 'cursor-pointer hover:outline hover:outline-1 hover:outline-bbg-amber' : ''}`}
                style={{ background: c.bg, border: `1px solid ${isToday ? '#ff9800' : c.bd}` }}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] tnum ${isToday ? 'font-bold text-bbg-amber' : 'text-bbg-dim'}`}>{cell.d}</span>
                  {cell.rec && <span className="text-[9px] text-bbg-dim">{cell.rec.count}T</span>}
                </div>
                {cell.rec && (
                  <div className={`tnum mt-2 text-center text-[12px] font-bold ${cell.rec.pnl >= 0 ? 'text-bbg-green' : 'text-bbg-red'}`}>
                    {cell.rec.pnl >= 0 ? '+' : ''}{fmtCompactUSD(cell.rec.pnl)}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Card>
    </div>
  )
}
