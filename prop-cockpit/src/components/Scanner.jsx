import { useEffect, useMemo, useState } from 'react'
import { fetchMarkets } from '../lib/bybit.js'
import { classifyZone, sizePosition, fmtUSD, fmtPct, fmtNum, fmtCompactUSD, ZONES } from '../lib/risk.js'
import { Card, ZonePill } from './ui.jsx'

const FILTERS = [
  { key: 'all', label: 'ALL' },
  { key: 'tradeable', label: 'TRADEABLE' },
  ...ZONES.map((z) => ({ key: z.key, label: z.label })),
]

export default function Scanner({ settings, equity }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [degraded, setDegraded] = useState(false)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [filter, setFilter] = useState('tradeable')
  const [query, setQuery] = useState('')

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      const { rows: data, degraded: deg } = await fetchMarkets({ limit: 300 })
      setRows(data)
      setDegraded(deg)
      setUpdatedAt(new Date())
    } catch (e) {
      setError(e.message || 'Failed to load markets')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const enriched = useMemo(() => {
    return rows.map((r) => {
      const zone = classifyZone(r.rangePct)
      const sizing = sizePosition({
        rangePct: r.rangePct,
        settings,
        equity,
        sizeFactor: zone?.sizeFactor ?? 0,
      })
      return { ...r, zone, sizing }
    })
  }, [rows, settings, equity])

  const filtered = useMemo(() => {
    let list = enriched
    if (filter === 'tradeable') list = list.filter((r) => r.zone?.tradeable)
    else if (filter !== 'all') list = list.filter((r) => r.zone?.key === filter)
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      list = list.filter(
        (r) => r.symbol.toLowerCase().includes(q) || r.name.toLowerCase().includes(q),
      )
    }
    return [...list].sort((a, b) => b.rangePct - a.rangePct)
  }, [enriched, filter, query])

  return (
    <div className="space-y-2">
      <Card
        title="SCANNER · BYBIT CRYPTO PERPS · TOP 300 MKT CAP"
        right={
          <div className="flex items-center gap-3">
            <span className="text-[10px] uppercase text-bbg-dim">
              {filtered.length} SYM
            </span>
            {updatedAt && (
              <span className="tnum text-[10px] text-bbg-dim">
                {updatedAt.toISOString().slice(11, 19)}Z
              </span>
            )}
            <button
              onClick={refresh}
              disabled={loading}
              className="border border-bbg-amber bg-bbg-amber px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-black hover:bg-bbg-amber2 disabled:opacity-40"
            >
              {loading ? 'LOADING' : 'REFRESH'}
            </button>
          </div>
        }
      >
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="FILTER SYMBOL…"
            className="w-44 rounded-none border border-bbg-border bg-black px-2 py-1 text-xs uppercase text-bbg-gold caret-bbg-amber outline-none placeholder:text-bbg-dim focus:border-bbg-amber"
          />
          <div className="flex flex-wrap gap-px">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${
                  filter === f.key
                    ? 'bg-bbg-amber text-black'
                    : 'border border-bbg-border bg-black text-bbg-amber2 hover:bg-bbg-head'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-2 border border-bbg-red bg-bbg-red/10 px-2 py-1 text-xs text-bbg-red">
            ▲ {error}
          </div>
        )}
        {degraded && !error && (
          <div className="mb-2 border border-bbg-amber bg-bbg-amber/10 px-2 py-1 text-[11px] text-bbg-amber">
            ▲ MKT-CAP DATA UNAVAILABLE (COINGECKO RATE-LIMITED) — RANKED BY 24H TURNOVER · MICRO-CAP FILTER OFF
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-xs">
            <thead>
              <tr className="border-y border-bbg-border bg-bbg-head text-left text-[10px] uppercase tracking-wider text-bbg-amber">
                <th className="px-2 py-1 font-bold">Symbol</th>
                <th className="px-2 py-1 text-right font-bold">Mkt Cap</th>
                <th className="px-2 py-1 text-right font-bold">Last</th>
                <th className="px-2 py-1 text-right font-bold">24h%</th>
                <th className="px-2 py-1 text-right font-bold">Range%</th>
                <th className="px-2 py-1 font-bold">Zone</th>
                <th className="px-2 py-1 text-right font-bold">Stop%</th>
                <th className="px-2 py-1 text-right font-bold">Notional</th>
                <th className="px-2 py-1 text-right font-bold">Lev</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                <tr
                  key={r.id}
                  className={`border-b border-bbg-grid hover:bg-bbg-head ${
                    i % 2 ? 'bg-black' : 'bg-bbg-panel'
                  }`}
                >
                  <td className="px-2 py-1">
                    <span className="font-bold text-bbg-gold">{r.symbol}</span>
                    <span className="ml-1.5 text-[10px] text-bbg-dim">
                      {r.name?.slice(0, 16)}
                    </span>
                  </td>
                  <td className="tnum px-2 py-1 text-right text-bbg-text">
                    {fmtCompactUSD(r.marketCap)}
                    {r.mcapRank && (
                      <span className="ml-1 text-[10px] text-bbg-dim">#{r.mcapRank}</span>
                    )}
                  </td>
                  <td className="tnum px-2 py-1 text-right text-bbg-text">
                    {fmtUSD(r.price, r.price < 1 ? 4 : 2)}
                  </td>
                  <td
                    className={`tnum px-2 py-1 text-right ${
                      r.change24hPct >= 0 ? 'text-bbg-green' : 'text-bbg-red'
                    }`}
                  >
                    {r.change24hPct >= 0 ? '+' : ''}
                    {fmtNum(r.change24hPct, 1)}
                  </td>
                  <td className="tnum px-2 py-1 text-right font-bold text-bbg-text">
                    {fmtPct(r.rangePct, 1)}
                  </td>
                  <td className="px-2 py-1">
                    <ZonePill zone={r.zone} />
                  </td>
                  <td className="tnum px-2 py-1 text-right text-bbg-dim">
                    {r.zone?.tradeable ? fmtPct(r.sizing.stopDistancePct, 1) : '—'}
                  </td>
                  <td className="tnum px-2 py-1 text-right text-bbg-text">
                    {r.zone?.tradeable ? fmtUSD(r.sizing.notional, 0) : '—'}
                  </td>
                  <td className="tnum px-2 py-1 text-right text-bbg-amber2">
                    {r.zone?.tradeable ? `${fmtNum(r.sizing.leverage, 1)}×` : '—'}
                  </td>
                </tr>
              ))}
              {!filtered.length && !loading && (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-bbg-dim">
                    NO SYMBOLS MATCH FILTER
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[10px] uppercase tracking-wide text-bbg-dim">
          RISK {settings.riskPerTradePct}% OF {fmtUSD(equity, 0)} · STOP = RANGE% ×{' '}
          {settings.stopMultiplier} · ELEV ZONE AUTO-SIZES 50% · SRC: BYBIT + COINGECKO · NOT ADVICE
        </p>
      </Card>
    </div>
  )
}
