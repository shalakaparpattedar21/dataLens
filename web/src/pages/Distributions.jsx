import { useState } from 'react'
import { BarList, BoxPlot, Histogram } from '../components/charts.jsx'
import { Empty, fmt, num, pct } from '../components/ui.jsx'

/** Missing-value bars (full-data profile) + histograms/box plots/categorical bars (sample), all from the backend. */
export function MissingBars({ profile }) {
  const rows = (profile.dtypes || []).filter((c) => c.missing_cells > 0).sort((a, b) => b.missing_cells - a.missing_cells)
  if (!rows.length) return <p className="text-sm text-slate-400">No missing values in any column (full-data scan of {num(profile.rows)} rows).</p>
  return <div><BarList rows={rows.slice(0, 15).map((c) => ({ label: c.column, value: 100 * c.missing_cells / profile.rows, display: `${(100 * c.missing_cells / profile.rows).toFixed(2)}% (${num(c.missing_cells)})` }))} max={Math.max(5, ...rows.map((c) => 100 * c.missing_cells / profile.rows))} />
    <p className="mt-2 text-xs text-slate-400">Share of {num(profile.rows)} rows missing, per column (full scan). {rows.length > 15 ? `Top 15 of ${rows.length} columns shown.` : ''}</p></div>
}

export function NumericDistributions({ dist }) {
  const [col, setCol] = useState('')
  if (!dist) return <p className="text-sm text-slate-400">Run the analysis to see distributions.</p>
  if (!dist.numeric.length) return <Empty title="No numeric columns">There are no numeric, non-constant columns to plot.</Empty>
  const picked = dist.numeric.find((c) => c.column === col) || dist.numeric[0]
  const heavy = [...dist.numeric].sort((a, b) => (b.outliers_low + b.outliers_high) / b.n - (a.outliers_low + a.outliers_high) / a.n).slice(0, 8)
  return <div className="grid gap-8 lg:grid-cols-2">
    <div><label className="mb-2 flex items-center gap-2 text-sm text-slate-600">Histogram of<select aria-label="Histogram column" value={picked.column} onChange={(e) => setCol(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1 text-sm">{dist.numeric.map((c) => <option key={c.column}>{c.column}</option>)}</select></label>
      <Histogram counts={picked.histogram.counts} edges={picked.histogram.edges} xLabel={picked.column} />
      <p className="mt-1 text-xs text-slate-400">n = {num(picked.n)} sampled values · mean {fmt(picked.mean)} · median {fmt(picked.median)} · std {fmt(picked.std)} · skew {fmt(picked.skew)} · missing {pct(picked.missing_percent, 2)}</p></div>
    <div><h4 className="mb-2 text-sm font-semibold text-slate-700">Box plots: columns with the most IQR outliers</h4>
      <ul className="space-y-1">{heavy.map((s) => <li key={s.column}><div className="flex justify-between text-xs text-slate-600"><span>{s.column}</span><span className="num text-slate-400">{num(s.outliers_low + s.outliers_high)} outside fences ({pct(100 * (s.outliers_low + s.outliers_high) / s.n, 1)})</span></div><BoxPlot stat={s} /></li>)}</ul>
      <p className="text-xs text-slate-400">Whiskers: 1.5×IQR. Orange dots mark the extreme value beyond a fence. {dist.note}</p></div>
  </div>
}

export function CategoricalDistributions({ dist }) {
  if (!dist?.categorical?.length) return <p className="text-sm text-slate-400">No categorical columns in the sample.</p>
  return <div className="grid gap-8 lg:grid-cols-2">{dist.categorical.slice(0, 6).map((c) => <div key={c.column}><h4 className="mb-2 text-sm font-semibold text-slate-700">{c.column} <span className="font-normal text-slate-400">· {num(c.distinct)} distinct{c.high_cardinality ? ' (high cardinality)' : ''}</span></h4>
    <BarList rows={c.top.map((t) => ({ label: t.value, value: t.count, display: `${num(t.count)} · ${(100 * t.count / c.n).toFixed(1)}%` }))} /><p className="mt-1 text-xs text-slate-400">Top {c.top.length} of {num(c.n)} sampled rows.</p></div>)}</div>
}
