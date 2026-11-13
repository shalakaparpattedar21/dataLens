import { useMemo, useState } from 'react'
import Segmented from '../components/controls/Segmented.jsx'
import { EXTRA_FILE, FILES, infinite, mb, running, when } from '../api.js'
import { BarList, GroupedBars, StackedBar } from '../components/charts.jsx'
import { DataTable, Details, Empty, Figure, InfoBox, PageHeader, Section, SevTag, Tip, num, pct } from '../components/ui.jsx'
import { CategoricalDistributions, MissingBars, NumericDistributions } from './Distributions.jsx'
import Recommendations from './Recommendations.jsx'

const sevRank = { warning: 0, info: 1 }
export const sortedIssues = (p) => [...(p?.issues || [])].sort((a, b) => (sevRank[a.severity] ?? 2) - (sevRank[b.severity] ?? 2))
const crumbs = (ctx, page) => ['Workspace', ...(ctx.dataset ? [ctx.dataset.name] : []), page]

export function NoDataset({ ctx }) {
  return <Empty title="Start with a dataset" action={<><button onClick={() => ctx.pick()} className="primary-btn">Upload CSV</button><button onClick={ctx.addCic} disabled={ctx.busy} className="secondary-btn">Use local CIC-IDS2017</button></>}>Upload a CSV or register local CIC-IDS2017 files. Profiling scans in chunks and never changes your source data.</Empty>
}
export function NeedProfile({ ctx }) {
  if (!ctx.dataset) return <NoDataset ctx={ctx} />
  return <Empty title="Profile this dataset first" action={<button disabled={ctx.busy || running(ctx.job)} onClick={() => ctx.profileDataset(ctx.dataset.id)} className="primary-btn">Run profile</button>}>{ctx.dataset.name} has not been profiled yet.</Empty>
}

function IssueList({ issues, show }) {
  return <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">{issues.slice(0, show).map((issue, i) => <li key={i} className="flex items-start gap-3 px-4 py-3">
    <SevTag severity={issue.severity === 'warning' ? 'medium' : 'info'} /><div className="min-w-0 flex-1"><div className="flex flex-wrap gap-2 text-sm font-medium">{issue.title}{issue.column && <span className="rounded bg-slate-100 px-1.5 text-xs font-normal text-slate-500">{issue.column}</span>}</div>
      <p className="mt-1 text-sm leading-relaxed text-slate-500">{issue.explanation}</p>{issue.recommendation && <p className="mt-1 text-sm leading-relaxed text-indigo-700"><b>Recommendation:</b> {issue.recommendation}</p>}
      {issue.classes?.length > 0 && <p className="mt-1 text-xs text-slate-500">Classes: {issue.classes.map((c) => c.label + ' (' + num(c.count) + ')').join(', ')}</p>}</div><b className="num text-sm text-slate-600">{num(issue.count)}</b></li>)}
    {!issues.length && <li className="px-4 py-4 text-sm text-emerald-800">No issues detected.</li>}</ul>
}

export function ColumnTable({ profile }) {
  return <DataTable caption="Column profile" rows={profile.dtypes} searchKeys={['column', 'dtype']} pageSize={12} columns={[
    { key: 'column', label: 'Column', render: (c) => <>{c.column}{c.column === profile.label_column && <span className="ml-2 rounded bg-indigo-50 px-1 text-[10.5px] text-indigo-600">TARGET</span>}</> },
    { key: 'dtype', label: 'Type' }, { key: 'missing_cells', label: 'Missing', num: true }, { key: 'positive_infinity_cells', label: '+∞', num: true }, { key: 'negative_infinity_cells', label: '−∞', num: true },
    { key: 'constant', label: 'Signal', render: (c) => (c.constant ? <span className="pill neutral">Constant</span> : '—') }]} />
}

export function Overview({ ctx }) {
  const { dataset, profile, analysis, go, job, busy } = ctx
  const issues = sortedIssues(profile)
  const classes = profile?.class_distribution || []
  const h = analysis?.health
  const head = <PageHeader crumbs={crumbs(ctx, 'Overview')} title="Know your data before you model" description="Upload → Understand → Investigate → Recommend → Prepare → Validate → Export. Your source data is never modified."
    actions={profile && <><button disabled={busy || running(job)} onClick={() => ctx.profileDataset(dataset.id)} className="secondary-btn">Refresh profile</button><button onClick={() => go('Prepare')} className="primary-btn">Prepare data →</button></>} />
  if (!dataset) return <div className="space-y-6">{head}<NoDataset ctx={ctx} /></div>
  if (!profile) return <div className="space-y-6">{head}<section className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white p-5"><div><div className="eyebrow text-indigo-600">SELECTED DATASET</div><h3 className="mt-1">{dataset.name}</h3><p className="mt-1 text-xs text-slate-500">{dataset.file_names?.join(', ')} · {mb(dataset.size_bytes)} MB</p></div><button disabled={busy || running(job)} onClick={() => ctx.profileDataset(dataset.id)} className="primary-btn">Run profile</button></section></div>
  return <div className="space-y-2">{head}
    <div className="flex flex-wrap gap-x-12 gap-y-4 border-b border-slate-200 py-5">
      <Figure label="Rows scanned" value={num(profile.rows)} note="full dataset · chunked scan" /><Figure label="Columns" value={profile.columns} note={`${num(profile.dtypes.filter((c) => c.constant).length)} constant`} />
      <Figure label="Missing + infinite" value={num(profile.missing_cells + infinite(profile))} note={`${num(profile.missing_cells)} missing · ${num(infinite(profile))} infinite`} tone={profile.missing_cells + infinite(profile) ? 'warn' : undefined} />
      <Figure label="Exact duplicates" value={num(profile.duplicate_rows)} note="repeated feature + label rows" tone={profile.duplicate_rows ? 'warn' : undefined} />
      {h && <button className="text-left" onClick={() => go('Dataset Health')} aria-label="Open dataset health"><Figure label="Health score" value={h.overall === null ? '—' : Math.round(h.overall) + ' / 100'} note={h.readiness.label + ' →'} tone={h.readiness.status === 'high_risk' ? 'crit' : h.readiness.status === 'ready_for_experimentation' ? 'ok' : 'warn'} /></button>}
    </div>
    {!analysis?.health && <InfoBox title="Next:">Run the full analysis to unlock Feature Intelligence, Anomaly Analysis, Leakage Intelligence, the Health Score and preprocessing recommendations. <button className="ml-2 font-semibold underline" disabled={busy || running(job)} onClick={ctx.runAnalysis}>Run analysis</button></InfoBox>}
    <div className="grid gap-10 pt-6 xl:grid-cols-[1.25fr_.75fr]">
      <Section title="Quality signals" subtitle="Most severe first. Findings are explained and never auto-corrected.">
        <IssueList issues={issues} show={5} />{issues.length > 5 && <button className="mt-3 text-sm font-semibold text-indigo-600" onClick={() => go('Investigate')}>View all {issues.length} findings with recommendations →</button>}</Section>
      <Section title="Class distribution" subtitle={profile.label_column ? 'Target: ' + profile.label_column : 'No target detected'}>
        <BarList rows={classes.slice(0, 8).map((c) => ({ label: c.label, value: c.percent, display: `${num(c.count)} · ${c.percent}%`, color: (profile.issues.find((i) => i.title === 'Rare classes')?.classes || []).some((r) => r.label === c.label) ? '#d97706' : undefined }))} emptyText="No target column, so no class distribution." />
        {classes.length > 8 && <button className="mt-3 text-sm font-semibold text-indigo-600" onClick={() => go('Investigate')}>View all {classes.length} classes →</button>}</Section>
    </div>
    <Section title="Column profile" subtitle="Data types, missingness, infinity and constants."><ColumnTable profile={profile} /></Section></div>
}

export function Investigate({ ctx }) {
  const { dataset, profile, analysis, go, job, busy, severity, setSeverity } = ctx
  const head = <PageHeader crumbs={crumbs(ctx, 'Investigate')} title="Investigate data quality" description="Findings, distributions and recommendations drawn from the full-data profile and a seeded 50,000-row sample."
    actions={profile && <button className="secondary-btn" disabled={busy || running(job)} onClick={ctx.runAnalysis}>{analysis?.health ? 'Re-run analysis' : 'Run analysis'}</button>} />
  if (!profile) return <div className="space-y-6">{head}<NeedProfile ctx={ctx} /></div>
  const issues = sortedIssues(profile).filter((i) => severity === 'all' || i.severity === severity)
  const dist = analysis?.distributions
  const lk = analysis?.leakage
  const conf = (ctx.runLeakage?.findings || []).concat(lk?.findings || []).filter((f) => f.status === 'confirmed').length
  const out = profile.outliers || []
  const dup = profile.duplicates
  const links = [['Feature Intelligence', analysis?.relationships ? `${analysis.relationships.high_correlation_pairs_total} correlated pairs` : 'not run'], ['Anomaly Analysis', analysis?.anomalies ? `${num(analysis.anomalies.summary.flagged)} flagged` : 'not run'],
    ['Leakage Intelligence', lk ? `${conf} confirmed` : 'not run'], ['Dataset Health', analysis?.health?.overall != null ? `score ${Math.round(analysis.health.overall)}` : 'not run']]
  return <div className="space-y-2">{head}
    <nav aria-label="Analysis shortcuts" className="grid gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200 sm:grid-cols-2 xl:grid-cols-4">{links.map(([p, n]) => <button key={p} onClick={() => go(p)} className="bg-white px-4 py-3 text-left hover:bg-slate-50"><div className="text-sm font-medium">{p} →</div><div className="mt-0.5 text-xs text-slate-500">{n}</div></button>)}</nav>
    {!analysis?.health && <InfoBox tone="info" title="Analysis not run yet.">Distributions, recommendations and the four analysis pages need the background analysis (about 10 seconds for a million rows). <button className="ml-2 font-semibold underline" disabled={busy || running(job)} onClick={ctx.runAnalysis}>Run analysis</button></InfoBox>}

    {analysis?.recommendations && <Section title="Recommended preprocessing" subtitle="Derived from measured findings. Review, accept or customise them on the Recommendations page.">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm"><span>{analysis.recommendations.items.length} recommendation(s), {analysis.recommendations.applicable} can be applied to the Prepare form.</span><button className="primary-btn" onClick={() => go('Recommendations')}>Review recommendations →</button></div></Section>}

    <Section title="Findings" subtitle="Full-data profile. Each finding explains what was seen and what to do."
      actions={<div className="flex gap-1" role="group" aria-label="Severity filter">{['all', 'warning', 'info'].map((s) => <button key={s} onClick={() => setSeverity(s)} className={s === severity ? 'primary-btn !py-1.5' : 'secondary-btn !py-1.5'}>{s === 'all' ? 'All' : s === 'warning' ? 'Warnings' : 'Info'}</button>)}</div>}>
      <IssueList issues={issues} show={100} /></Section>

    <div className="grid gap-10 xl:grid-cols-2">
      <Section title="Missing values" subtitle="Share of rows missing per column."><MissingBars profile={profile} /></Section>
      <Section title="Class distribution" subtitle={profile.label_column ? 'Target: ' + profile.label_column + '. Amber = fewer than 100 rows.' : 'No target detected'}>
        <div className="soft-scroll max-h-[340px] overflow-y-auto pr-2"><BarList rows={(profile.class_distribution || []).map((c) => ({ label: c.label, value: c.percent, display: `${num(c.count)} · ${c.percent}%`, color: c.count < 100 ? '#d97706' : undefined }))} emptyText="No target column." /></div></Section>
    </div>
    <Section title="Numeric distributions" subtitle="Histogram and box plots from the seeded sample."><NumericDistributions dist={dist} /></Section>
    <Section title="Categorical distributions"><CategoricalDistributions dist={dist} /></Section>
    <div className="grid gap-10 xl:grid-cols-2">
      <Section title="Duplicates" subtitle="Rows with identical feature and label values.">{dup ? <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">{[['Global exact repeats', dup.exact_duplicate_rows_global], ['Within-file repeats', dup.exact_duplicate_rows_within_file], ['Only across files', dup.exact_duplicates_only_across_files], ['Conflicting-label rows', dup.label_conflict_rows]].map(([k, v]) => <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd className="num mt-1 text-xl">{num(v)}</dd></div>)}</dl> : <p className="text-sm text-slate-400">No duplicate detail. Refresh the profile.</p>}</Section>
      <Section title="Constant columns" subtitle="A single value carries no signal.">{(profile.constant_columns || []).length ? <div className="flex flex-wrap gap-2">{profile.constant_columns.map((c) => <span key={c} className="pill neutral">{c}</span>)}</div> : <p className="text-sm text-slate-400">None detected.</p>}</Section>
    </div>
    <Section title="IQR outliers" subtitle={`1.5×IQR rule on ${num(profile.outlier_sample_rows)} deterministic sample rows. Estimates only; no rows are removed. See Anomaly Analysis for multivariate methods.`}>
      <DataTable caption="IQR outliers" rows={out} searchKeys={['column']} pageSize={8} initialSort={{ key: 'estimated_percent', dir: 'desc' }} empty="No outliers detected in the sample." columns={[{ key: 'column', label: 'Column' }, { key: 'sample_outlier_rows', label: 'Outlier rows', num: true, render: (o) => `${num(o.sample_outlier_rows)} / ${num(o.sample_rows)}` }, { key: 'estimated_percent', label: 'Share', num: true, render: (o) => pct(o.estimated_percent, 2) }]} /></Section>
    <Section title="All columns"><ColumnTable profile={profile} /></Section></div>
}

export function Datasets({ ctx }) {
  const { datasets, datasetId, busy, job } = ctx
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('name')
  const [view, setView] = useState('all')
  const list = useMemo(() => {
    const sorters = { name: (a, b) => a.name.localeCompare(b.name), rows: (a, b) => (b.profile?.rows || 0) - (a.profile?.rows || 0), size: (a, b) => (b.size_bytes || 0) - (a.size_bytes || 0) }
    return datasets.filter((d) => d.name.toLowerCase().includes(q.trim().toLowerCase()) && (view === 'all' || (view === 'profiled' ? !!d.profile : !d.profile))).sort(sorters[sort])
  }, [datasets, q, sort, view])
  return <div className="space-y-6"><PageHeader crumbs={crumbs(ctx, 'Datasets')} title="Dataset library" description="Uploaded and registered CSV sources with their profiling status. Removing a dataset never deletes registered source files."
    actions={<><button className="secondary-btn" disabled={busy} onClick={ctx.addCic}>＋ Add CIC-IDS2017</button><button className="primary-btn" onClick={() => ctx.pick()}>↑ Upload CSV</button></>} />
    {datasets.length > 0 && <div className="flex flex-wrap items-center gap-3"><input type="search" aria-label="Search datasets" placeholder="Search datasets…" value={q} onChange={(e) => setQ(e.target.value)} className="w-full max-w-xs rounded-full border border-slate-300 bg-white px-4 py-2 text-sm sm:w-64" />
      <Segmented label="Profile status" value={view} onChange={setView} options={[['all', 'All'], ['profiled', 'Profiled'], ['new', 'Not profiled']]} />
      <label className="flex items-center gap-2 text-xs text-slate-500">Sort<select aria-label="Sort datasets" value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"><option value="name">Name</option><option value="rows">Most rows</option><option value="size">Largest file</option></select></label>
      <span className="text-xs text-slate-400">{list.length} of {datasets.length}</span></div>}
    {datasets.length ? <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">{list.map((d) => <li key={d.id} className={'flex flex-wrap items-center gap-4 px-4 py-3 ' + (d.id === datasetId ? 'bg-indigo-50/60' : '')}>
      <div className="min-w-0 flex-1"><b className="block truncate text-[15px]">{d.name}{d.id === datasetId && <span className="ml-2 rounded bg-indigo-100 px-1.5 text-[11px] font-semibold text-indigo-700">SELECTED</span>}</b><span className="text-xs text-slate-400">{d.file_names.join(', ')} · {mb(d.size_bytes)} MB</span><span className="mt-0.5 block text-xs text-slate-500">{d.profile ? num(d.profile.rows) + ' rows · ' + d.profile.columns + ' columns' : 'Not profiled'}</span></div>
      <span className="pill neutral">{d.source_status === 'available' ? (d.profile ? 'Profiled' : 'Not profiled') : 'Source missing'}</span><span className="pill neutral">{d.kind === 'local_read_only' ? 'Read-only source' : 'Upload'}</span>
      {!d.profile && d.source_status === 'available' && <button className="secondary-btn" disabled={busy || running(job)} onClick={() => ctx.profileDataset(d.id)}>Profile</button>}
      <button className="secondary-btn" onClick={() => ctx.openDataset(d.id)}>Open</button>
      <button className="secondary-btn" aria-label={'Remove ' + d.name} onClick={() => ctx.setConfirm({ type: 'dataset', id: d.id, name: d.name })}>Remove</button></li>)}
      {!list.length && <li className="px-4 py-8 text-center text-sm text-slate-400">No datasets match this search.</li>}</ul>
      : <Empty title="No datasets yet" action={<button className="primary-btn" onClick={() => ctx.pick()}>Upload CSV</button>}>Upload a CSV to begin.</Empty>}</div>
}

const HELP = {
  target: 'The label column. It is exported unchanged and never used as a feature.', sample: 'Rows are sampled in a single seeded pass. A sample is not a full-data result.',
  test: 'Share of rows assigned to test. Assignment is seeded and approximately stratified per class.', duplicate: 'Keep reports duplicates only. The other policies remove rows and the removed count is reported.',
  imputer: 'Fitted on training rows only. A missing-indicator column is added for each imputed column.', encoding: 'One-hot groups categories under 1% of training rows into one “infrequent” column. Ordinal maps categories to integers.',
  scaler: 'Fitted on training rows only, then applied to test. Robust is least sensitive to outliers.', selection: 'Variance removes constant outputs. Top k (ANOVA F) ranks on training rows and needs a target.',
}
function Select({ label, help, value, set, children }) { return <label>{label}<Tip text={help} /><select value={value} onChange={(e) => set(e.target.value)} aria-label={label}>{children}</select></label> }

const FLOW = ['Target', 'Sample', 'Split', 'Duplicates', 'Missing', 'Encoding', 'Scaling', 'Selection', 'Seed', 'Review', 'Prepare', 'Validate', 'Export']
/** 13-step flow. Steps 1-9 are the form fields (always configured via defaults); 10+ reflect real run state. */
function FlowStrip({ ctx }) {
  const { run, runOk, job } = ctx
  const state = (i) => (i < 9 ? 'done' : i === 9 ? 'done' : i === 10 ? (run ? 'done' : running(job) ? 'now' : 'now') : i === 11 ? (run && runOk ? 'done' : '') : i === 12 ? (run ? 'done' : '') : '')
  return <ol aria-label="Preparation flow" className="flex flex-wrap gap-2">{FLOW.map((n, i) => { const st = state(i); return <li key={n} className={'flow-step ' + (st === 'done' ? 'flow-done' : st === 'now' ? 'flow-now' : '')}><b>{i + 1}</b>{n}</li> })}</ol>
}

export function Prepare({ ctx }) {
  const { dataset, profile, run, runOk, form, setForm, target, setTarget, job, busy, applied, setApplied } = ctx
  const f = (k) => (v) => setForm({ ...form, [k]: v })
  const cov = run?.class_coverage || []
  const tot = (k) => cov.reduce((s, c) => s + c[k], 0) || 1
  return <div className="space-y-6"><PageHeader crumbs={crumbs(ctx, 'Prepare')} title="Prepare a dataset" description="Choose each transform explicitly. Fitting uses training rows only; source files remain unchanged." />
    <FlowStrip ctx={ctx} />
    <div className="grid gap-10 xl:grid-cols-[.9fr_1.1fr]">
      <div className="space-y-4">{!dataset ? <NoDataset ctx={ctx} /> : !profile ? <NeedProfile ctx={ctx} /> : <div className="space-y-4">
        {applied.length > 0 && <InfoBox tone="ok" title="Applied from recommendations:">{applied.join(' · ')}. Review the form, then prepare. <button className="ml-2 underline" onClick={() => setApplied([])}>Dismiss</button></InfoBox>}
        <div className="rounded-lg border border-slate-200 bg-white p-5"><div className="mb-4 flex items-center justify-between gap-2 text-sm font-semibold"><span className="truncate">{dataset.name}<span className="ml-2 text-xs font-normal text-slate-400">{num(profile.rows)} rows</span></span><button className="text-xs font-semibold text-indigo-600" onClick={() => ctx.go('Investigate')}>See recommendations</button></div>
          <div className="form-grid">
            <Select label="Target column" help={HELP.target} value={target} set={setTarget}><option value="">No target</option>{profile.column_names.map((c) => <option key={c}>{c}</option>)}</Select>
            <Select label="Dataset size" help={HELP.sample} value={form.sample} set={f('sample')}><option value="0.1">10% sample</option><option value="0.25">25% sample</option><option value="1">Full dataset</option></Select>
            <Select label="Test split" help={HELP.test} value={form.testSize} set={f('testSize')}><option value="0.2">20% test</option><option value="0.25">25% test</option><option value="0.3">30% test</option></Select>
            <Select label="Duplicate policy" help={HELP.duplicate} value={form.duplicate} set={f('duplicate')}><option value="keep">Keep all · report only</option><option value="drop_within_file">Remove within-file repeats</option><option value="drop_exact">Remove global exact repeats</option></Select>
            <Select label="Missing numeric values" help={HELP.imputer} value={form.imputer} set={f('imputer')}><option value="median">Median</option><option value="mean">Mean</option><option value="most_frequent">Most frequent</option></Select>
            <Select label="Categorical encoding" help={HELP.encoding} value={form.encoding} set={f('encoding')}><option value="onehot">One-hot</option><option value="ordinal">Ordinal</option></Select>
            <Select label="Numeric scaling" help={HELP.scaler} value={form.scaler} set={f('scaler')}><option value="robust">Robust</option><option value="standard">Standard</option><option value="minmax">Min-max</option><option value="none">None</option></Select>
            <Select label="Feature selection" help={HELP.selection} value={form.selection} set={f('selection')}><option value="none">None</option><option value="variance">Remove zero variance</option><option value="kbest_f" disabled={!target}>Top k · ANOVA F{target ? '' : ' (needs target)'}</option></Select>
            <label>Random seed<Tip text="Same seed and options always produce identical files." /><input type="number" min="0" value={form.seed} onChange={(e) => f('seed')(e.target.value)} aria-label="Random seed" className="mt-1.5 block w-full rounded-[10px] border border-slate-300 bg-white px-2.5 py-2 text-sm" /></label>
          </div>
          <div className="mt-4"><InfoBox tone="warn" title="Review:">rows are removed only if you select a duplicate policy. A sample is not a full-data result. Rare classes may be missing from the test split; the run reports coverage per class.</InfoBox></div>
          <button onClick={ctx.prepare} disabled={busy || running(job)} className="primary-btn mt-4 w-full">{running(job) ? 'Working…' : '✦ Prepare and validate'}</button></div></div>}</div>
      <div className="space-y-4"><Section title="Validation and comparison" subtitle="Latest prepared run for this dataset.">
        {run ? <div className="space-y-4">
          <InfoBox tone={runOk ? 'ok' : 'crit'}>{runOk ? '✓ Preprocessing validation passed: no missing or infinite values in exported features. This is not a full ML-readiness verdict; see Dataset Health and Leakage Intelligence.' : '✕ Validation found remaining missing or infinite feature values. See quality_report.json.'}</InfoBox>
          <div className="grid grid-cols-2 gap-6 text-sm"><div><div className="text-xs text-slate-400">Before · source sample</div><b className="num mt-1 block text-xl font-medium">{num(run.comparison?.before_sample_preparation?.rows)} rows</b><span className="block text-xs text-slate-500">{run.comparison?.before_sample_preparation?.columns} columns · {num(run.comparison?.before_sample_preparation?.missing_cells)} missing · {num(run.comparison?.before_sample_preparation?.infinite_cells)} infinite</span></div>
            <div><div className="text-xs text-indigo-600">After · prepared</div><b className="num mt-1 block text-xl font-medium">{num(run.rows.train + run.rows.test)} rows</b><span className="block text-xs text-slate-500">{num(run.rows.train)} train · {num(run.rows.test)} test · {num(run.comparison?.processed_sample?.transformed_features)} features · {num(run.comparison?.processed_sample?.duplicate_rows_removed)} duplicates removed · {num(run.comparison?.processed_sample?.missing_feature_cells_after)} missing · {num(run.comparison?.processed_sample?.infinite_feature_cells_after)} infinite</span></div></div>
          {run.config && <p className="text-xs text-slate-500">Recipe: {run.config.duplicate_policy} duplicates · {run.config.numeric_imputer} imputer · {run.config.encoding} · {run.config.scaler} scaling · selection {run.config.feature_selection} · seed {run.config.seed} · {Math.round(run.sample_fraction * 100)}% of rows{run.target_column ? ' · target ' + run.target_column : ' · no target'}</p>}
          {run.train_test_overlap?.test_rows > 0 && <div><div className="mb-2 text-xs font-medium text-slate-600">Train/test overlap (exact copies in test)</div><StackedBar parts={[{ label: 'Also in train', value: run.train_test_overlap.test_rows_also_in_train, color: '#b42318' }, { label: 'Unique to test', value: run.train_test_overlap.test_rows - run.train_test_overlap.test_rows_also_in_train, color: '#c7cdf2' }]} /></div>}
          {run.warnings?.length > 0 && <InfoBox tone="warn" title={`${run.warnings.length} warning(s):`}><ul className="mt-1 list-disc space-y-1 pl-5">{run.warnings.map((w) => <li key={w}>{w}</li>)}</ul></InfoBox>}
          {cov.length > 0 && <Details summary={`Class coverage by split (${cov.length} classes)`}><div className="soft-scroll max-h-80 overflow-auto"><GroupedBars aLabel="Share of train" bLabel="Share of test" rows={cov.slice(0, 20).map((c) => ({ label: c.label, a: 100 * c.train / tot('train'), b: 100 * c.test / tot('test'), flag: c.flags.length ? <span className="ml-2 text-amber-700"> {c.flags.join(', ')}</span> : null, c }))} tipA={(r) => `${num(r.c.train)} train rows`} tipB={(r) => `${num(r.c.test)} test rows`} /></div></Details>}
          <div className="grid gap-2 sm:grid-cols-2">{[...FILES, ...(run.has_leakage ? [EXTRA_FILE] : [])].map(([n, d]) => <a key={n} className="download-link" href={'/api/preparations/' + run.id + '/files/' + n} download title={d}>⇩ {n}</a>)}</div>
          <button className="text-sm font-semibold text-indigo-600" onClick={() => ctx.go('Leakage Intelligence')}>Open leakage findings for this run →</button></div>
          : <Empty title="No prepared run yet">Configure the recipe and prepare. Validation and comparison appear here.</Empty>}</Section></div></div></div>
}

const GROUPED = [['DATA', ['train.csv', 'test.csv']], ['CONFIGURATION', ['config.json']], ['REPORTS', ['quality_report.json', 'quality_report.md', 'comparison.json', 'leakage_report.json']]]
function FileGroups({ run }) {
  const all = Object.fromEntries([...FILES, ...(run.has_leakage ? [EXTRA_FILE] : [])])
  return <div className="grid gap-4 md:grid-cols-3">{GROUPED.map(([g, names]) => <div key={g}><div className="eyebrow mb-2">{g}</div><div className="space-y-2">{names.filter((n) => all[n]).map((n) => <a key={n} className="download-link block" href={'/api/preparations/' + run.id + '/files/' + n} download title={all[n]}>⇩ {n}<span className="mt-0.5 block text-[11px] font-normal text-slate-400">{all[n]}</span></a>)}</div></div>)}</div>
}

export function Exports({ ctx }) {
  const { runs, dataset } = ctx
  return <div className="space-y-6"><PageHeader crumbs={crumbs(ctx, 'Exports')} title="Prepared exports" description="Data, configuration and reports for every prepared run, grouped by what they are." />
    {runs.length ? <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">{runs.map((r) => <li key={r.id} className="space-y-4 px-4 py-4"><div className="flex flex-wrap items-center gap-4"><div className="min-w-0 flex-1"><b className="block truncate text-[15px]">{r.dataset_name}</b><span className="text-xs text-slate-400">{when(r.created_at)} · {Math.round(r.sample_fraction * 100)}% {r.sample_fraction < 1 ? 'sample' : 'full'} · {num(r.rows.train)} train / {num(r.rows.test)} test{r.warnings?.length ? ' · ' + r.warnings.length + ' warning(s)' : ''}{dataset && r.dataset_id === dataset.id ? ' · selected dataset' : ''}</span></div>
      <button className="secondary-btn" aria-label={'Delete export ' + r.id} onClick={() => ctx.setConfirm({ type: 'run', id: r.id })}>Delete</button></div>
      <FileGroups run={r} /></li>)}</ul>
      : <Empty title="No prepared exports yet" action={<button className="primary-btn" onClick={() => ctx.go('Prepare')}>Go to Prepare</button>}>Create a run from a profiled dataset.</Empty>}</div>
}
