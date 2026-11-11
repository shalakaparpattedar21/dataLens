import { useMemo, useState } from 'react'
import { fmt, num } from './ui.jsx'

const COLORS = { base: '#6b7bd6', soft: '#c7cdf2', flag: '#c2410c', teal: '#0f766e', amber: '#d97706', grid: '#e3e8f0', ink: '#142338' }

/** Horizontal bar list: rows {label, value, display?, color?, note?}. Every value is drawn from props. */
export function BarList({ rows, max, unit = '', emptyText = 'No data.' }) {
  if (!rows?.length) return <p className="text-sm text-slate-400">{emptyText}</p>
  const top = max ?? Math.max(...rows.map((r) => r.value), 1e-9)
  return <ul className="space-y-2">{rows.map((r) => <li key={r.label}><div className="mb-1 flex justify-between gap-3 text-xs"><span className="truncate text-slate-700" title={r.label}>{r.label}{r.badge}</span><span className="num shrink-0 text-slate-500">{r.display ?? fmt(r.value) + unit}{r.note ? ' · ' + r.note : ''}</span></div>
    <div className="h-2 rounded-sm bg-slate-100"><div className="h-full rounded-sm" style={{ width: Math.max(0.6, 100 * r.value / top) + '%', background: r.color || COLORS.base }} /></div></li>)}</ul>
}

/** Histogram from counts/edges. overlay = counts drawn in the flag colour on the same bins. */
export function Histogram({ counts, edges, overlay, height = 120, xLabel, logY = false }) {
  const w = 420, pad = { l: 36, r: 8, t: 6, b: 22 }
  const f = (c) => (logY ? Math.log10(1 + c) : c)
  const top = Math.max(...counts.map(f), 1)
  const bw = (w - pad.l - pad.r) / counts.length
  const y = (c) => pad.t + (height - pad.t - pad.b) * (1 - f(c) / top)
  return <svg viewBox={`0 0 ${w} ${height}`} className="w-full" role="img" aria-label={xLabel ? `Histogram of ${xLabel}` : 'Histogram'}>
    <line x1={pad.l} x2={w - pad.r} y1={height - pad.b} y2={height - pad.b} stroke={COLORS.grid} />
    {counts.map((c, i) => <g key={i}><rect x={pad.l + i * bw + 0.5} y={y(c)} width={Math.max(1, bw - 1)} height={height - pad.b - y(c)} fill={COLORS.soft}><title>{`${fmt(edges[i])} – ${fmt(edges[i + 1])}: ${num(c)}${overlay ? ` (flagged ${num(overlay[i])})` : ''}`}</title></rect>
      {overlay && overlay[i] > 0 && <rect x={pad.l + i * bw + 0.5} y={y(overlay[i])} width={Math.max(1, bw - 1)} height={height - pad.b - y(overlay[i])} fill={COLORS.flag} />}</g>)}
    <text className="chart-text" x={pad.l} y={height - 6}>{fmt(edges[0])}</text><text className="chart-text" x={w - pad.r} y={height - 6} textAnchor="end">{fmt(edges[edges.length - 1])}</text>
    <text className="chart-text" x={pad.l - 4} y={pad.t + 8} textAnchor="end">{logY ? 'log' : num(Math.max(...counts))}</text>
  </svg>
}

/** One horizontal box plot from backend quartile stats. */
export function BoxPlot({ stat, width = 420 }) {
  const lo = Math.min(stat.min, stat.whisker_low), hi = Math.max(stat.max, stat.whisker_high)
  const span = hi - lo || 1
  const x = (v) => 8 + (width - 16) * ((v - lo) / span)
  return <svg viewBox={`0 0 ${width} 38`} className="w-full" role="img" aria-label={`Box plot of ${stat.column}`}>
    <line x1={x(stat.whisker_low)} x2={x(stat.whisker_high)} y1={16} y2={16} stroke="#7b8aa0" />
    <rect x={x(stat.q1)} y={7} width={Math.max(1.5, x(stat.q3) - x(stat.q1))} height={18} fill={COLORS.soft} stroke={COLORS.base}><title>{`Q1 ${fmt(stat.q1)} · median ${fmt(stat.median)} · Q3 ${fmt(stat.q3)}`}</title></rect>
    <line x1={x(stat.median)} x2={x(stat.median)} y1={7} y2={25} stroke={COLORS.ink} strokeWidth="2" />
    {stat.outliers_low > 0 && <circle cx={x(stat.min)} cy={16} r={3} fill={COLORS.flag}><title>{`${num(stat.outliers_low)} low outliers, min ${fmt(stat.min)}`}</title></circle>}
    {stat.outliers_high > 0 && <circle cx={x(stat.max)} cy={16} r={3} fill={COLORS.flag}><title>{`${num(stat.outliers_high)} high outliers, max ${fmt(stat.max)}`}</title></circle>}
    <text className="chart-text" x={8} y={36}>{fmt(lo)}</text><text className="chart-text" x={width - 8} y={36} textAnchor="end">{fmt(hi)}</text>
  </svg>
}

const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t))
const POS = [67, 56, 202], NEG = [217, 119, 6], MID = [250, 251, 253]
export const corrColor = (v) => (v === null || v === undefined ? '#eef1f6' : `rgb(${mix(MID, v >= 0 ? POS : NEG, Math.min(1, Math.abs(v)) ** 0.9).join(',')})`)

/** Correlation heatmap with rotated column labels, scroll, hover read-out and feature selection. */
export function Heatmap({ columns, matrix, selected, onSelect, cell = 20, labelMax = 24 }) {
  const [hover, setHover] = useState(null)
  const n = columns.length
  const left = 168, top = 132
  const trunc = (s) => (s.length > labelMax ? s.slice(0, labelMax - 1) + '…' : s)
  return <div className="min-w-0">
    <div className="mb-2 min-h-[22px] text-xs text-slate-600" aria-live="polite">{hover ? <><b>{hover.a}</b> × <b>{hover.b}</b>: <span className="num">{hover.v === null ? 'n/a' : hover.v.toFixed(3)}</span> <span className="text-slate-400">({hover.v === null ? '' : Math.abs(hover.v) >= .9 ? 'very strong' : Math.abs(hover.v) >= .7 ? 'strong' : Math.abs(hover.v) >= .4 ? 'moderate' : 'weak'} {hover.v !== null && hover.v < 0 ? 'negative' : 'positive'})</span></> : 'Hover a cell for details; click a label to inspect a feature.'}</div>
    <div className="soft-scroll overflow-auto rounded-lg border border-slate-200 bg-white" style={{ maxHeight: 560 }}>
      <svg width={left + n * cell + 12} height={top + n * cell + 8} role="img" aria-label="Correlation heatmap">
        {columns.map((c, j) => <text key={'c' + j} className="chart-text" style={{ fontWeight: selected === c ? 700 : 400, fill: selected === c ? '#4338ca' : undefined, cursor: 'pointer' }} transform={`translate(${left + j * cell + cell / 2 + 3},${top - 6}) rotate(-60)`} onClick={() => onSelect?.(c)}><title>{c}</title>{trunc(c)}</text>)}
        {columns.map((r, i) => <g key={'r' + i}>
          <text className="chart-text" x={left - 6} y={top + i * cell + cell / 2 + 4} textAnchor="end" style={{ fontWeight: selected === r ? 700 : 400, fill: selected === r ? '#4338ca' : undefined, cursor: 'pointer' }} onClick={() => onSelect?.(r)}><title>{r}</title>{trunc(r)}</text>
          {columns.map((c, j) => { const v = matrix[i][j]; const dim = selected && selected !== r && selected !== c
            return <rect key={j} x={left + j * cell} y={top + i * cell} width={cell - 1} height={cell - 1} rx="2" fill={corrColor(i === j ? null : v)} opacity={dim ? 0.3 : 1} stroke={hover && hover.i === i && hover.j === j ? '#142338' : 'none'}
              onMouseEnter={() => setHover({ a: r, b: c, v, i, j })} onMouseLeave={() => setHover(null)} onClick={() => onSelect?.(selected === r ? null : r)} />
          })}</g>)}
      </svg>
    </div>
    <div className="mt-2 flex items-center gap-2 text-xs text-slate-500"><span>−1 negative</span><div className="h-2 w-40 rounded-sm" style={{ background: `linear-gradient(90deg, ${corrColor(-1)}, ${corrColor(0)}, ${corrColor(1)})` }} /><span>+1 positive</span><span className="ml-3 text-slate-400">Light = weak or none</span></div>
  </div>
}

/** Scatter plot. points {x,y,flagged,row_id,score}. */
export function Scatter({ points, xLabel, yLabel, onSelect, selectedId }) {
  const w = 640, h = 360, pad = { l: 48, r: 12, t: 10, b: 36 }
  const { sx, sy, xr, yr } = useMemo(() => {
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y)
    const xr = [Math.min(...xs), Math.max(...xs)], yr = [Math.min(...ys), Math.max(...ys)]
    const sp = (r) => (r[1] - r[0]) || 1
    return { xr, yr, sx: (v) => pad.l + (w - pad.l - pad.r) * ((v - xr[0]) / sp(xr)), sy: (v) => pad.t + (h - pad.t - pad.b) * (1 - (v - yr[0]) / sp(yr)) }
  }, [points])
  const ordered = useMemo(() => [...points].sort((a, b) => a.flagged - b.flagged), [points])
  return <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-lg border border-slate-200 bg-white" role="img" aria-label={`Scatter of ${xLabel} against ${yLabel}`}>
    <line x1={pad.l} x2={w - pad.r} y1={h - pad.b} y2={h - pad.b} stroke={COLORS.grid} /><line x1={pad.l} x2={pad.l} y1={pad.t} y2={h - pad.b} stroke={COLORS.grid} />
    {ordered.map((p) => <circle key={p.row_id} cx={sx(p.x)} cy={sy(p.y)} r={p.flagged ? 3.6 : 2.2} fill={p.flagged ? COLORS.flag : COLORS.base} opacity={p.flagged ? 0.9 : 0.35} stroke={selectedId === p.row_id ? '#142338' : 'none'} strokeWidth="1.5" style={{ cursor: 'pointer' }} onClick={() => onSelect?.(p.row_id)}><title>{`row ${p.row_id} · score ${p.score}${p.flagged ? ' · flagged' : ''}`}</title></circle>)}
    <text className="chart-text" x={(w + pad.l) / 2} y={h - 8} textAnchor="middle">{xLabel}</text>
    <text className="chart-text" transform={`translate(12,${h / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
    <text className="chart-text" x={pad.l} y={h - 20}>{fmt(xr[0])}</text><text className="chart-text" x={w - pad.r} y={h - 20} textAnchor="end">{fmt(xr[1])}</text>
    <text className="chart-text" x={pad.l - 4} y={pad.t + 8} textAnchor="end">{fmt(yr[1])}</text><text className="chart-text" x={pad.l - 4} y={h - pad.b} textAnchor="end">{fmt(yr[0])}</text>
  </svg>
}

/** Grouped horizontal bars: rows {label, a, b} where a/b are shares (0-100). */
export function GroupedBars({ rows, aLabel, bLabel, unit = '%', tipA, tipB }) {
  if (!rows?.length) return <p className="text-sm text-slate-400">No data.</p>
  const top = Math.max(...rows.flatMap((r) => [r.a, r.b]), 1e-9)
  return <div><div className="mb-2 flex gap-4 text-xs text-slate-500"><span><i className="mr-1 inline-block h-2 w-3 align-middle" style={{ background: COLORS.base }} />{aLabel}</span><span><i className="mr-1 inline-block h-2 w-3 align-middle" style={{ background: COLORS.teal }} />{bLabel}</span></div>
    <ul className="space-y-3">{rows.map((r) => <li key={r.label}><div className="mb-1 truncate text-xs text-slate-700" title={r.label}>{r.label}{r.flag}</div>
      {[[r.a, COLORS.base, tipA?.(r)], [r.b, COLORS.teal, tipB?.(r)]].map(([v, c, t], i) => <div key={i} className="mb-0.5 flex items-center gap-2" title={t}><div className="h-1.5 flex-1 rounded-sm bg-slate-100"><div className="h-full rounded-sm" style={{ width: Math.max(0.5, 100 * v / top) + '%', background: c }} /></div><span className="num w-16 text-right text-[11.5px] text-slate-500">{v.toFixed(2)}{unit}</span></div>)}</li>)}</ul></div>
}

/** One stacked bar from parts {label, value, color}. */
export function StackedBar({ parts, total }) {
  const t = total ?? parts.reduce((s, p) => s + p.value, 0)
  return <div><div className="flex h-5 overflow-hidden rounded-sm bg-slate-100" role="img" aria-label={parts.map((p) => `${p.label}: ${p.value}`).join(', ')}>{parts.map((p) => <div key={p.label} style={{ width: (t ? 100 * p.value / t : 0) + '%', background: p.color, minWidth: p.value > 0 ? 2 : 0 }} title={`${p.label}: ${num(p.value)}`} />)}</div>
    <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600">{parts.map((p) => <span key={p.label}><i className="mr-1.5 inline-block h-2 w-3" style={{ background: p.color }} />{p.label}: <b className="num">{num(p.value)}</b>{t ? <span className="text-slate-400"> ({(100 * p.value / t).toFixed(2)}%)</span> : null}</span>)}</div></div>
}

/** Score bar 0..100 with quality bands, or "Insufficient data". */
export function ScoreBar({ score, label }) {
  if (score === null || score === undefined) return <div className="text-sm text-slate-400">{label || 'Insufficient data'}</div>
  const color = score >= 80 ? '#067647' : score >= 60 ? '#b45309' : '#b42318'
  return <div className="flex items-center gap-3" role="img" aria-label={`Score ${score} of 100`}><div className="relative h-2.5 flex-1 rounded-sm bg-slate-100"><div className="h-full rounded-sm" style={{ width: score + '%', background: color }} />{[60, 80].map((t) => <i key={t} className="absolute top-[-3px] h-4 w-px bg-slate-400/60" style={{ left: t + '%' }} />)}</div><span className="num w-12 text-right text-sm font-semibold" style={{ color }}>{score.toFixed(0)}</span></div>
}

/** Line of health snapshots. points {label, value}. */
export function Trend({ points }) {
  const w = 360, h = 90, p = 14
  if (points.length < 2) return <p className="text-sm text-slate-400">A trend appears after two or more health snapshots (each analysis or preparation adds one).</p>
  const xs = (i) => p + (w - 2 * p) * (i / (points.length - 1)), ys = (v) => p + (h - 2 * p) * (1 - v / 100)
  return <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Health score history">
    {[0, 50, 100].map((g) => <line key={g} x1={p} x2={w - p} y1={ys(g)} y2={ys(g)} stroke={COLORS.grid} />)}
    <polyline fill="none" stroke={COLORS.base} strokeWidth="2" points={points.map((q, i) => `${xs(i)},${ys(q.value)}`).join(' ')} />
    {points.map((q, i) => <circle key={i} cx={xs(i)} cy={ys(q.value)} r="3" fill={COLORS.base}><title>{`${q.label}: ${q.value}`}</title></circle>)}
    <text className="chart-text" x={w - p} y={ys(points[points.length - 1].value) - 7} textAnchor="end">{points[points.length - 1].value}</text>
  </svg>
}
