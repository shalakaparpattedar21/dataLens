/** Dependency-free radar chart. axes: [{label, value 0..100}]. Needs at least 3 axes. */
export default function Radar({ axes, size = 320, title = 'Radar chart' }) {
  const n = axes.length
  if (n < 3) return <p className="text-sm text-slate-400">At least three scored dimensions are needed for a radar chart.</p>
  const c = size / 2, R = size / 2 - 52
  const pt = (i, v) => { const a = -Math.PI / 2 + (2 * Math.PI * i) / n; return [c + (R * v / 100) * Math.cos(a), c + (R * v / 100) * Math.sin(a)] }
  const poly = axes.map((a, i) => pt(i, Math.max(0, Math.min(100, a.value))).join(',')).join(' ')
  const desc = axes.map((a) => `${a.label} ${Math.round(a.value)}`).join(', ')
  return <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${title}: ${desc}`} className="mx-auto block h-auto w-full max-w-[360px]">
    {[25, 50, 75, 100].map((r) => <polygon key={r} points={axes.map((_, i) => pt(i, r).join(',')).join(' ')} fill="none" stroke="var(--line)" />)}
    {axes.map((_, i) => <line key={i} x1={c} y1={c} x2={pt(i, 100)[0]} y2={pt(i, 100)[1]} stroke="var(--line)" />)}
    <polygon points={poly} fill="var(--chart-1)" fillOpacity=".18" stroke="var(--chart-1)" strokeWidth="2" />
    {axes.map((a, i) => { const [x, y] = pt(i, Math.max(0, Math.min(100, a.value))); const [lx, ly] = pt(i, 122)
      return <g key={a.label}><circle cx={x} cy={y} r="3.5" fill="var(--chart-1)"><title>{a.label}: {Math.round(a.value)}</title></circle>
        <text x={lx} y={ly} textAnchor={lx < c - 4 ? 'end' : lx > c + 4 ? 'start' : 'middle'} dominantBaseline="middle" className="chart-text capitalize">{a.label} {Math.round(a.value)}</text></g> })}
  </svg>
}
