import { useState } from 'react'
import { Details, DataTable, Empty, Figure, InfoBox, NeedsAnalysis, Section, SevTag, StatusTag, fmt, num } from '../components/ui.jsx'
import { StackedBar, Histogram } from '../components/charts.jsx'
import Segmented from '../components/controls/Segmented.jsx'

const TYPE = { exact_overlap: 'Exact train/test overlap', near_duplicates: 'Near-duplicates', identifier_like_column: 'Identifier-like column', suspicious_feature_target: 'Suspicious feature–target link',
  target_name_proxy: 'Target-name proxy', duplicate_exposure: 'Duplicate exposure', group_leakage: 'Group leakage', temporal_leakage: 'Temporal leakage', preprocessing_leakage: 'Preprocessing leakage' }
const ORDER = ['confirmed', 'potential', 'not_assessed', 'clear']
const SEV = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }

function Finding({ f }) {
  const ev = Object.entries(f.evidence || {}).filter(([, v]) => v !== null && typeof v !== 'object')
  return <details className={'rounded-lg border bg-white ' + (f.status === 'confirmed' ? 'border-rose-300' : f.status === 'potential' ? 'border-amber-300 border-dashed' : 'border-slate-200')} open={f.status === 'confirmed'}>
    <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-3"><StatusTag status={f.status} /><SevTag severity={f.severity} /><span className="text-sm font-medium">{f.title}</span><span className="ml-auto text-xs text-slate-400">{TYPE[f.type] || f.type}</span></summary>
    <div className="space-y-3 border-t border-slate-100 px-4 py-3 text-sm">
      <p><b className="text-xs uppercase tracking-wide text-slate-400">Evidence</b><br />{f.evidence_text || '—'}</p>
      {ev.length > 0 && <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">{ev.map(([k, v]) => <div key={k} className="flex justify-between gap-3 border-b border-slate-100 py-0.5"><dt className="text-slate-500">{k.replace(/_/g, ' ')}</dt><dd className="num font-medium">{fmt(v)}</dd></div>)}</dl>}
      {f.risk && <p><b className="text-xs uppercase tracking-wide text-slate-400">Why it matters</b><br />{f.risk}</p>}
      {f.recommended_action && <p><b className="text-xs uppercase tracking-wide text-slate-400">Recommended action</b><br />{f.recommended_action}</p>}
      {f.limitations && <p className="text-xs text-slate-500"><b>Limits of this check:</b> {f.limitations}</p>}
    </div></details>
}

export default function LeakageIntelligence({ ctx }) {
  const { analysis, dataset, profile, busy, runAnalysis, runLeakage, latestRun, runLeakageCheck, job } = ctx
  const [threshold, setThreshold] = useState('0.05')
  const [stFilter, setStFilter] = useState('all')
  const [sevFilter, setSevFilter] = useState('all')
  const src = analysis?.leakage
  if (!src) return <NeedsAnalysis dataset={dataset} profile={profile} busy={busy || ['queued', 'running'].includes(job?.status)} onRun={runAnalysis} what="Leakage analysis" />
  const run = runLeakage
  const findings = [...src.findings, ...(run?.findings || [])].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || SEV[a.severity] - SEV[b.severity])
  const count = (s) => findings.filter((f) => f.status === s).length
  const active = findings.filter((f) => ['confirmed', 'potential'].includes(f.status))
  const level = (() => { const t = ['critical', 'high', 'medium', 'low', 'info'].find((s) => active.some((f) => f.severity === s)); return t ? { critical: 'Critical', high: 'High', medium: 'Moderate', low: 'Low', info: 'Low' }[t] : 'None detected' })()
  const sevGroup = (v) => (v === 'critical' ? 'high' : v === 'info' ? 'low' : v)
  const shown = findings.filter((f) => f.status !== 'clear' && (stFilter === 'all' || f.status === stFilter) && (sevFilter === 'all' || sevGroup(f.severity) === sevFilter))
  const overlap = run?.findings.find((f) => f.type === 'exact_overlap')
  const near = run?.findings.find((f) => f.type === 'near_duplicates')
  const affected = findings.filter((f) => f.features.length && ['confirmed', 'potential'].includes(f.status)).flatMap((f) => f.features.map((c) => ({ id: f.id + c, feature: c, type: TYPE[f.type] || f.type, severity: f.severity, status: f.status })))
  return <div className="space-y-2">
    <div className="flex flex-wrap gap-x-10 gap-y-4 border-b border-slate-200 pb-5">
      <Figure label="Highest active severity" value={level} tone={level === 'Critical' || level === 'High' ? 'crit' : level === 'Moderate' ? 'warn' : 'ok'} note="max severity of confirmed + potential" />
      <Figure label="Confirmed" value={num(count('confirmed'))} tone={count('confirmed') ? 'crit' : undefined} note="verified by computation" />
      <Figure label="Potential" value={num(count('potential'))} tone={count('potential') ? 'warn' : undefined} note="warning signs, not proof" />
      <Figure label="Not assessed" value={num(count('not_assessed'))} note="evidence missing" />
      <Figure label="Checked, clear" value={num(count('clear'))} tone="ok" />
    </div>
    <InfoBox>No risk score is invented here. Severity is a fixed rule applied to measured evidence, and every finding shows that evidence. <b>Confirmed</b> means verified on the data or the run record; <b>potential</b> means a warning sign that needs your judgement.</InfoBox>

    <Section title="Train / test overlap" subtitle={run ? `Prepared run ${latestRun?.id.slice(0, 8)} · exact copies are matched by 64-bit row hash; near-duplicates use an explicit similarity threshold.` : undefined}>
      {!run ? <Empty title="No prepared run yet" >Exact overlap, near-duplicates and preprocessing leakage are checked on a prepared train/test split. Prepare the dataset and they appear here automatically.</Empty> : <div className="grid gap-8 lg:grid-cols-2">
        <div><h4 className="mb-2 text-sm font-semibold text-slate-700">Exact copies of training rows in the test set</h4>
          {overlap?.evidence?.test_rows ? <StackedBar parts={[{ label: 'Also in train (exact)', value: overlap.evidence.test_rows_also_in_train, color: '#b42318' }, { label: 'Unique to test', value: overlap.evidence.test_rows - overlap.evidence.test_rows_also_in_train, color: '#c7cdf2' }]} /> : <p className="text-sm text-slate-400">No overlap record for this run.</p>}</div>
        <div><h4 className="mb-2 text-sm font-semibold text-slate-700">Nearest training row, per test row</h4>
          {near?.evidence?.histogram ? <><Histogram counts={near.evidence.histogram.counts} edges={near.evidence.histogram.edges} xLabel="RMS distance to nearest training row" />
            <p className="mt-1 text-xs text-slate-400">Distance in train-std units per feature. Threshold {near.evidence.threshold_rms}: {num(near.evidence.near_not_exact)} near and {num(near.evidence.exact_in_sample)} exact of {num(near.evidence.test_rows_checked)} checked (clipped at the 95th percentile).</p></> : <p className="text-sm text-slate-400">Near-duplicate check not available for this run.</p>}</div>
        <div className="flex flex-wrap items-end gap-3 lg:col-span-2"><label className="text-xs text-slate-600">Near-duplicate threshold (RMS, train std units)<input aria-label="Near-duplicate threshold" type="number" step="0.01" min="0.001" max="1" value={threshold} onChange={(e) => setThreshold(e.target.value)} className="mt-1 block w-32 rounded-md border border-slate-300 px-2 py-1.5 text-sm" /></label>
          <button className="secondary-btn" disabled={busy || ['queued', 'running'].includes(job?.status)} onClick={() => runLeakageCheck(latestRun.id, Number(threshold))}>Re-check this run</button></div>
      </div>}
    </Section>

    <Section title="Findings" subtitle="Confirmed first, then potential. Expand a finding for its evidence, risk, recommended action and the limits of the check."
      actions={<div className="flex flex-wrap gap-3"><Segmented label="Status filter" value={stFilter} onChange={setStFilter} options={[['all', 'All'], ['confirmed', 'Confirmed'], ['potential', 'Potential'], ['not_assessed', 'Not assessed']]} />
        <Segmented label="Severity filter" value={sevFilter} onChange={setSevFilter} options={[['all', 'All'], ['high', 'High'], ['medium', 'Medium'], ['low', 'Low']]} /></div>}>
      <p className="-mt-2 mb-3 text-xs text-slate-400">Severity “High” includes critical findings; “Low” includes informational ones. Showing {shown.length} of {findings.filter((f) => f.status !== 'clear').length} open finding(s).</p>
      <div className="space-y-2">{shown.map((f, i) => <Finding key={i + f.id} f={f} />)}{!shown.length && <p className="rounded-lg border border-dashed border-slate-300 bg-white/60 px-4 py-6 text-center text-sm text-slate-400">No findings match these filters.</p>}</div>
      {count('clear') > 0 && <div className="mt-3"><Details summary={`${count('clear')} check(s) passed`}><div className="space-y-2">{findings.filter((f) => f.status === "clear").map((f, i) => <Finding key={i + f.id} f={f} />)}</div></Details></div>}
    </Section>

    {affected.length > 0 && <Section title="Affected features">
      <DataTable caption="Affected features" rows={affected} searchKeys={['feature', 'type']} columns={[{ key: 'feature', label: 'Feature' }, { key: 'type', label: 'Finding' }, { key: 'severity', label: 'Severity', sortValue: (r) => -SEV[r.severity], render: (r) => <SevTag severity={r.severity} /> }, { key: 'status', label: 'Status', render: (r) => <StatusTag status={r.status} /> }]} /></Section>}
    <Details summary="What DataLens does and does not check"><ul className="list-disc space-y-1 pl-5 text-xs"><li>Exact duplicates across train and test are verified computationally (confirmed).</li><li>Near-duplicates use the threshold you set; training rows searched are a sample, so counts are a lower bound.</li><li>High feature–target association is a warning, not proof. Identifier-like columns are risks, not automatic leakage.</li><li>Group and temporal leakage are only assessed when a group-like or time column exists.</li><li>Preprocessing leakage is judged from the run's recorded fit scope; runs without that record are shown as not assessed.</li></ul></Details>
  </div>
}
