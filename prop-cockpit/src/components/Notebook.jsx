import { useEffect, useMemo, useState } from 'react'
import { dailyPnl, todayKey } from '../lib/journal.js'
import { fmtUSD } from '../lib/risk.js'
import { Card } from './ui.jsx'

const SECTIONS = [
  { key: 'plan', label: 'Pre-market plan', placeholder: 'Bias, key levels, what would make you trade / stand aside…' },
  { key: 'review', label: 'Post-session review', placeholder: 'How did the session actually go vs the plan?' },
  { key: 'good', label: 'What went well', placeholder: 'Good decisions, disciplined execution…' },
  { key: 'mistakes', label: 'Mistakes', placeholder: 'Rule breaks, FOMO, oversizing, revenge trades…' },
  { key: 'lessons', label: 'Lessons / adjustments', placeholder: 'What to do differently next session…' },
]

function shiftDay(day, delta) {
  const d = new Date(day + 'T00:00:00')
  d.setDate(d.getDate() + delta)
  return todayKey(d)
}

export default function Notebook({ entries, saveEntry, trades, selectedDay, setSelectedDay }) {
  const day = selectedDay || todayKey()
  const stored = entries[day]

  const [draft, setDraft] = useState(() => stored || { day })

  // Reload draft when the day (or its stored entry) changes.
  useEffect(() => {
    setDraft(entries[day] || { day })
  }, [day, entries])

  const daySummary = useMemo(() => dailyPnl(trades).get(day), [trades, day])

  function setSection(key, value) {
    setDraft((d) => ({ ...d, [key]: value }))
  }
  function persist() {
    saveEntry({ ...draft, day, updatedAt: new Date().toISOString() })
  }

  return (
    <div className="space-y-2">
      <Card
        title={`NOTEBOOK · ${day}`}
        right={
          <div className="flex items-center gap-1">
            <button onClick={() => setSelectedDay(shiftDay(day, -1))}
              className="border border-bbg-border bg-black px-2 py-0.5 text-[11px] text-bbg-amber2 hover:bg-bbg-head">◀</button>
            <input type="date" value={day} onChange={(e) => setSelectedDay(e.target.value)}
              className="rounded-none border border-bbg-border bg-black px-1.5 py-0.5 text-[11px] text-bbg-gold outline-none focus:border-bbg-amber" />
            <button onClick={() => setSelectedDay(todayKey())}
              className="border border-bbg-border bg-black px-2 py-0.5 text-[10px] uppercase text-bbg-amber2 hover:bg-bbg-head">TODAY</button>
            <button onClick={() => setSelectedDay(shiftDay(day, 1))}
              className="border border-bbg-border bg-black px-2 py-0.5 text-[11px] text-bbg-amber2 hover:bg-bbg-head">▶</button>
          </div>
        }
      >
        {/* Day P&L summary */}
        <div className="mb-2 flex flex-wrap gap-4 border-b border-bbg-grid pb-2 text-[11px] uppercase">
          {daySummary ? (
            <>
              <span className="text-bbg-dim">NET <span className={`tnum font-bold ${daySummary.pnl >= 0 ? 'text-bbg-green' : 'text-bbg-red'}`}>{daySummary.pnl >= 0 ? '+' : ''}{fmtUSD(daySummary.pnl)}</span></span>
              <span className="text-bbg-dim">TRADES <span className="tnum font-bold text-bbg-text">{daySummary.count}</span></span>
              <span className="text-bbg-dim">W/L <span className="tnum font-bold text-bbg-text">{daySummary.wins}/{daySummary.losses}</span></span>
            </>
          ) : (
            <span className="text-bbg-dim">NO TRADES THIS DAY</span>
          )}
          {draft.updatedAt && <span className="ml-auto text-bbg-dim">SAVED {new Date(draft.updatedAt).toISOString().slice(11, 16)}</span>}
        </div>

        <div className="grid gap-2 lg:grid-cols-2">
          {SECTIONS.map((s) => (
            <div key={s.key}>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-bbg-amber2">{s.label}</label>
              <textarea
                value={draft[s.key] || ''}
                onChange={(e) => setSection(s.key, e.target.value)}
                onBlur={persist}
                rows={4}
                placeholder={s.placeholder}
                className="w-full rounded-none border border-bbg-border bg-black px-2 py-1.5 text-[13px] leading-snug text-bbg-gold outline-none placeholder:text-bbg-dim focus:border-bbg-amber"
              />
            </div>
          ))}
          <div className="lg:col-span-2">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-bbg-amber2">Free notes</label>
            <textarea
              value={draft.notes || ''}
              onChange={(e) => setSection('notes', e.target.value)}
              onBlur={persist}
              rows={3}
              placeholder="Anything else — market context, news, screenshots referenced in the journal…"
              className="w-full rounded-none border border-bbg-border bg-black px-2 py-1.5 text-[13px] leading-snug text-bbg-gold outline-none placeholder:text-bbg-dim focus:border-bbg-amber"
            />
          </div>
        </div>
        <div className="mt-2 flex justify-end">
          <button onClick={persist}
            className="border border-bbg-amber bg-bbg-amber px-4 py-1.5 text-[11px] font-bold uppercase tracking-wider text-black hover:bg-bbg-amber2">
            SAVE ENTRY
          </button>
        </div>
      </Card>
    </div>
  )
}
