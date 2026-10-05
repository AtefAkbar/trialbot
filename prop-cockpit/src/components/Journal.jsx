import { useMemo, useRef, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid,
} from 'recharts'
import { fmtUSD, fmtPct, fmtNum } from '../lib/risk.js'
import { deriveTrade, fmtHold } from '../lib/journal.js'
import { filterTrades } from '../lib/reports.js'
import { screenshotsFromFiles, screenshotsFromPaste } from '../lib/images.js'
import { Card, Field, NumberInput, TextInput, Stat } from './ui.jsx'
import FilterBar from './FilterBar.jsx'

function nowLocalInput() {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

export default function Journal({
  settings, trades, stats, playbooks, filter, setFilter,
  addTrade, updateTrade, removeTrade, clearAll,
}) {
  const [lightbox, setLightbox] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const target = settings.stageTarget

  // Sort newest-first for display (IndexedDB returns rows by id, not date).
  const shown = useMemo(
    () => filterTrades(trades, filter).sort((a, b) => new Date(b.date) - new Date(a.date)),
    [trades, filter],
  )

  return (
    <div className="space-y-2">
      {stats.softStopHit && (
        <div className="border border-bbg-amber bg-bbg-amber/10 px-3 py-2 text-xs uppercase tracking-wide text-bbg-amber">
          ■ SOFT DAILY STOP REACHED — {fmtUSD(stats.todayLoss)} LOST TODAY
          {stats.consecutiveLosses >= settings.maxConsecutiveLosses && ` / ${stats.consecutiveLosses} LOSSES IN A ROW`}
          . STEP AWAY — PROTECT THE {fmtUSD(stats.dailyRemaining)} BEFORE THE HARD LIMIT.
        </div>
      )}

      {/* Stat grid (full account) */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Equity" value={fmtUSD(stats.equity, 0)} sub={`${stats.netPnl >= 0 ? '+' : ''}${fmtUSD(stats.netPnl, 0)}`} tone={stats.netPnl >= 0 ? 'good' : 'bad'} />
        <Stat label="To target" value={fmtUSD(Math.max(0, stats.remainingToTarget), 0)} sub={`${fmtPct(stats.targetPct, 0)} of ${fmtUSD(target, 0)}`} tone={stats.remainingToTarget <= 0 ? 'good' : 'default'} />
        <Stat label="Win rate" value={fmtPct(stats.winRate, 0)} sub={`${stats.wins}W / ${stats.losses}L`} />
        <Stat label="Expectancy" value={fmtUSD(stats.expectancy, 1)} sub="per trade" tone={stats.expectancy >= 0 ? 'good' : 'bad'} />
        <Stat label="Profit factor" value={stats.profitFactor === Infinity ? '∞' : fmtNum(stats.profitFactor, 2)} />
        <Stat label="Max DD" value={fmtUSD(stats.maxDrawdown, 0)} sub={`of ${fmtUSD(stats.overallBuffer, 0)}`} tone={stats.maxDrawdown >= stats.overallBuffer * 0.7 ? 'warn' : 'default'} />
      </div>

      {/* Equity curve */}
      <Card title="EQUITY CURVE">
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={stats.equityCurve} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
              <CartesianGrid stroke="#1c1c1c" strokeDasharray="2 2" />
              <XAxis dataKey="i" tick={{ fill: '#7d7d7d', fontSize: 10 }} stroke="#2a2a2a" />
              <YAxis domain={['auto', 'auto']} tick={{ fill: '#7d7d7d', fontSize: 10 }} stroke="#2a2a2a" tickFormatter={(v) => `${fmtNum(v, 0)}`} />
              <Tooltip contentStyle={{ background: '#000', border: '1px solid #ff9800', borderRadius: 0, fontSize: 11, fontFamily: 'monospace' }}
                itemStyle={{ color: '#ffcc33' }} labelStyle={{ color: '#ff9800' }}
                formatter={(v) => [fmtUSD(v, 2), 'EQ']} labelFormatter={(i) => (i === 0 ? 'START' : `TRADE ${i}`)} />
              <ReferenceLine y={settings.startingBalance} stroke="#7d7d7d" strokeDasharray="3 3" />
              <ReferenceLine y={settings.startingBalance + target} stroke="#00d15f" strokeDasharray="3 3" label={{ value: 'TGT', fill: '#00d15f', fontSize: 9, position: 'insideTopRight' }} />
              <ReferenceLine y={stats.drawdownFloor} stroke="#ff3b30" strokeDasharray="3 3" label={{ value: 'DD FLOOR', fill: '#ff3b30', fontSize: 9, position: 'insideBottomRight' }} />
              <Line type="stepAfter" dataKey="equity" stroke="#ff9800" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <NewTradeForm addTrade={addTrade} playbooks={playbooks} onShot={setLightbox} />

      <FilterBar trades={trades} filter={filter} setFilter={setFilter} />

      <Card
        title={`BLOTTER · ${shown.length}${shown.length !== trades.length ? ` / ${trades.length}` : ''} TRADES`}
        right={trades.length > 0 && (
          <button onClick={() => { if (confirm('Clear ALL trades? This cannot be undone.')) clearAll() }}
            className="text-[10px] uppercase tracking-wider text-bbg-dim hover:text-bbg-red">CLEAR ALL</button>
        )}
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-xs">
            <thead>
              <tr className="border-y border-bbg-border bg-bbg-head text-left text-[10px] uppercase tracking-wider text-bbg-amber">
                <th className="px-2 py-1 font-bold" />
                <th className="px-2 py-1 font-bold">Date/Time</th>
                <th className="px-2 py-1 font-bold">Symbol</th>
                <th className="px-2 py-1 font-bold">Dir</th>
                <th className="px-2 py-1 font-bold">Playbook</th>
                <th className="px-2 py-1 text-right font-bold">R</th>
                <th className="px-2 py-1 text-right font-bold">P&L</th>
                <th className="px-2 py-1 text-center font-bold">SS</th>
                <th className="px-2 py-1" />
              </tr>
            </thead>
            <tbody>
              {shown.map((t, i) => (
                <TradeRow key={t.id} t={t} zebra={i % 2}
                  open={expanded === t.id}
                  onToggle={() => setExpanded(expanded === t.id ? null : t.id)}
                  onShot={setLightbox} onRemove={() => removeTrade(t.id)} onUpdate={updateTrade} />
              ))}
              {!shown.length && (
                <tr><td colSpan={9} className="py-6 text-center uppercase text-bbg-dim">
                  {trades.length ? 'No trades match filter' : 'No trades logged'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {lightbox && <Lightbox src={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  )
}

function DL({ label, value, tone = 'default' }) {
  const c = { default: 'text-bbg-text', good: 'text-bbg-green', bad: 'text-bbg-red' }[tone]
  return (
    <div className="flex justify-between border-b border-bbg-grid pb-0.5">
      <span className="text-bbg-dim">{label}</span>
      <span className={`tnum font-bold ${c}`}>{value}</span>
    </div>
  )
}

// ---- New trade form ----
function emptyForm(playbooks) {
  return {
    symbol: '', direction: 'long', playbook: playbooks[0]?.name || 'Other',
    entry: '', stop: '', exit: '', size: '', fees: '', pnl: '', rating: 3,
    entryTime: nowLocalInput(), exitTime: '', notes: '',
  }
}

function NewTradeForm({ addTrade, playbooks, onShot }) {
  const [f, setF] = useState(() => emptyForm(playbooks))
  const [shots, setShots] = useState([])
  const [tags, setTags] = useState([])
  const [tagInput, setTagInput] = useState('')
  const [drag, setDrag] = useState(false)
  const fileRef = useRef(null)
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }))

  const derived = useMemo(() => deriveTrade({
    ...f,
    entryTime: f.entryTime ? new Date(f.entryTime).toISOString() : null,
    exitTime: f.exitTime ? new Date(f.exitTime).toISOString() : null,
  }), [f])

  async function onPaste(e) {
    const added = await screenshotsFromPaste(e)
    if (added.length) { e.preventDefault(); setShots((s) => [...s, ...added]) }
  }
  async function onFiles(list) {
    const added = await screenshotsFromFiles(list)
    if (added.length) setShots((s) => [...s, ...added])
  }
  function addTag() {
    const t = tagInput.trim().replace(/,$/, '')
    if (t && !tags.includes(t)) setTags((x) => [...x, t])
    setTagInput('')
  }

  function submit(e) {
    e.preventDefault()
    let pnl = f.pnl === '' ? derived.pnlSuggested : Number(f.pnl)
    if (!f.symbol.trim() || pnl == null || Number.isNaN(pnl)) return
    addTrade({
      date: new Date().toISOString(),
      entryTime: f.entryTime ? new Date(f.entryTime).toISOString() : null,
      exitTime: f.exitTime ? new Date(f.exitTime).toISOString() : null,
      symbol: f.symbol.trim().toUpperCase(),
      direction: f.direction,
      playbook: f.playbook,
      entry: f.entry === '' ? null : Number(f.entry),
      stop: f.stop === '' ? null : Number(f.stop),
      exit: f.exit === '' ? null : Number(f.exit),
      size: f.size === '' ? null : Number(f.size),
      fees: f.fees === '' ? null : Number(f.fees),
      pnl,
      rMultiple: derived.rMultiple,
      rating: f.rating,
      tags,
      notes: f.notes.trim(),
      screenshots: shots,
    })
    setF(emptyForm(playbooks))
    setShots([])
    setTags([])
  }

  return (
    <Card title="NEW TRADE — RECORD EVERYTHING">
      <form onSubmit={submit} onPaste={onPaste} className="space-y-2.5">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Symbol"><TextInput value={f.symbol} onChange={set('symbol')} placeholder="BTC" className="uppercase" /></Field>
          <Field label="Direction">
            <div className="flex gap-px">
              {['long', 'short'].map((d) => (
                <button key={d} type="button" onClick={() => set('direction')(d)}
                  className={`flex-1 py-1.5 text-[11px] font-bold uppercase ${f.direction === d ? (d === 'long' ? 'bg-bbg-green text-black' : 'bg-bbg-red text-black') : 'border border-bbg-border bg-black text-bbg-amber2'}`}>{d}</button>
              ))}
            </div>
          </Field>
          <Field label="Playbook / setup">
            <select value={f.playbook} onChange={(e) => set('playbook')(e.target.value)}
              className="w-full rounded-none border border-bbg-border bg-black px-2 py-1.5 text-sm text-bbg-gold outline-none focus:border-bbg-amber">
              {playbooks.map((p) => <option key={p.id} value={p.name}>{p.name}</option>)}
              <option value="Other">Other</option>
            </select>
          </Field>
          <Field label={`Rating · ${f.rating}/5`}>
            <input type="range" min="1" max="5" value={f.rating} onChange={(e) => set('rating')(Number(e.target.value))} className="mt-2 w-full accent-bbg-amber" />
          </Field>
        </div>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Entry time">
            <input type="datetime-local" value={f.entryTime} onChange={(e) => set('entryTime')(e.target.value)}
              className="tnum w-full rounded-none border border-bbg-border bg-black px-2 py-1.5 text-xs text-bbg-gold outline-none focus:border-bbg-amber" />
          </Field>
          <Field label="Exit time">
            <input type="datetime-local" value={f.exitTime} onChange={(e) => set('exitTime')(e.target.value)}
              className="tnum w-full rounded-none border border-bbg-border bg-black px-2 py-1.5 text-xs text-bbg-gold outline-none focus:border-bbg-amber" />
          </Field>
          <div className="lg:col-span-2">
            <Field label="Tags">
              <div className="flex flex-wrap items-center gap-1 border border-bbg-border bg-black px-1.5 py-1">
                {tags.map((t) => (
                  <span key={t} className="flex items-center gap-1 bg-bbg-head px-1.5 py-0.5 text-[10px] uppercase text-bbg-amber2">
                    {t}<button type="button" onClick={() => setTags((x) => x.filter((y) => y !== t))} className="text-bbg-dim hover:text-bbg-red">✕</button>
                  </span>
                ))}
                <input value={tagInput} onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag() } }}
                  onBlur={addTag} placeholder="add tag + enter"
                  className="min-w-[100px] flex-1 bg-transparent text-xs text-bbg-gold outline-none placeholder:text-bbg-dim" />
              </div>
            </Field>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <Field label="Entry"><NumberInput value={f.entry} onChange={set('entry')} /></Field>
          <Field label="Stop"><NumberInput value={f.stop} onChange={set('stop')} /></Field>
          <Field label="Exit"><NumberInput value={f.exit} onChange={set('exit')} /></Field>
          <Field label="Size (units)"><NumberInput value={f.size} onChange={set('size')} /></Field>
          <Field label="Fees"><NumberInput value={f.fees} onChange={set('fees')} /></Field>
          <Field label="Net P&L" hint={f.pnl === '' && derived.pnlSuggested != null ? `auto: ${fmtUSD(derived.pnlSuggested)}` : 'required'}>
            <NumberInput value={f.pnl} onChange={set('pnl')} suffix="USD" />
          </Field>
        </div>

        <div className="flex flex-wrap gap-3 border-y border-bbg-grid py-1.5 text-[11px] uppercase text-bbg-dim">
          <span>R-MULT: <span className="tnum text-bbg-amber2">{derived.rMultiple != null ? `${fmtNum(derived.rMultiple, 2)}R` : '—'}</span></span>
          <span>STOP DIST: <span className="tnum text-bbg-amber2">{derived.stopDistPct != null ? fmtPct(derived.stopDistPct, 2) : '—'}</span></span>
          <span>HOLD: <span className="tnum text-bbg-amber2">{fmtHold(derived.holdMs)}</span></span>
        </div>

        {/* Screenshots */}
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-bbg-amber2">Screenshots</span>
            <span className="text-[10px] text-bbg-dim">PASTE (⌘V) · DROP · OR CLICK</span>
          </div>
          <div onClick={() => fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files) }}
            className={`flex min-h-[64px] cursor-pointer flex-wrap items-center gap-2 border border-dashed p-2 ${drag ? 'border-bbg-amber bg-bbg-amber/10' : 'border-bbg-border bg-black'}`}>
            {shots.length === 0 && <span className="text-[11px] uppercase text-bbg-dim">+ Attach chart screenshots</span>}
            {shots.map((s) => (
              <div key={s.id} className="group relative">
                <img src={s.dataUrl} alt={s.name} onClick={(e) => { e.stopPropagation(); onShot(s.dataUrl) }} className="h-14 w-20 border border-bbg-border object-cover" />
                <button type="button" onClick={(e) => { e.stopPropagation(); setShots((x) => x.filter((y) => y.id !== s.id)) }}
                  className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center border border-bbg-border bg-black text-[10px] text-bbg-red">✕</button>
              </div>
            ))}
          </div>
          <input ref={fileRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => { onFiles(e.target.files); e.target.value = '' }} />
        </div>

        <Field label="Notes">
          <textarea value={f.notes} onChange={(e) => set('notes')(e.target.value)} rows={2} placeholder="Thesis, execution, mistakes, lessons…"
            className="w-full rounded-none border border-bbg-border bg-black px-2 py-1.5 text-sm text-bbg-gold outline-none focus:border-bbg-amber" />
        </Field>

        <button type="submit" className="w-full border border-bbg-amber bg-bbg-amber py-1.5 text-[11px] font-bold uppercase tracking-wider text-black hover:bg-bbg-amber2">
          + ADD TRADE TO JOURNAL
        </button>
      </form>
    </Card>
  )
}

// ---- Trade row ----
function TradeRow({ t, zebra, open, onToggle, onShot, onRemove, onUpdate }) {
  const d = deriveTrade(t)
  const addRef = useRef(null)
  const shots = t.screenshots || []

  async function addShots(list) {
    const added = await screenshotsFromFiles(list)
    if (added.length) onUpdate({ ...t, screenshots: [...shots, ...added] })
  }

  return (
    <>
      <tr className={`border-b border-bbg-grid ${zebra ? 'bg-black' : 'bg-bbg-panel'} ${open ? 'bg-bbg-head' : ''} cursor-pointer hover:bg-bbg-head`} onClick={onToggle}>
        <td className="px-2 py-1 text-bbg-amber">{open ? '▾' : '▸'}</td>
        <td className="tnum px-2 py-1 text-bbg-dim">{new Date(t.date).toISOString().slice(2, 10)} {new Date(t.date).toISOString().slice(11, 16)}</td>
        <td className="px-2 py-1 font-bold text-bbg-gold">{t.symbol}</td>
        <td className={`px-2 py-1 uppercase ${t.direction === 'short' ? 'text-bbg-red' : 'text-bbg-green'}`}>{t.direction}</td>
        <td className="px-2 py-1 text-bbg-dim">{t.playbook || t.setup || '—'}</td>
        <td className={`tnum px-2 py-1 text-right ${d.rMultiple >= 0 ? 'text-bbg-green' : 'text-bbg-red'}`}>{d.rMultiple != null ? `${fmtNum(d.rMultiple, 1)}R` : '—'}</td>
        <td className={`tnum px-2 py-1 text-right font-bold ${t.pnl >= 0 ? 'text-bbg-green' : 'text-bbg-red'}`}>{t.pnl >= 0 ? '+' : ''}{fmtUSD(t.pnl)}</td>
        <td className="px-2 py-1 text-center text-bbg-dim">{shots.length ? `▣ ${shots.length}` : '—'}</td>
        <td className="px-2 py-1 text-right"><button onClick={(e) => { e.stopPropagation(); onRemove() }} className="text-bbg-dim hover:text-bbg-red" title="Delete">✕</button></td>
      </tr>
      {open && (
        <tr className="border-b border-bbg-border bg-black">
          <td colSpan={9} className="px-3 py-2.5">
            <div className="grid gap-3 lg:grid-cols-[1fr_1.4fr]">
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] uppercase sm:grid-cols-3">
                <DL label="Entry" value={t.entry != null ? fmtUSD(t.entry, 4) : '—'} />
                <DL label="Stop" value={t.stop != null ? fmtUSD(t.stop, 4) : '—'} />
                <DL label="Exit" value={t.exit != null ? fmtUSD(t.exit, 4) : '—'} />
                <DL label="Size" value={t.size != null ? fmtNum(t.size, 4) : '—'} />
                <DL label="Fees" value={t.fees != null ? fmtUSD(t.fees) : '—'} />
                <DL label="Stop dist" value={d.stopDistPct != null ? fmtPct(d.stopDistPct, 2) : '—'} />
                <DL label="R-multiple" value={d.rMultiple != null ? `${fmtNum(d.rMultiple, 2)}R` : '—'} tone={d.rMultiple >= 0 ? 'good' : 'bad'} />
                <DL label="Hold" value={fmtHold(d.holdMs)} />
                <DL label="Rating" value={t.rating ? `${'★'.repeat(t.rating)}${'☆'.repeat(5 - t.rating)}` : '—'} />
              </div>
              <div>
                {(t.tags || []).length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {t.tags.map((tag) => <span key={tag} className="bg-bbg-head px-1.5 py-0.5 text-[10px] uppercase text-bbg-amber2">{tag}</span>)}
                  </div>
                )}
                {t.notes && <div className="mb-2 border-l-2 border-bbg-amber bg-bbg-panel px-2 py-1 text-[11px] text-bbg-text">{t.notes}</div>}
                <div className="flex flex-wrap items-center gap-2">
                  {shots.map((s) => (
                    <img key={s.id} src={s.dataUrl} alt={s.name} onClick={() => onShot(s.dataUrl)} className="h-16 w-24 cursor-zoom-in border border-bbg-border object-cover hover:border-bbg-amber" />
                  ))}
                  <button onClick={() => addRef.current?.click()} className="flex h-16 w-24 items-center justify-center border border-dashed border-bbg-border text-[10px] uppercase text-bbg-dim hover:border-bbg-amber hover:text-bbg-amber2">+ SS</button>
                  <input ref={addRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => { addShots(e.target.files); e.target.value = '' }} />
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function Lightbox({ src, onClose }) {
  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-6">
      <img src={src} alt="" className="max-h-full max-w-full border border-bbg-amber object-contain" />
      <button onClick={onClose} className="absolute right-4 top-4 border border-bbg-border bg-black px-3 py-1 text-xs uppercase text-bbg-amber hover:bg-bbg-head">CLOSE ✕</button>
    </div>
  )
}
