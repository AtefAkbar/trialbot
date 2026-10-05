import { fmtUSD } from '../lib/risk.js'
import { Card, Field, NumberInput } from './ui.jsx'

export default function Settings({ settings, update, reset }) {
  const buffer = (settings.startingBalance * settings.maxDrawdownPct) / 100
  return (
    <Card
      title="ACCOUNT & RISK CONFIG"
      right={
        <button
          onClick={reset}
          className="text-[10px] uppercase tracking-wider text-bbg-dim hover:text-bbg-amber"
        >
          RESET DEFAULTS
        </button>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Starting balance" hint="Prop account size">
          <NumberInput
            value={settings.startingBalance}
            onChange={(v) => update({ startingBalance: Number(v) })}
            suffix="USD"
          />
        </Field>
        <Field label="Max overall drawdown" hint={`= ${fmtUSD(buffer, 0)} buffer`}>
          <NumberInput
            value={settings.maxDrawdownPct}
            onChange={(v) => update({ maxDrawdownPct: Number(v) })}
            suffix="%"
          />
        </Field>
        <Field label="Daily loss limit" hint="Hard floor per day">
          <NumberInput
            value={settings.dailyLossLimit}
            onChange={(v) => update({ dailyLossLimit: Number(v) })}
            suffix="USD"
          />
        </Field>
        <Field label="Stage 1 target">
          <NumberInput
            value={settings.stageTarget}
            onChange={(v) => update({ stageTarget: Number(v) })}
            suffix="USD"
          />
        </Field>
        <Field label="Risk per trade" hint="0.5–1.5% recommended">
          <NumberInput
            value={settings.riskPerTradePct}
            onChange={(v) => update({ riskPerTradePct: Number(v) })}
            suffix="%"
            step="0.1"
          />
        </Field>
        <Field label="Stop multiplier" hint="stop = range% × this">
          <NumberInput
            value={settings.stopMultiplier}
            onChange={(v) => update({ stopMultiplier: Number(v) })}
            suffix="×"
            step="0.1"
          />
        </Field>
        <Field label="Soft daily stop" hint="Self-imposed buffer">
          <NumberInput
            value={settings.softDailyLoss}
            onChange={(v) => update({ softDailyLoss: Number(v) })}
            suffix="USD"
          />
        </Field>
        <Field label="Max consecutive losses" hint="Then stop for the day">
          <NumberInput
            value={settings.maxConsecutiveLosses}
            onChange={(v) => update({ maxConsecutiveLosses: Number(v) })}
            step="1"
          />
        </Field>
      </div>
    </Card>
  )
}
