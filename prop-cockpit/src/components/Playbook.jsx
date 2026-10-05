import { useMemo, useState } from 'react'
import { byPlaybook } from '../lib/reports.js'
import { deriveTrade } from '../lib/journal.js'
import { fmtUSD, fmtPct, fmtNum } from '../lib/risk.js'
import { Card, Field, TextInput, Stat } from './ui.jsx'

export default function Playbook({ playbooks, savePlaybook, removePlaybook, trades }) {
  const [editing, setEditing] = useState(null) // playbook being edited (or {new})

  const perf = useMemo(() => {
    const rows = byPlaybook(trades)
    const map = new Map(rows.map((r) => [r.key, r]))
    // avg R per playbook
    const rByPb = new Map()
    for (const t of trades) {
      const r = deriveTrade(t).rMultiple
      if (r == null) continue
      const k = t.playbook || t.setup || 'Unassigned'
      const cur = rByPb.get(k) || { sum: 0, n: 0 }
      cur.sum += r; cur.n += 1; rByPb.set(k, cur)
    }
    return { map, rByPb }
  }, [trades])

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wider text-bbg-dim">
          {playbooks.length} PLAYBOOKS · TRACK WHICH STRATEGIES MAKE MONEY
        </span>
        <button onClick={() => setEditing({ name: '', description: '', rules: [] })}
          className="border border-bbg-amber bg-bbg-amber px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-black hover:bg-bbg-amber2">
          + NEW PLAYBOOK
        </button>
      </div>

      {editing && (
        <PlaybookForm
          pb={editing}
          onCancel={() => setEditing(null)}
          onSave={async (pb) => { await savePlaybook(pb); setEditing(null) }}
        />
      )}

      <div className="grid gap-2 lg:grid-cols-2">
        {playbooks.map((pb) => {
          const p = perf.map.get(pb.name)
          const r = perf.rByPb.get(pb.name)
          const avgR = r && r.n ? r.sum / r.n : null
          return (
            <Card key={pb.id} title={pb.name}
              right={
                <div className="flex gap-2">
                  <button onClick={() => setEditing(pb)} className="text-[10px] uppercase text-bbg-dim hover:text-bbg-amber">EDIT</button>
                  <button onClick={() => { if (confirm(`Delete playbook "${pb.name}"?`)) removePlaybook(pb.id) }}
                    className="text-[10px] uppercase text-bbg-dim hover:text-bbg-red">DEL</button>
                </div>
              }>
              {pb.description && <p className="mb-2 text-[11px] text-bbg-text">{pb.description}</p>}

              <div className="mb-2 grid grid-cols-4 gap-1.5">
                <Stat label="Trades" value={p?.count || 0} />
                <Stat label="Win%" value={fmtPct(p?.winRate || 0, 0)} />
                <Stat label="Net P&L" value={fmtUSD(p?.pnl || 0, 0)} tone={(p?.pnl || 0) >= 0 ? 'good' : 'bad'} />
                <Stat label="Avg R" value={avgR != null ? `${fmtNum(avgR, 2)}R` : '—'} tone={(avgR || 0) >= 0 ? 'good' : 'bad'} />
              </div>

              {pb.rules?.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-bbg-amber2">Rules / checklist</div>
                  <ul className="space-y-0.5">
                    {pb.rules.map((rule, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-[11px] text-bbg-text">
                        <span className="text-bbg-green">☑</span> {rule}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          )
        })}
      </div>
    </div>
  )
}

function PlaybookForm({ pb, onCancel, onSave }) {
  const [name, setName] = useState(pb.name || '')
  const [description, setDescription] = useState(pb.description || '')
  const [rules, setRules] = useState(pb.rules || [])
  const [ruleInput, setRuleInput] = useState('')

  function addRule() {
    const r = ruleInput.trim()
    if (r) { setRules((x) => [...x, r]); setRuleInput('') }
  }

  return (
    <Card title={pb.id ? `EDIT · ${pb.name}` : 'NEW PLAYBOOK'}>
      <div className="space-y-2.5">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Name"><TextInput value={name} onChange={setName} placeholder="e.g. Opening range breakout" /></Field>
          <Field label="Description"><TextInput value={description} onChange={setDescription} placeholder="One-line thesis" /></Field>
        </div>
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-bbg-amber2">Rules / checklist</div>
          <div className="mb-1.5 flex gap-1.5">
            <TextInput value={ruleInput} onChange={setRuleInput} placeholder="Add a rule and press +"
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addRule() } }} />
            <button type="button" onClick={addRule}
              className="shrink-0 border border-bbg-border bg-black px-3 text-bbg-amber2 hover:bg-bbg-head">+</button>
          </div>
          <ul className="space-y-0.5">
            {rules.map((r, i) => (
              <li key={i} className="flex items-center justify-between border-b border-bbg-grid py-0.5 text-[11px] text-bbg-text">
                <span>☑ {r}</span>
                <button type="button" onClick={() => setRules((x) => x.filter((_, j) => j !== i))}
                  className="text-bbg-dim hover:text-bbg-red">✕</button>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={() => name.trim() && onSave({ ...pb, name: name.trim(), description: description.trim(), rules })}
            className="border border-bbg-amber bg-bbg-amber px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-black hover:bg-bbg-amber2">
            SAVE
          </button>
          <button onClick={onCancel}
            className="border border-bbg-border bg-black px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-bbg-amber2 hover:bg-bbg-head">
            CANCEL
          </button>
        </div>
      </div>
    </Card>
  )
}
