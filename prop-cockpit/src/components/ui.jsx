// Bloomberg-terminal styled primitives shared across tabs.
// Sharp corners, 1px borders, amber header bars, monospace.

export function Card({ title, children, className = '', right }) {
  return (
    <div className={`border border-bbg-border bg-bbg-panel ${className}`}>
      {(title || right) && (
        <div className="flex items-center justify-between border-b border-bbg-border bg-bbg-head px-2.5 py-1.5">
          {title && (
            <h3 className="text-[11px] font-bold uppercase tracking-wider text-bbg-amber">
              {title}
            </h3>
          )}
          {right}
        </div>
      )}
      <div className="p-2.5">{children}</div>
    </div>
  )
}

export function Stat({ label, value, sub, tone = 'default' }) {
  const toneClass = {
    default: 'text-bbg-text',
    good: 'text-bbg-green',
    bad: 'text-bbg-red',
    warn: 'text-bbg-amber',
  }[tone]
  return (
    <div className="border border-bbg-grid bg-black px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-bbg-dim">{label}</div>
      <div className={`tnum text-lg font-semibold leading-tight ${toneClass}`}>{value}</div>
      {sub && <div className="tnum text-[11px] text-bbg-dim">{sub}</div>}
    </div>
  )
}

export function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-bbg-amber2">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[10px] text-bbg-dim">{hint}</span>}
    </label>
  )
}

export function NumberInput({ value, onChange, step = 'any', min, suffix, ...rest }) {
  return (
    <div className="relative">
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        onChange={(e) => onChange(e.target.value)}
        className="tnum w-full rounded-none border border-bbg-border bg-black px-2 py-1.5 text-sm text-bbg-gold caret-bbg-amber outline-none focus:border-bbg-amber"
        {...rest}
      />
      {suffix && (
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[10px] uppercase text-bbg-dim">
          {suffix}
        </span>
      )}
    </div>
  )
}

export function TextInput({ value, onChange, className = '', ...rest }) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`w-full rounded-none border border-bbg-border bg-black px-2 py-1.5 text-sm text-bbg-gold caret-bbg-amber outline-none focus:border-bbg-amber ${className}`}
      {...rest}
    />
  )
}

export function ZonePill({ zone }) {
  if (!zone) return <span className="text-bbg-dim">—</span>
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider"
      style={{ color: zone.color, border: `1px solid ${zone.color}55`, background: zone.color + '14' }}
    >
      {zone.label}
    </span>
  )
}
