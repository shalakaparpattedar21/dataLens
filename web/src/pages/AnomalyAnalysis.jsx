import { useMemo, useState } from 'react'
import { BarList, Histogram, Scatter } from '../components/charts.jsx'
import { DataTable, Details, Figure, InfoBox, NeedsAnalysis, Section, Tip, fmt, num, pct } from '../components/ui.jsx'

const METHODS = { isolation_forest: 'Isolation Forest', lof: 'Local Outlier Factor', iqr: 'IQR statistical rule', dbscan: 'DBSCAN (exploratory)' }
const CLASS = { multivariate_anomaly: 'Multivariate anomaly', statistical_outlier: 'Statistical outlier' }

export default function AnomalyAnalysis({ ctx }) {
  const { analysis, dataset, profile, busy, runAnalysis, runAnomaly, job } = ctx
  const a = analysis?.anomalies
  const numericOptions = useMemo(() => (analysis?.distributions?.numeric || []).map((c) => c.column), [analysis])
  const [form, setForm] = useState({ method: 'isolation_forest', contamination: '0.01', max_rows: '20000', seed: '42' })
  const [chosen, setChosen] = useState(null)   // null = backend default
  const [labelFilter, setLabelFilter] = useState('all')
  const [errorsOnly, setErrorsOnly] = useState(false)
  const [selectedRow, setSelectedRow] = useState(null)
  const running = busy || ['queued', 'running'].includes(job?.status)
  if (!a) return <NeedsAnalysis dataset={dataset} profile={profile} busy={running} onRun={runAnalysis} what="Anomaly analysis" />
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const features = chosen ?? a.config.features
  const toggle = (c) => setChosen(features.includes(c) ? features.filter((x) => x !== c) : features.length < 25 ? [...features, c] : features)
  const labels = [...new Set(a.records.map((r) => r.label).filter(Boolean))]
  const rows = a.records.filter((r) => (labelFilter === 'all' || r.label === labelFilter) && (!errorsOnly || r.data_error_indicators.length))
  const picked = selectedRow != null ? a.records.find((r) => r.row_id === selectedRow) : null
  const download = () => {
    const csv = 'row_id,score,label,category\n' + a.records.map((r) => [r.row_id, r.score, JSON.stringify(r.label ?? ''), r.category].join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    Object.assign(document.createElement('a'), { href: url, download: 'flagged_row_ids.csv' }).click(); URL.revokeObjectURL(url)
  }
  const run = () => runAnomaly({ method: form.method, contamination: Number(form.contamination), max_rows: Number(form.max_rows), seed: Number(form.seed) || 0, features: chosen })
  const noContam = ['iqr', 'dbscan'].includes(form.method)
  return <div className="space-y-2">
    <Section title="Run configuration" subtitle="Rows are never removed or changed. Re-running with other settings replaces this result.">
      <div className="form-grid !grid-cols-2 sm:!grid-cols-4">
        <label>Method<select aria-label="Method" value={form.method} onChange={set('method')}>{Object.entries(METHODS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Expected anomaly share<Tip text="Share of analysed rows to flag. Ignored by IQR (flags anything outside the fences) and DBSCAN (flags noise points)." /><select aria-label="Contamination" value={form.contamination} onChange={set('contamination')} disabled={noContam}>{['0.001', '0.005', '0.01', '0.02', '0.05', '0.1'].map((v) => <option key={v} value={v}>{(Number(v) * 100).toFixed(1)}%</option>)}</select></label>
        <label>Max rows analysed<select aria-label="Max rows" value={form.max_rows} onChange={set('max_rows')}>{['5000', '10000', '20000', '50000'].map((v) => <option key={v} value={v}>{num(Number(v))}</option>)}</select></label>
        <label>Seed<input aria-label="Anomaly seed" type="number" min="0" value={form.seed} onChange={set('seed')} className="mt-1.5 block w-full rounded-[10px] border border-slate-300 px-2.5 py-2 text-sm" /></label>
      </div>
      <Details summary={`Features (${features.length} selected${chosen ? '' : ', default'})`}><div className="grid max-h-48 gap-x-4 gap-y-1 overflow-auto sm:grid-cols-3">{numericOptions.map((c) => <label key={c} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={features.includes(c)} onChange={() => toggle(c)} />{c}</label>)}</div>
        <p className="mt-2 text-xs text-slate-400">At most 25 features. Missing values are median-imputed and infinities treated as missing before scoring.</p></Details>
      <div className="mt-3"><button className="primary-btn" disabled={running || !features.length} onClick={run}>{running ? 'Running…' : 'Run detection'}</button></div>
    </Section>

    <Section title="Result" subtitle={`${METHODS[a.method]} · ${CLASS[a.category]}`}>
      <div className="flex flex-wrap gap-x-10 gap-y-4 border-b border-slate-200 pb-5">
        <Figure label="Records analysed" value={num(a.summary.rows_analyzed)} note={`of ${num(a.summary.rows_available)} in the dataset`} />
        <Figure label="Flagged" value={num(a.summary.flagged)} note={pct(a.summary.flagged_percent, 2)} tone={a.summary.flagged ? 'warn' : undefined} />
        <Figure label="Data-error indicators" value={num(a.summary.data_error_indicator_rows)} note="heuristic" />
        <Figure label="Seed" value={a.config.seed} note={`${a.config.features.length} features`} />
      </div>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <InfoBox title="Statistical outlier">Extreme on a single feature (IQR rule).</InfoBox>
        <InfoBox title="Multivariate anomaly">Unusual in combination across features (Isolation Forest, LOF, DBSCAN).</InfoBox>
        <InfoBox tone="warn" title="Potential data error">Heuristic only: infinite value, or negative in an otherwise non-negative column.</InfoBox>
      </div>
      <p className="mt-3 text-sm text-slate-500">{a.interpretation}</p>
    </Section>

    <Section title="Score distribution" subtitle={a.score_meaning}>
      <div className="max-w-2xl"><Histogram counts={a.score_histogram.all} overlay={a.score_histogram.flagged} edges={a.score_histogram.edges} xLabel="anomaly score" logY /></div>
      <p className="mt-1 text-xs text-slate-400">Log-scaled counts. Orange = flagged rows. Threshold: {fmt(a.config.score_threshold)}.</p>
    </Section>

    <Section title="Projection" subtitle={`${a.scatter.projection}${a.scatter.explained_variance ? ` · explains ${(100 * (a.scatter.explained_variance[0] + a.scatter.explained_variance[1])).toFixed(0)}% of variance` : ''}. All flagged points (capped) plus a seeded subsample of normal rows (${num(a.scatter.points.length)} drawn). Click a point to inspect it.`}>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_1fr]">
        <Scatter points={a.scatter.points} xLabel={a.scatter.explained_variance ? 'PC 1' : 'feature value'} yLabel={a.scatter.explained_variance ? 'PC 2' : 'anomaly score'} selectedId={selectedRow} onSelect={setSelectedRow} />
        <aside aria-label="Selected record">{picked ? <div className="text-sm"><h3>Row {picked.row_id}</h3><p className="mt-1 text-xs text-slate-500">Score {picked.score} · {CLASS[picked.category]}{picked.label ? ` · label ${picked.label}` : ''}</p>
          <ul className="mt-3 space-y-1 text-xs">{picked.top_features.map((f) => <li key={f.feature}><b>{f.feature}</b> = {fmt(f.value)} <span className="text-slate-400">(median {fmt(f.median)}, {f.robust_z > 0 ? '+' : ''}{f.robust_z} IQR)</span></li>)}</ul>
          {picked.data_error_indicators.map((d) => <p key={d} className="mt-2 text-xs text-amber-700">Possible data error: {d}</p>)}</div>
          : <p className="text-xs text-slate-400">Select a point or table row to see why it was flagged. “Why” lists the features furthest from the median in IQR units: descriptive, not model-intrinsic.</p>}</aside>
      </div>
    </Section>

    {a.by_class.length > 0 && <Section title="Flagged share by class" subtitle="In intrusion data, attack classes are often flagged because they are rare or unusual, not because the records are wrong.">
      <div className="max-w-2xl"><BarList rows={a.by_class.map((c) => ({ label: c.label, value: c.flagged_percent, display: `${c.flagged_percent}% (${num(c.flagged)} / ${num(c.rows)})` }))} /></div></Section>}

    <Section title="Flagged records" subtitle={`Top ${num(a.records_shown)} of ${num(a.records_total_flagged)} by score. Row ID = 0-based position among data rows in the source file(s).`}
      actions={<button className="secondary-btn" onClick={download}>Download row IDs (CSV)</button>}>
      <DataTable caption="Flagged records" rows={rows} searchKeys={['row_id', 'label']} initialSort={{ key: 'score', dir: 'desc' }}
        filters={<><label className="flex items-center gap-2 text-sm text-slate-600">Class<select aria-label="Class filter" value={labelFilter} onChange={(e) => setLabelFilter(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1 text-sm"><option value="all">All</option>{labels.map((l) => <option key={l}>{l}</option>)}</select></label>
          <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} />Data-error indicators only</label></>}
        columns={[{ key: 'row_id', label: 'Row ID', num: true }, { key: 'score', label: 'Score', num: true }, { key: 'label', label: 'Label' },
          { key: 'category', label: 'Type', render: (r) => CLASS[r.category] },
          { key: 'why', label: 'Why flagged', sortValue: (r) => r.top_features[0] ? Math.abs(r.top_features[0].robust_z) : 0, render: (r) => <button className="text-left text-xs text-slate-600 hover:text-indigo-700" onClick={() => setSelectedRow(r.row_id)}>{r.top_features.slice(0, 2).map((f) => `${f.feature} (${f.robust_z > 0 ? '+' : ''}${f.robust_z} IQR)`).join(', ') || '—'}</button> },
          { key: 'err', label: 'Data error?', sortValue: (r) => r.data_error_indicators.length, render: (r) => (r.data_error_indicators.length ? <span className="text-xs text-amber-700">{r.data_error_indicators[0]}</span> : '—') }]} />
    </Section>

    {a.data_error_candidates.length > 0 && <Section title="Potential data errors" subtitle={a.data_error_note}>
      <DataTable rows={a.data_error_candidates} pageSize={8} searchKeys={['row_id']} columns={[{ key: 'row_id', label: 'Row ID', num: true }, { key: 'reasons', label: 'Indicator', render: (r) => r.reasons.join('; ') }, { key: 'flagged', label: 'Also flagged', render: (r) => (r.flagged ? 'yes' : 'no') }, { key: 'label', label: 'Label' }]} /></Section>}
    <Details summary="Configuration and execution metadata"><pre className="soft-scroll overflow-auto text-xs">{JSON.stringify({ config: a.config, sample: a.sample, created_at: a.created_at }, null, 2)}</pre></Details>
  </div>
}
