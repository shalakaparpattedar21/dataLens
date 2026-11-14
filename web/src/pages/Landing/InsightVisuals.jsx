import { useMemo, useState } from 'react'
import { gauss, rng } from '../../hooks/useMotion.js'

const Badge = () => <span className="rounded-full border border-slate-600 px-2 py-0.5 text-[11px] font-semibold tracking-wider text-slate-400">ILLUSTRATIVE</span>
const Panel = ({ tag, title, text, children }) => <section className="rounded-2xl border border-slate-700/70 bg-[#0d1530] p-5">
  <div className="flex items-center justify-between gap-2"><span className="text-xs font-bold tracking-[.18em] text-indigo-300">{tag}</span><Badge /></div>
  <h3 className="mt-2 text-[22px] text-white">{title}</h3><p className="mt-1 text-[14px] leading-snug text-slate-400">{text}</p><div className="mt-4">{children}</div></section>

const NAMES = ['duration', 'bytes_in', 'bytes_out', 'packets', 'port', 'rate', 'flags']
// Illustrative correlation matrix: two positive blocks and one negative pair.
const M = (() => { const n = NAMES.length, m = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => (i === j ? 1 : 0.04 * (((i * 7 + j * 3) % 5) - 2))))
  const set = (a, b, v) => { m[a][b] = v; m[b][a] = v }
  set(1, 2, 0.92); set(1, 3, 0.74); set(2, 3, 0.69); set(0, 5, -0.62); set(5, 6, 0.41); set(0, 4, 0.12); return m })()

function Heat() {
  const [h, setH] = useState(null)
  const color = (v) => v >= 0 ? `rgba(99,102,241,${0.08 + 0.92 * v})` : `rgba(251,191,36,${0.08 + 0.92 * -v})`
  return <div><svg viewBox="0 0 330 300" role="img" aria-label="Illustrative correlation heatmap with positive and negative relationships" className="block h-auto w-full">
    {M.map((row, i) => row.map((v, j) => <rect key={i + '-' + j} x={80 + j * 35} y={20 + i * 35} width="33" height="33" rx="3" fill={color(v)} stroke={h && h[0] === i && h[1] === j ? '#fff' : 'none'} onMouseEnter={() => setH([i, j])} onMouseLeave={() => setH(null)} />))}
    {NAMES.map((n, i) => <text key={n} x="74" y={42 + i * 35} textAnchor="end" className="fill-slate-400" fontSize="11.5">{n}</text>)}
    {NAMES.map((n, j) => <text key={n} transform={`translate(${98 + j * 35} 276) rotate(-40)`} className="fill-slate-400" fontSize="11.5">{n}</text>)}
  </svg><p className="mt-1 min-h-[20px] text-[13px] text-slate-300" role="status">{h ? `${NAMES[h[0]]} × ${NAMES[h[1]]}: r = ${M[h[0]][h[1]].toFixed(2)} (illustrative)` : 'Hover a cell. Indigo = positive, amber = negative.'}</p></div>
}

function Scatter() {
  const [hot, setHot] = useState(null)
  const pts = useMemo(() => { const r = rng(5); const a = []
    for (let i = 0; i < 360; i++) a.push({ x: 160 + gauss(r) * 55, y: 140 + gauss(r) * 38 + (0), out: false })
    for (let i = 0; i < 14; i++) { const ang = r() * 6.28; const d = 130 + r() * 40; a.push({ x: 160 + Math.cos(ang) * d * 1.2, y: 140 + Math.sin(ang) * d * .8, out: true, id: i }) }
    return a.filter((p) => p.x > 8 && p.x < 312 && p.y > 8 && p.y < 272) }, [])
  return <div><svg viewBox="0 0 320 280" role="img" aria-label="Illustrative scatter plot with normal observations and highlighted unusual observations" className="block h-auto w-full">
    <rect width="320" height="280" rx="8" fill="#0a1022" />
    {pts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={p.out ? 4.5 : 2} fill={p.out ? '#fbbf24' : '#7c8cf8'} opacity={p.out ? 1 : 0.55} onMouseEnter={() => p.out && setHot(p.id)} onMouseLeave={() => setHot(null)} stroke={p.out && hot === p.id ? '#fff' : 'none'} />)}
  </svg><p className="mt-1 min-h-[20px] text-[13px] text-slate-300" role="status">{hot !== null ? 'Unusual observation: far from the main cluster. Inspect before deciding (illustrative).' : 'Amber points sit far from the main group. DataLens flags them; it never removes them.'}</p></div>
}

const Q = [['Missing cells', '3.2%', 'warn', 'Imputation recommended'], ['Duplicate rows', '1.1%', 'warn', 'Policy is your choice'], ['Infinite values', '0', 'ok', 'None found'], ['Constant columns', '2', 'warn', 'No signal'], ['Validation after preparation', 'No missing / infinite', 'ok', 'Not a full ML-readiness verdict']]
function Quality() {
  return <ul className="divide-y divide-slate-700/70 text-[14px]" aria-label="Illustrative data quality summary">{Q.map(([k, v, t, n]) => <li key={k} className="flex items-start justify-between gap-3 py-2.5"><div><div className="text-slate-200">{k}</div><div className="text-[12.5px] text-slate-500">{n}</div></div><span className={'rounded-md px-2 py-0.5 text-[13px] font-semibold ' + (t === 'ok' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300')}>{v}</span></li>)}</ul>
}

export default function InsightVisuals() {
  return <div className="grid gap-5 lg:grid-cols-3">
    <Panel tag="A · RELATIONSHIPS" title="See what moves together" text="Correlated, redundant and opposing features stand out."><Heat /></Panel>
    <Panel tag="B · ANOMALIES" title="Spot what doesn’t belong" text="Unusual observations are separated from the main structure."><Scatter /></Panel>
    <Panel tag="C · DATA QUALITY" title="Know what needs attention" text="Missingness, duplicates, infinite values and validation at a glance."><Quality /></Panel>
  </div>
}
