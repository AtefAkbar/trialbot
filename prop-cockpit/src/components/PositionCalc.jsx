import { useMemo, useState } from 'react'
import { calcFromStop, fmtUSD, fmtPct, fmtNum } from '../lib/risk.js'
import { Card, Field, NumberInput, Stat } from './ui.jsx'

export default function PositionCalc({ settings, equity, stats }) {
  const [direction, setDirection] = useState('long')
  const [entry, setEntry] = useState('')
  const [stop, setStop] = useState('')
  const [riskPct, setRiskPct] = useState(settings.riskPerTradePct)

  const risk = useMemo(() => (equity * Number(riskPct)) / 100, [equity, riskPct])

  const result = useMemo(() => {
    const e = Number(entry)
    const s = Number(stop)
    if (!e || !s || e === s) return null
    const dirOk = direction === 'long' ? s < e : s > e
    const r = calcFromStop({ entry: e, stop: s, riskDollars: risk, equity })
    return { ...r, dirOk }
  }, [entry, stop, risk, equity, direction])

  const dailyRemaining = stats?.dailyRemaining ?? settings.dailyLossLimit
  const overRisk = risk > dailyRemaining
  const softRemaining = settings.softDailyLoss - (stats?.todayLoss ?? 0)
  const overSoft = risk > softRemaining && softRemaining >= 0

  return (
    <div className="grid gap-2 lg:grid-cols-2">
      <Card title="POSITION CALCULATOR">
        <div className="space-y-2.5">
          <div className="flex gap-px">
            {['long', 'short'].map((d) => (
              <button
                key={d}
                onClick={() => setDirection(d)}
                className={`flex-1 py-1.5 text-[11px] font-bold uppercase tracking-wider ${
                  direction === d
                    ? d === 'long'
                      ? 'bg-bbg-green text-black'
                      : 'bg-bbg-red text-black'
                    : 'border border-bbg-border bg-black text-bbg-amber2 hover:bg-bbg-head'
                }`}
              >
                {d === 'long' ? 'LONG ▲' : 'SHORT ▼'}
              </button>
            ))}
          </div>

          <Field label="Entry price">
            <NumberInput value={entry} onChange={setEntry} suffix="USD" />
          </Field>
          <Field
            label="Stop-loss price"
            hint={direction === 'long' ? 'Below entry for a long.' : 'Above entry for a short.'}
          >
            <NumberInput value={stop} onChange={setStop} suffix="USD" />
          </Field>
          <Field label="Risk this trade" hint={`Equity: ${fmtUSD(equity, 0)}`}>
            <NumberInput value={riskPct} onChange={setRiskPct} suffix="%" step="0.1" min="0" />
          </Field>

          <div className="flex justify-between border border-bbg-grid bg-black px-2 py-1.5 text-xs">
            <span className="uppercase text-bbg-dim">Risk amount</span>
            <span className="tnum font-bold text-bbg-gold">{fmtUSD(risk)}</span>
          </div>
        </div>
      </Card>

      <div className="space-y-2">
        <Card title="RESULT">
          {result ? (
            <>
              {!result.dirOk && (
                <div className="mb-2 border border-bbg-amber bg-bbg-amber/10 px-2 py-1 text-[11px] uppercase text-bbg-amber">
                  ▲ Stop on wrong side of entry for a {direction}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <Stat label="Size (units)" value={fmtNum(result.units, 4)} />
                <Stat label="Notional" value={fmtUSD(result.notional, 0)} />
                <Stat label="Stop distance" value={fmtPct(result.stopDistancePct, 2)} />
                <Stat
                  label="Leverage"
                  value={`${fmtNum(result.leverage, 2)}×`}
                  tone={result.leverage > 10 ? 'warn' : 'default'}
                />
              </div>
            </>
          ) : (
            <p className="py-5 text-center text-xs uppercase text-bbg-dim">
              Enter entry + stop to size the trade
            </p>
          )}
        </Card>

        <Card title="DRAWDOWN BUDGET CHECK">
          <div className="space-y-1.5 text-xs">
            <BudgetRow
              label="Today's loss budget left"
              value={fmtUSD(dailyRemaining)}
              tone={dailyRemaining <= 0 ? 'bad' : 'default'}
            />
            <BudgetRow
              label="Soft stop remaining"
              value={fmtUSD(Math.max(0, softRemaining))}
              tone={softRemaining <= 0 ? 'warn' : 'default'}
            />
            {overRisk && (
              <div className="border border-bbg-red bg-bbg-red/10 px-2 py-1 text-[11px] uppercase text-bbg-red">
                ■ RISK {fmtUSD(risk)} EXCEEDS {fmtUSD(dailyRemaining)} DAILY BUDGET — DO NOT TAKE
              </div>
            )}
            {!overRisk && overSoft && (
              <div className="border border-bbg-amber bg-bbg-amber/10 px-2 py-1 text-[11px] uppercase text-bbg-amber">
                ▲ WOULD BREACH SOFT STOP ({fmtUSD(settings.softDailyLoss)}/DAY) — SIZE DOWN
              </div>
            )}
            {!overRisk && !overSoft && result && (
              <div className="border border-bbg-green bg-bbg-green/10 px-2 py-1 text-[11px] uppercase text-bbg-green">
                ✓ RISK FITS TODAY'S BUDGET
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}

function BudgetRow({ label, value, tone = 'default' }) {
  const c = { default: 'text-bbg-text', bad: 'text-bbg-red', warn: 'text-bbg-amber' }[tone]
  return (
    <div className="flex justify-between border-b border-bbg-grid pb-1">
      <span className="uppercase text-bbg-dim">{label}</span>
      <span className={`tnum font-bold ${c}`}>{value}</span>
    </div>
  )
}
