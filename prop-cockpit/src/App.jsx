import { useEffect, useMemo, useState } from 'react'
import { useSettings, useTrades, usePlaybooks, useNotebook } from './lib/hooks.js'
import { computeStats, todayKey } from './lib/journal.js'
import { fmtUSD } from './lib/risk.js'
import Scanner from './components/Scanner.jsx'
import PositionCalc from './components/PositionCalc.jsx'
import Journal from './components/Journal.jsx'
import Reports from './components/Reports.jsx'
import Calendar from './components/Calendar.jsx'
import Playbook from './components/Playbook.jsx'
import Notebook from './components/Notebook.jsx'
import Settings from './components/Settings.jsx'

const TABS = [
  { key: 'scanner', label: 'SCAN', fn: '1' },
  { key: 'calc', label: 'CALC', fn: '2' },
  { key: 'journal', label: 'JOURNAL', fn: '3' },
  { key: 'reports', label: 'REPORTS', fn: '4' },
  { key: 'calendar', label: 'CALENDAR', fn: '5' },
  { key: 'playbook', label: 'PLAYBOOK', fn: '6' },
  { key: 'notebook', label: 'NOTEBOOK', fn: '7' },
  { key: 'settings', label: 'CONFIG', fn: '8' },
]

const EMPTY_FILTER = { side: 'all', playbook: 'all', tag: 'all' }

export default function App() {
  const [tab, setTab] = useState('scanner')
  const { settings, update, reset } = useSettings()
  const { trades, addTrade, updateTrade, removeTrade, clearAll } = useTrades()
  const { playbooks, savePlaybook, removePlaybook } = usePlaybooks()
  const { entries, saveEntry } = useNotebook()
  const [clock, setClock] = useState('')
  const [filter, setFilter] = useState(EMPTY_FILTER)
  const [selectedDay, setSelectedDay] = useState(todayKey())

  // Account-level stats always run on the FULL trade set (guardrails).
  const stats = useMemo(() => computeStats(trades, settings), [trades, settings])
  const equity = stats.equity

  useEffect(() => {
    const tick = () => setClock(new Date().toISOString().slice(11, 19) + 'Z')
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return
      const t = TABS.find((x) => x.fn === e.key)
      if (t) setTab(t.key)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function openDay(day) {
    setSelectedDay(day)
    setTab('notebook')
  }

  return (
    <div className="min-h-screen bg-bbg-bg font-mono text-bbg-text">
      <header className="border-b-2 border-bbg-amber">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-3 py-1.5">
          <div className="flex items-center gap-3">
            <span className="text-sm font-bold tracking-widest text-bbg-amber">PROP·COCKPIT</span>
            <span className="hidden text-[11px] text-bbg-dim sm:inline">RISK TERMINAL <span className="text-bbg-amber2">&lt;GO&gt;</span></span>
          </div>
          <div className="flex items-center gap-4 text-[11px]">
            <span className="text-bbg-dim"><span className="text-bbg-cyan">{clock}</span></span>
            <span className="flex items-center gap-1.5 text-bbg-green"><span className="bbg-blink text-bbg-green">●</span> LIVE</span>
          </div>
        </div>

        <div className="flex items-stretch gap-px overflow-x-auto border-t border-bbg-border bg-bbg-border">
          {TABS.map((t) => {
            const active = tab === t.key
            return (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 whitespace-nowrap px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-colors ${active ? 'bg-bbg-amber text-black' : 'bg-black text-bbg-amber2 hover:bg-bbg-head'}`}>
                <span className={active ? 'text-black/60' : 'text-bbg-dim'}>F{t.fn}</span>{t.label}
              </button>
            )
          })}
          <div className="flex-1 bg-black" />
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-3 py-3">
        {tab === 'scanner' && <Scanner settings={settings} equity={equity} />}
        {tab === 'calc' && <PositionCalc settings={settings} equity={equity} stats={stats} />}
        {tab === 'journal' && (
          <Journal settings={settings} trades={trades} stats={stats} playbooks={playbooks}
            filter={filter} setFilter={setFilter}
            addTrade={addTrade} updateTrade={updateTrade} removeTrade={removeTrade} clearAll={clearAll} />
        )}
        {tab === 'reports' && <Reports trades={trades} settings={settings} filter={filter} setFilter={setFilter} />}
        {tab === 'calendar' && <Calendar trades={trades} filter={filter} setFilter={setFilter} onSelectDay={openDay} />}
        {tab === 'playbook' && <Playbook playbooks={playbooks} savePlaybook={savePlaybook} removePlaybook={removePlaybook} trades={trades} />}
        {tab === 'notebook' && <Notebook entries={entries} saveEntry={saveEntry} trades={trades} selectedDay={selectedDay} setSelectedDay={setSelectedDay} />}
        {tab === 'settings' && <Settings settings={settings} update={update} reset={reset} />}
      </main>

      <footer className="sticky bottom-0 border-t border-bbg-border bg-bbg-head">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 px-3 py-1 text-[11px]">
          <StatusItem label="EQ" value={fmtUSD(equity, 2)} tone={stats.netPnl >= 0 ? 'good' : 'bad'} />
          <StatusItem label="DAY" value={`${stats.todayPnl >= 0 ? '+' : ''}${fmtUSD(stats.todayPnl, 2)}`} tone={stats.todayPnl >= 0 ? 'good' : 'bad'} />
          <StatusItem label="DD·LEFT" value={fmtUSD(stats.overallDdRemaining, 2)} tone={stats.overallDdRemaining < stats.overallBuffer * 0.3 ? 'bad' : 'default'} />
          <StatusItem label="TGT" value={fmtUSD(Math.max(0, stats.remainingToTarget), 2)} />
          <div className="ml-auto flex items-center gap-4 text-bbg-dim">
            <span className="flex items-center gap-1"><span className="text-bbg-green">●</span> BYBIT</span>
            <span className="hidden md:inline">RISK TOOL · NOT ADVICE</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

function StatusItem({ label, value, tone = 'default' }) {
  const c = { default: 'text-bbg-text', good: 'text-bbg-green', bad: 'text-bbg-red' }[tone]
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-bbg-dim">{label}</span>
      <span className={`tnum font-semibold ${c}`}>{value}</span>
    </span>
  )
}
