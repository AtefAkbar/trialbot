import { allTags, hasActiveFilter } from '../lib/reports.js'
import { playbookOf } from '../lib/reports.js'

// Compact global filter bar. Reads/writes the shared filter object.
// `trades` is the FULL set (used to populate playbook/tag dropdowns).
export default function FilterBar({ trades, filter, setFilter }) {
  const set = (k) => (v) => setFilter((f) => ({ ...f, [k]: v }))
  const playbooks = [...new Set(trades.map(playbookOf))].sort()
  const tags = allTags(trades)
  const active = hasActiveFilter(filter)

  const selCls =
    'rounded-none border border-bbg-border bg-black px-1.5 py-1 text-[11px] text-bbg-gold outline-none focus:border-bbg-amber'

  return (
    <div className="flex flex-wrap items-center gap-1.5 border border-bbg-border bg-bbg-panel px-2 py-1.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-bbg-amber">Filter</span>

      <input type="date" value={filter.from || ''} onChange={(e) => set('from')(e.target.value)}
        className={selCls} title="From date" />
      <span className="text-bbg-dim">→</span>
      <input type="date" value={filter.to || ''} onChange={(e) => set('to')(e.target.value)}
        className={selCls} title="To date" />

      <input value={filter.symbol || ''} onChange={(e) => set('symbol')(e.target.value)}
        placeholder="SYMBOL" className={`${selCls} w-24 uppercase placeholder:text-bbg-dim`} />

      <select value={filter.side || 'all'} onChange={(e) => set('side')(e.target.value)} className={selCls}>
        <option value="all">ALL SIDES</option>
        <option value="long">LONG</option>
        <option value="short">SHORT</option>
      </select>

      <select value={filter.playbook || 'all'} onChange={(e) => set('playbook')(e.target.value)} className={selCls}>
        <option value="all">ALL PLAYBOOKS</option>
        {playbooks.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>

      <select value={filter.tag || 'all'} onChange={(e) => set('tag')(e.target.value)} className={selCls}>
        <option value="all">ALL TAGS</option>
        {tags.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>

      {active && (
        <button onClick={() => setFilter({ side: 'all', playbook: 'all', tag: 'all' })}
          className="border border-bbg-border bg-black px-2 py-1 text-[10px] uppercase tracking-wider text-bbg-amber2 hover:bg-bbg-head">
          CLEAR ✕
        </button>
      )}
    </div>
  )
}
