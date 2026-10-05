import { useMemo } from 'react'
import {
  RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell, AreaChart, Area, CartesianGrid,
} from 'recharts'
import { computeStats, fmtHold } from '../lib/journal.js'
import {
  filterTrades, advancedStats, performanceScore,
  byWeekday, byHour, bySymbol, byPlaybook, bySide, byTag, cumulativePnl, dailyBars,
} from '../lib/reports.js'
import { fmtUSD, fmtPct, fmtNum } from '../lib/risk.js'
import { Card, Stat } from './ui.jsx'
import FilterBar from './FilterBar.jsx'

const GREEN = '#00d15f'
const RED = '#ff3b30'
const AMBER = '#ff9800'

export default function Reports({ trades, settings, filter, setFilter }) {
  const f = useMemo(() => filterTrades(trades, filter), [trades, filter])
  const stats = useMemo(() => computeStats(f, settings), [f, settings])
  const adv = useMemo(() => advancedStats(f), [f])
  const score = useMemo(() => performanceScore(f, stats, settings), [f, stats, settings])
  const cum = useMemo(() => cumulativePnl(f), [f])
  const bars = useMemo(() => dailyBars(f), [f])

  const scoreTone = score.overall >= 70 ? GREEN : score.overall >= 40 ? AMBER : RED

  if (!f.length) {
    return (
      <div className="space-y-2">
        <FilterBar trades={trades} filter={filter} setFilter={setFilter} />
        <Card title="REPORTS"><p className="py-8 text-center uppercase text-bbg-dim">No trades in range</p></Card>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <FilterBar trades={trades} filter={filter} setFilter={setFilter} />

      <div className="grid gap-2 lg:grid-cols-3">
        {/* Performance score */}
        <Card title="PERFORMANCE SCORE">
          <div className="flex items-center gap-3">
            <div className="text-center">
              <div className="tnum text-5xl font-bold leading-none" style={{ color: scoreTone }}>{score.overall}</div>
              <div className="mt-1 text-[10px] uppercase tracking-wider text-bbg-dim">/ 100</div>
            </div>
            <div className="h-40 flex-1">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={score.axes} outerRadius="72%">
                  <PolarGrid stroke="#2a2a2a" />
                  <PolarAngleAxis dataKey="name" tick={{ fill: '#7d7d7d', fontSize: 9 }} />
                  <Radar dataKey="score" stroke={AMBER} fill={AMBER} fillOpacity={0.35} isAnimationActive={false} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </Card>

        {/* Key stats */}
        <Card title="STATS" className="lg:col-span-2">
          <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
            <Stat label="Net P&L" value={fmtUSD(stats.netPnl, 0)} tone={stats.netPnl >= 0 ? 'good' : 'bad'} />
            <Stat label="Trades" value={stats.n} sub={`${stats.wins}W/${stats.losses}L`} />
            <Stat label="Win rate" value={fmtPct(stats.winRate, 0)} />
            <Stat label="Profit factor" value={stats.profitFactor === Infinity ? '∞' : fmtNum(stats.profitFactor, 2)} />
            <Stat label="Avg win" value={fmtUSD(stats.avgWin, 0)} tone="good" />
            <Stat label="Avg loss" value={fmtUSD(stats.avgLoss, 0)} tone="bad" />
            <Stat label="Expectancy" value={fmtUSD(stats.expectancy, 1)} tone={stats.expectancy >= 0 ? 'good' : 'bad'} />
            <Stat label="Avg R" value={adv.avgR != null ? `${fmtNum(adv.avgR, 2)}R` : '—'} tone={adv.avgR >= 0 ? 'good' : 'bad'} />
            <Stat label="Largest win" value={fmtUSD(adv.largestWin, 0)} tone="good" />
            <Stat label="Largest loss" value={fmtUSD(adv.largestLoss, 0)} tone="bad" />
            <Stat label="Max win streak" value={adv.maxConsecWins} />
            <Stat label="Max loss streak" value={adv.maxConsecLosses} />
            <Stat label="Avg hold" value={fmtHold(adv.avgHoldMs)} />
            <Stat label="Green/Red days" value={`${adv.winningDays}/${adv.losingDays}`} />
            <Stat label="Avg daily" value={fmtUSD(adv.avgDailyPnl, 0)} tone={adv.avgDailyPnl >= 0 ? 'good' : 'bad'} />
            <Stat label="Total fees" value={fmtUSD(adv.totalFees, 0)} tone="bad" />
          </div>
        </Card>
      </div>

      {/* P&L charts */}
      <div className="grid gap-2 lg:grid-cols-2">
        <Card title="CUMULATIVE NET P&L">
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={cum} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                <defs>
                  <linearGradient id="cumFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={AMBER} stopOpacity={0.5} />
                    <stop offset="100%" stopColor={AMBER} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1c1c1c" strokeDasharray="2 2" />
                <XAxis dataKey="i" tick={{ fill: '#7d7d7d', fontSize: 10 }} stroke="#2a2a2a" />
                <YAxis tick={{ fill: '#7d7d7d', fontSize: 10 }} stroke="#2a2a2a" tickFormatter={(v) => fmtNum(v, 0)} />
                <Tooltip contentStyle={tt} itemStyle={{ color: '#ffcc33' }} labelStyle={{ color: AMBER }}
                  formatter={(v) => [fmtUSD(v, 2), 'CUM']} labelFormatter={(i) => `TRADE ${i}`} />
                <Area type="stepAfter" dataKey="cum" stroke={AMBER} strokeWidth={1.5} fill="url(#cumFill)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="NET DAILY P&L">
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bars} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                <CartesianGrid stroke="#1c1c1c" strokeDasharray="2 2" />
                <XAxis dataKey="day" tick={{ fill: '#7d7d7d', fontSize: 9 }} stroke="#2a2a2a"
                  tickFormatter={(d) => d.slice(5)} />
                <YAxis tick={{ fill: '#7d7d7d', fontSize: 10 }} stroke="#2a2a2a" tickFormatter={(v) => fmtNum(v, 0)} />
                <Tooltip contentStyle={tt} itemStyle={{ color: '#ffcc33' }} labelStyle={{ color: AMBER }}
                  formatter={(v) => [fmtUSD(v, 2), 'P&L']} />
                <Bar dataKey="pnl" isAnimationActive={false}>
                  {bars.map((b, i) => <Cell key={i} fill={b.pnl >= 0 ? GREEN : RED} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Weekday + hour bar charts */}
      <div className="grid gap-2 lg:grid-cols-2">
        <BucketBars title="P&L BY WEEKDAY" data={byWeekday(f)} />
        <BucketBars title="P&L BY HOUR (ENTRY)" data={byHour(f)} />
      </div>

      {/* Breakdown tables */}
      <div className="grid gap-2 lg:grid-cols-2">
        <BucketTable title="BY PLAYBOOK" rows={byPlaybook(f)} />
        <BucketTable title="BY SYMBOL" rows={bySymbol(f)} />
        <BucketTable title="BY SIDE" rows={bySide(f)} />
        <BucketTable title="BY TAG" rows={byTag(f)} empty="No tags" />
      </div>
    </div>
  )
}

const tt = { background: '#000', border: `1px solid ${AMBER}`, borderRadius: 0, fontSize: 11, fontFamily: 'monospace' }

function BucketBars({ title, data }) {
  return (
    <Card title={title}>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="#1c1c1c" strokeDasharray="2 2" />
            <XAxis dataKey="key" tick={{ fill: '#7d7d7d', fontSize: 9 }} stroke="#2a2a2a" />
            <YAxis tick={{ fill: '#7d7d7d', fontSize: 10 }} stroke="#2a2a2a" tickFormatter={(v) => fmtNum(v, 0)} />
            <Tooltip contentStyle={tt} itemStyle={{ color: '#ffcc33' }} labelStyle={{ color: AMBER }}
              formatter={(v, n, p) => [`${fmtUSD(v, 2)} · ${p.payload.count}T · ${fmtPct(p.payload.winRate, 0)}`, 'P&L']} />
            <Bar dataKey="pnl" isAnimationActive={false}>
              {data.map((b, i) => <Cell key={i} fill={b.pnl >= 0 ? GREEN : RED} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function BucketTable({ title, rows, empty = 'No data' }) {
  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.pnl)))
  return (
    <Card title={title}>
      {rows.length === 0 ? (
        <p className="py-4 text-center text-[11px] uppercase text-bbg-dim">{empty}</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-bbg-dim">
              <th className="pb-1 font-bold">Bucket</th>
              <th className="pb-1 text-right font-bold">Trades</th>
              <th className="pb-1 text-right font-bold">Win%</th>
              <th className="pb-1 text-right font-bold">Net P&L</th>
              <th className="w-24 pb-1" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-bbg-grid">
                <td className="py-1 font-bold text-bbg-gold">{r.key}</td>
                <td className="tnum py-1 text-right text-bbg-text">{r.count}</td>
                <td className="tnum py-1 text-right text-bbg-text">{fmtPct(r.winRate, 0)}</td>
                <td className={`tnum py-1 text-right font-bold ${r.pnl >= 0 ? 'text-bbg-green' : 'text-bbg-red'}`}>
                  {r.pnl >= 0 ? '+' : ''}{fmtUSD(r.pnl, 0)}
                </td>
                <td className="py-1 pl-2">
                  <div className="h-2 w-full bg-black">
                    <div className="h-full" style={{
                      width: `${(Math.abs(r.pnl) / maxAbs) * 100}%`,
                      background: r.pnl >= 0 ? GREEN : RED,
                    }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}
