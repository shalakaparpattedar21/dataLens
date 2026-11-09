import { useCallback, useEffect, useRef, useState } from 'react'

const api = '/api'
async function call(path, options = {}) {
  let res
  try { res = await fetch(api + path, options) } catch {
    throw new Error('Cannot reach the DataLens backend. Start it with: python -m uvicorn datalens.api:app --port 8000')
  }
  const data = res.headers.get('content-type')?.includes('json') ? await res.json().catch(() => null) : null
  if (!res.ok) {
    const detail = data?.detail
    const text = Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : detail
    const err = new Error(text || `Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}

const PAGES = ['Overview', 'Investigate', 'Datasets', 'Prepare', 'Exports']
const icons = { Overview: '◫', Investigate: '⌕', Datasets: '▤', Prepare: '◈', Exports: '⇩' }
const titles = { Overview: 'Dataset overview', Investigate: 'Investigate data quality', Datasets: 'Dataset library', Prepare: 'Prepare a dataset', Exports: 'Prepared exports' }
const FILES = [
  ['train.csv', 'Transformed training rows'], ['test.csv', 'Transformed test rows'],
  ['config.json', 'Exact recipe, seed and fitted parameters'], ['quality_report.json', 'Machine-readable findings and validation'],
  ['quality_report.md', 'Human-readable quality report'], ['comparison.json', 'Before / after figures'],
]
const HELP = {
  target: 'The label column. It is exported unchanged and never used as a feature.',
  sample: 'Rows are sampled in a single seeded pass. A sample is not a full-data result.',
  test: 'Share of rows assigned to test. Assignment is seeded and approximately stratified per class.',
  duplicate: 'Keep reports duplicates only. The other policies remove rows and the removed count is reported.',
  imputer: 'Fitted on training rows only. A missing-indicator column is added for each imputed column.',
  encoding: 'One-hot groups categories under 1% of training rows into one “infrequent” column. Ordinal maps categories to integers.',
  scaler: 'Fitted on training rows only, then applied to test. Robust is least sensitive to outliers.',
  selection: 'Variance removes constant outputs. Top k (ANOVA F) ranks on training rows and needs a target.',
}
const num = (n) => Number(n || 0).toLocaleString()
const mb = (b) => (Number(b || 0) / 1048576).toFixed(1)
const sevRank = { warning: 0, info: 1 }
const bySeverity = (a, b) => (sevRank[a.severity] ?? 2) - (sevRank[b.severity] ?? 2)
const when = (v) => { const d = new Date(v); return isNaN(d) ? '' : d.toLocaleString() }
const infinite = (p) => (p?.positive_infinity_cells || 0) + (p?.negative_infinity_cells || 0)
const running = (j) => !!j && ['queued', 'running'].includes(j.status)

function Tip({ text }) { return <span title={text} aria-label={text} className="ml-1 cursor-help text-slate-300">ⓘ</span> }
function Empty({ icon = '▤', title, children, action }) {
  return <div className="panel grid place-items-center border-dashed p-10 text-center"><div><div className="big-icon">{icon}</div><h3 className="mt-4 text-base font-semibold">{title}</h3><p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{children}</p>{action && <div className="mt-4 flex justify-center gap-2">{action}</div>}</div></div>
}
function Sev({ severity }) { return <span className={severity === 'warning' ? 'text-amber-600' : 'text-indigo-500'}>{severity === 'warning' ? '⚠' : '✦'}</span> }

function recommend(profile) {
  if (!profile) return null
  const why = []
  const rec = { sample: profile.rows > 2_000_000 ? '0.1' : '1', duplicate: 'keep', imputer: 'median', scaler: 'robust', selection: 'none', encoding: 'onehot' }
  rec.sample === '0.1' ? why.push('Large dataset: start with a 10% sample, then rerun on the full data.') : why.push('Dataset is small enough to prepare in full.')
  if (profile.duplicates?.exact_duplicate_rows_global > 0) { rec.duplicate = 'drop_exact'; why.push('Exact duplicates found: remove them so train and test do not share copies.') }
  if (profile.missing_cells || infinite(profile)) why.push('Missing or infinite values: median imputation (infinite values are treated as missing).')
  if (profile.constant_columns?.length) { rec.selection = 'variance'; why.push('Constant columns found: remove zero-variance outputs.') }
  if (profile.outliers?.length) why.push('Outliers present: robust scaling is the least sensitive choice.')
  return { rec, why }
}

function App() {
  const [datasets, setDatasets] = useState([])
  const [runs, setRuns] = useState([])
  const [datasetId, setDatasetId] = useState('')
  const [dataset, setDataset] = useState(null)
  const [page, setPage] = useState('Overview')
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const [severity, setSeverity] = useState('all')
  const [target, setTarget] = useState('')
  const [sample, setSample] = useState('0.1')
  const [duplicate, setDuplicate] = useState('keep')
  const [imputer, setImputer] = useState('median')
  const [encoding, setEncoding] = useState('onehot')
  const [scaler, setScaler] = useState('robust')
  const [selection, setSelection] = useState('none')
  const [testSize, setTestSize] = useState('0.2')
  const [seed, setSeed] = useState('42')
  const picker = useRef(null)
  const profile = dataset?.profile
  const rec = recommend(profile)

  const refresh = useCallback(async (id) => {
    const [ds, pr] = await Promise.all([call('/datasets'), call('/preparations')])
    setDatasets(ds.datasets); setRuns(pr.preparations)
    if (id) {
      try { setDataset((await call('/datasets/' + id)).dataset) } catch (e) {
        if (e.status === 404) { setDatasetId(''); setDataset(null) } else throw e
      }
    }
  }, [])
  useEffect(() => { refresh('').catch((e) => setError(e.message)).finally(() => setLoaded(true)) }, [refresh])

  useEffect(() => {
    if (!job?.id || !running(job)) return
    const timer = setInterval(async () => {
      try {
        const { job: next } = await call('/jobs/' + job.id)
        setJob(next)
        if (next.status === 'complete') {
          await refresh(next.dataset_id)
          setNotice({ kind: next.kind, text: next.kind === 'profile' ? 'Profile complete.' : 'Preparation complete and validated.' })
        }
      } catch (e) {
        setJob(null)
        setError(e.status === 404 ? 'The job is no longer known to the backend (it may have restarted). Run the action again.' : e.message)
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [job, refresh])

  const defaultTarget = (ds) => ds?.profile?.label_column || ''
  // A fresh profile may arrive after the dataset was selected; adopt its detected label unless the current choice is still valid.
  useEffect(() => {
    const cols = profile?.column_names
    if (cols && target && !cols.includes(target)) setTarget(profile.label_column || '')
    else if (cols && !target && profile.label_column) setTarget(profile.label_column)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.created_at, datasetId])
  const selectDataset = async (id, go = 'Overview') => {
    const { dataset: ds } = await call('/datasets/' + id)
    setDatasetId(id); setDataset(ds); setTarget(defaultTarget(ds)); setPage(go); setNotice(null)
    return ds
  }
  const guard = async (fn) => { setError(''); setBusy(true); try { await fn() } catch (e) { setError(e.message) } finally { setBusy(false) } }

  const startProfile = async (id) => {
    setJob(null); setNotice(null)
    const { job: j } = await call('/datasets/' + id + '/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    setJob(j)
  }
  const profileDataset = (id) => guard(async () => { await selectDataset(id); await startProfile(id) })
  const upload = (file) => file && guard(async () => {
    const { dataset: d } = await call('/datasets/upload?filename=' + encodeURIComponent(file.name), { method: 'POST', headers: { 'Content-Type': 'text/csv' }, body: file })
    await refresh(d.id); await selectDataset(d.id); await startProfile(d.id)
  })
  const addCic = () => guard(async () => {
    const { dataset: d, already_registered } = await call('/datasets/import-cicids', { method: 'POST' })
    await refresh(d.id); const ds = await selectDataset(d.id)
    if (!already_registered || !ds.profile) await startProfile(d.id)
    else setNotice({ kind: 'info', text: 'CIC-IDS2017 is already registered and profiled.' })
  })
  const prepare = () => guard(async () => {
    setJob(null); setNotice(null)
    const body = { target_column: target || null, sample_fraction: Number(sample), test_size: Number(testSize), seed: Number(seed) || 0,
      duplicate_policy: duplicate, numeric_imputer: imputer, encoding, scaler, feature_selection: selection, missing_indicator: true }
    const { job: j } = await call('/datasets/' + datasetId + '/prepare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    setJob(j)
  })
  const applyRecipe = () => {
    if (!rec) return
    setSample(rec.rec.sample); setDuplicate(rec.rec.duplicate); setImputer(rec.rec.imputer); setScaler(rec.rec.scaler)
    setSelection(rec.rec.selection); setEncoding(rec.rec.encoding)
    setNotice({ kind: 'info', text: 'Recommended recipe applied. Review it, then prepare.' }); setPage('Prepare')
  }
  const doDelete = () => guard(async () => {
    const c = confirm; setConfirm(null)
    if (c.type === 'dataset') {
      await call('/datasets/' + c.id, { method: 'DELETE' })
      if (c.id === datasetId) { setDatasetId(''); setDataset(null); setTarget('') }
      setNotice({ kind: 'info', text: 'Dataset removed from the workspace. Source CSV files were not touched.' })
    } else {
      await call('/preparations/' + c.id, { method: 'DELETE' })
      setNotice({ kind: 'info', text: 'Prepared export deleted.' })
    }
    await refresh(c.type === 'dataset' && c.id === datasetId ? '' : datasetId)
  })

  const latestRun = runs.find((r) => r.dataset_id === datasetId)
  const datasetRuns = runs.filter((r) => r.dataset_id === datasetId)
  const metric = (label, value, detail, glyph, tint) => <div className="panel p-5"><div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-500">{label}</span><span className={'metric-icon ' + tint}>{glyph}</span></div><div className="mt-4 text-[27px] font-semibold tracking-tight">{value}</div><div className="mt-1 text-[11px] text-slate-400">{detail}</div></div>
  const go = (p) => setPage(p)
  const needProfile = (render) => !dataset
    ? <Empty title="No dataset selected" action={<><button onClick={() => picker.current?.click()} className="primary-btn">Upload CSV</button><button onClick={() => go('Datasets')} className="secondary-btn">Open library</button></>}>Pick a dataset from the library or upload a CSV.</Empty>
    : !profile
      ? <Empty title="Profile this dataset first" action={<button disabled={busy || running(job)} onClick={() => profileDataset(dataset.id)} className="primary-btn">Run profile</button>}>{dataset.name} has not been profiled yet.</Empty>
      : render()

  const issues = [...(profile?.issues || [])].sort(bySeverity)
  const shownIssues = issues.filter((i) => severity === 'all' || i.severity === severity)
  const classes = profile?.class_distribution || []
  const rareLabels = new Set((profile?.issues || []).find((i) => i.title === 'Rare classes')?.classes?.map((c) => c.label) || [])
  const dup = profile?.duplicates
  const run = latestRun
  const runOk = run && (run.comparison?.processed_sample?.missing_feature_cells_after ?? 1) === 0 && (run.comparison?.processed_sample?.infinite_feature_cells_after ?? 1) === 0

  return <div className="min-h-screen bg-[#f5f7fb] text-[#142338]">
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-[244px] flex-col border-r border-slate-200 bg-white px-4 py-5 lg:flex">
      <div className="flex items-center gap-3 px-2"><div className="brand-mark">✦</div><div><div className="text-[17px] font-bold">DataLens</div><div className="eyebrow">DATA WORKSPACE</div></div></div>
      <div className="eyebrow mt-10 px-3">WORKFLOW</div>
      <nav className="mt-3 space-y-1" aria-label="Primary">{PAGES.map((n) => <button key={n} onClick={() => go(n)} className={'nav-item ' + (page === n ? 'nav-active' : '')}><span className="w-5 text-center text-base">{icons[n]}</span>{n === 'Prepare' ? 'Prepare data' : n}{n === 'Datasets' && <span className="ml-auto rounded-full bg-slate-100 px-2 text-[10px] text-slate-500">{datasets.length}</span>}{n === 'Exports' && runs.length > 0 && <span className="ml-auto rounded-full bg-slate-100 px-2 text-[10px] text-slate-500">{runs.length}</span>}</button>)}</nav>
      <div className="mt-9 flex items-center justify-between px-3"><span className="eyebrow">YOUR DATASETS</span><button title="Upload CSV" aria-label="Upload CSV" onClick={() => picker.current?.click()} className="text-indigo-600">＋</button></div>
      <div className="soft-scroll mt-3 flex-1 space-y-1 overflow-y-auto">{datasets.map((d) => <button key={d.id} onClick={() => guard(() => selectDataset(d.id))} className={'dataset-link ' + (datasetId === d.id ? 'dataset-link-active' : '')}><span className="block truncate text-xs font-semibold">{d.name}</span><span className="mt-1 block text-[10px] text-slate-400">{d.profile ? num(d.profile.rows) + ' rows' : 'Ready to profile'}</span></button>)}{loaded && !datasets.length && <p className="px-3 text-[11px] text-slate-400">No datasets yet.</p>}</div>
      <div className="mt-4 rounded-2xl bg-slate-50 p-3"><div className="flex items-center gap-2 text-xs font-semibold"><i className="online-dot" />Local workspace</div><p className="mt-1 text-[10px] leading-relaxed text-slate-500">Your data stays on this machine.</p></div>
    </aside>
    <main className="min-h-screen lg:pl-[244px]">
      <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-[#f5f7fb]/90 backdrop-blur-xl">
        <div className="flex h-[72px] items-center justify-between px-5 sm:px-8">
          <div className="flex items-center gap-3"><div className="brand-mark lg:hidden">✦</div><div><div className="text-[10px] text-slate-400">Workspace <span className="mx-1">/</span> {page}{dataset ? <> <span className="mx-1">/</span> {dataset.name}</> : null}</div><h1 className="text-[17px] font-semibold">{titles[page]}</h1></div></div>
          <div className="flex gap-2"><button onClick={addCic} disabled={busy} className="hidden rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 disabled:opacity-50 sm:block">＋ Add CIC-IDS2017</button><button onClick={() => picker.current?.click()} disabled={busy} className="rounded-xl bg-indigo-600 px-3.5 py-2.5 text-xs font-semibold text-white shadow-md shadow-indigo-200 hover:bg-indigo-700 disabled:opacity-50">{busy ? 'Working…' : '↑ Upload CSV'}</button><input ref={picker} type="file" accept=".csv,text/csv" aria-label="CSV file" className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = '' }} /></div>
        </div>
        <nav aria-label="Mobile" className="soft-scroll flex gap-1 overflow-x-auto px-4 pb-2 lg:hidden">{PAGES.map((n) => <button key={n} onClick={() => go(n)} className={'nav-item !w-auto shrink-0 !py-2 ' + (page === n ? 'nav-active' : '')}>{n === 'Prepare' ? 'Prepare' : n}</button>)}</nav>
      </header>
      <div className="mx-auto max-w-[1460px] space-y-5 px-5 py-6 sm:px-8 sm:py-8">
        {error && <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
        {running(job) && <div className="panel flex items-center gap-4 p-4" role="status"><span className="h-8 w-8 shrink-0 animate-spin rounded-full border-2 border-indigo-100 border-t-indigo-600" /><div className="flex-1"><div className="flex justify-between text-xs font-semibold"><span>{job.kind === 'profile' ? 'Profiling dataset' : 'Preparing data'}</span><span>{Math.round(job.progress * 100)}%</span></div><p className="mt-1 text-[11px] text-slate-500">{job.message}</p><div className="mt-2 h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: (job.progress * 100) + '%' }} /></div></div></div>}
        {job?.status === 'failed' && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"><b>{job.kind === 'profile' ? 'Profiling failed' : 'Preparation failed'}:</b> {job.error}</div>}
        {notice && !running(job) && <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><span>✓ {notice.text}</span><span className="flex items-center gap-3">{notice.kind === 'profile' && <><button className="font-semibold underline" onClick={() => go('Investigate')}>Investigate findings</button><button className="font-semibold underline" onClick={() => go('Prepare')}>Prepare data</button></>}{notice.kind === 'prepare' && <><button className="font-semibold underline" onClick={() => go('Prepare')}>View validation</button><button className="font-semibold underline" onClick={() => go('Exports')}>Download exports</button></>}<button aria-label="Dismiss" onClick={() => setNotice(null)}>×</button></span></div>}
        {confirm && <div role="alertdialog" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><span>{confirm.type === 'dataset' ? `Remove “${confirm.name}” from the workspace? Source CSV files are not deleted.` : 'Delete this prepared export and its files?'}</span><span className="flex gap-2"><button className="secondary-btn" onClick={() => setConfirm(null)}>Cancel</button><button className="primary-btn !bg-rose-600" onClick={doDelete}>Delete</button></span></div>}

        {!loaded && <div className="panel p-10 text-center text-sm text-slate-500" role="status">Loading workspace…</div>}

        {loaded && page === 'Overview' && <>
          <section className="flex flex-wrap items-end justify-between gap-4"><div><span className="pill"><i className="online-dot" /> DATA QUALITY, MADE VISIBLE</span><h2 className="mt-4 text-3xl font-semibold tracking-[-.04em] sm:text-[36px]">Know your data before you model.</h2><p className="mt-2 max-w-2xl text-sm text-slate-500">Upload → Overview → Investigate → Prepare → Validate → Compare → Export. Your source data is never modified.</p></div></section>
          {!dataset ? <Empty title="Start with a dataset" action={<><button onClick={() => picker.current?.click()} className="primary-btn">Upload CSV</button><button onClick={addCic} disabled={busy} className="secondary-btn">Use local CIC-IDS2017</button></>}>Upload a CSV or register local CIC-IDS2017 files. Profiling scans in chunks and never changes your source data.</Empty>
            : !profile ? <section className="panel flex flex-wrap items-center justify-between gap-4 p-5"><div><div className="eyebrow text-indigo-600">SELECTED DATASET</div><h3 className="mt-1 text-xl font-semibold">{dataset.name}</h3><p className="mt-1 text-xs text-slate-500">{dataset.file_names?.join(', ')} · {mb(dataset.size_bytes)} MB</p></div><button disabled={busy || running(job)} onClick={() => profileDataset(dataset.id)} className="primary-btn">Run profile</button></section>
              : <>
                <section className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-3"><div className="flex items-center gap-3"><div className="big-icon small">▤</div><div><div className="text-sm font-semibold">{dataset.name}</div><div className="text-[10px] text-slate-400">{dataset.file_names.length} file(s) · Profiled {when(profile.created_at)}</div></div></div><div className="flex gap-2"><button disabled={busy || running(job)} onClick={() => profileDataset(dataset.id)} className="secondary-btn">Refresh profile</button><button onClick={() => go('Investigate')} className="secondary-btn">Investigate</button><button onClick={() => go('Prepare')} className="primary-btn">Prepare data →</button></div></section>
                <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">{metric('Rows scanned', num(profile.rows), 'Full dataset · chunked scan', '▤', 'indigo')}{metric('Columns', profile.columns, num(profile.dtypes.filter((c) => c.constant).length) + ' constant', '▦', 'teal')}{metric('Missing + infinite', num(profile.missing_cells + infinite(profile)), num(profile.missing_cells) + ' missing · ' + num(infinite(profile)) + ' infinite', '!', 'amber')}{metric('Exact duplicates', num(profile.duplicate_rows), 'Repeated feature and label rows', '⧉', 'slate')}</section>
                <section className="grid gap-5 xl:grid-cols-[1.2fr_.8fr]">
                  <div className="panel p-5"><div className="flex items-start justify-between"><div><h3 className="font-semibold">Quality signals</h3><p className="mt-1 text-xs text-slate-400">Most severe first. Findings are explained and never auto-corrected.</p></div><span className="pill neutral">{issues.length} findings</span></div>
                    <div className="mt-4 space-y-2">{issues.slice(0, 5).map((issue, i) => <div key={i} className="flex items-start gap-3 rounded-xl border border-slate-100 p-3"><Sev severity={issue.severity} /><div className="min-w-0 flex-1"><div className="flex flex-wrap gap-2 text-xs font-semibold">{issue.title}{issue.column && <span className="rounded bg-slate-100 px-1.5 text-slate-500">{issue.column}</span>}</div><p className="mt-1 text-[11px] leading-relaxed text-slate-500">{issue.explanation}</p></div><b className="text-xs text-slate-600">{num(issue.count)}</b></div>)}{!issues.length && <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800">No issues detected.</div>}</div>
                    {issues.length > 0 && <button className="mt-4 text-xs font-semibold text-indigo-600" onClick={() => go('Investigate')}>View all {issues.length} findings with recommendations →</button>}</div>
                  <div className="panel p-5"><div className="flex justify-between"><div><h3 className="font-semibold">Class distribution</h3><p className="mt-1 text-xs text-slate-400">{profile.label_column ? 'Target: ' + profile.label_column : 'No target detected'}</p></div><span className="pill">{classes.length} classes</span></div>
                    <div className="mt-5 space-y-3">{classes.slice(0, 8).map((row, i) => <div key={row.label}><div className="mb-1 flex justify-between gap-2 text-[10px]"><span className="truncate font-medium text-slate-600">{row.label}</span><span className="shrink-0 text-slate-400">{num(row.count)} · {row.percent}%</span></div><div className="h-1.5 rounded-full bg-slate-100"><div className={'h-full rounded-full ' + (rareLabels.has(row.label) ? 'bg-amber-400' : i ? 'bg-teal-400' : 'bg-indigo-500')} style={{ width: Math.max(.7, row.percent) + '%' }} /></div></div>)}{!classes.length && <p className="text-xs text-slate-400">No target column, so no class distribution.</p>}</div>
                    {classes.length > 8 && <button className="mt-4 text-xs font-semibold text-indigo-600" onClick={() => go('Investigate')}>View all {classes.length} classes →</button>}
                    <div className="mt-5 border-t border-slate-100 pt-3 text-[10px] text-slate-400">IQR outliers estimated on {num(profile.outlier_sample_rows)} deterministic sample rows; none are removed.</div></div>
                </section>
                <section className="panel overflow-hidden"><div className="flex items-center justify-between px-5 py-4"><div><h3 className="font-semibold">Column profile</h3><p className="mt-1 text-xs text-slate-400">Data types, missingness, infinity and constants</p></div><span className="text-xs text-slate-400">{profile.dtypes.length} columns</span></div><ColumnTable profile={profile} /></section>
              </>}
        </>}

        {loaded && page === 'Investigate' && needProfile(() => <>
          <section className="panel flex flex-wrap items-center justify-between gap-3 p-5"><div className="max-w-2xl"><h2 className="text-lg font-semibold">Recommended recipe</h2><ul className="mt-2 space-y-1 text-xs text-slate-500">{rec.why.map((w) => <li key={w}>• {w}</li>)}</ul></div><button onClick={applyRecipe} className="primary-btn">Apply recipe →</button></section>
          <section className="panel p-5"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="font-semibold">Findings</h3><p className="mt-1 text-xs text-slate-400">Each finding explains what was seen and what to do. Nothing is changed automatically.</p></div><div className="flex gap-1" role="group" aria-label="Severity filter">{['all', 'warning', 'info'].map((s) => <button key={s} onClick={() => setSeverity(s)} className={s === severity ? 'primary-btn !py-1.5' : 'secondary-btn !py-1.5'}>{s === 'all' ? 'All' : s === 'warning' ? 'Warnings' : 'Info'}</button>)}</div></div>
            <div className="mt-4 space-y-2">{shownIssues.map((issue, i) => <div key={i} className="flex items-start gap-3 rounded-xl border border-slate-100 p-3"><Sev severity={issue.severity} /><div className="min-w-0 flex-1"><div className="flex flex-wrap gap-2 text-xs font-semibold">{issue.title}{issue.column && <span className="rounded bg-slate-100 px-1.5 text-slate-500">{issue.column}</span>}</div><p className="mt-1 text-[11px] leading-relaxed text-slate-500">{issue.explanation}</p>{issue.recommendation && <p className="mt-1 text-[11px] leading-relaxed text-indigo-700"><b>Recommendation:</b> {issue.recommendation}</p>}{issue.classes?.length > 0 && <p className="mt-1 text-[11px] text-slate-500">Classes: {issue.classes.map((c) => c.label + ' (' + num(c.count) + ')').join(', ')}</p>}</div><b className="text-xs text-slate-600">{num(issue.count)}</b></div>)}{!shownIssues.length && <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800">{issues.length ? 'No findings at this severity.' : 'No issues detected.'}</div>}</div></section>
          <section className="grid gap-5 xl:grid-cols-2">
            <div className="panel p-5"><h3 className="font-semibold">Duplicates</h3><p className="mt-1 text-xs text-slate-400">Rows with identical feature and label values.</p>{dup ? <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">{[['Global exact repeats', dup.exact_duplicate_rows_global], ['Within-file repeats', dup.exact_duplicate_rows_within_file], ['Only across files', dup.exact_duplicates_only_across_files], ['Conflicting-label rows', dup.label_conflict_rows]].map(([k, v]) => <div key={k} className="rounded-xl bg-slate-50 p-3"><dt className="text-[10px] text-slate-400">{k}</dt><dd className="mt-1 text-base font-semibold">{num(v)}</dd></div>)}</dl> : <p className="mt-4 text-xs text-slate-400">No duplicate detail in this profile. Refresh the profile.</p>}</div>
            <div className="panel p-5"><h3 className="font-semibold">Constant columns</h3><p className="mt-1 text-xs text-slate-400">Columns with a single value carry no signal.</p><div className="mt-4 flex flex-wrap gap-2">{(profile.constant_columns || []).map((c) => <span key={c} className="pill neutral">{c}</span>)}{!profile.constant_columns?.length && <span className="text-xs text-slate-400">None detected.</span>}</div></div>
          </section>
          <section className="panel overflow-hidden"><div className="px-5 py-4"><h3 className="font-semibold">Outliers</h3><p className="mt-1 text-xs text-slate-400">IQR rule on {num(profile.outlier_sample_rows)} deterministic sample rows. Estimates only; no rows are removed.</p></div>{profile.outliers?.length ? <div className="soft-scroll overflow-x-auto"><table className="w-full min-w-[520px] text-left text-xs"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400"><tr><th className="px-4 py-3">Column</th><th className="px-4 py-3 text-right">Outlier rows</th><th className="px-4 py-3 text-right">Estimated share</th></tr></thead><tbody>{profile.outliers.map((o) => <tr key={o.column} className="border-t border-slate-100"><td className="px-4 py-3 font-medium">{o.column}</td><td className="px-4 py-3 text-right">{num(o.sample_outlier_rows)} / {num(o.sample_rows)}</td><td className="px-4 py-3 text-right">{o.estimated_percent}%</td></tr>)}</tbody></table></div> : <p className="px-5 pb-5 text-xs text-slate-400">No outliers detected in the sample.</p>}</section>
          <section className="panel p-5"><div className="flex justify-between"><div><h3 className="font-semibold">Class distribution</h3><p className="mt-1 text-xs text-slate-400">{profile.label_column ? 'Target: ' + profile.label_column + '. Amber = rare class.' : 'No target detected'}</p></div><span className="pill">{classes.length} classes</span></div><div className="soft-scroll mt-4 max-h-[420px] space-y-3 overflow-y-auto pr-2">{classes.map((row) => <div key={row.label}><div className="mb-1 flex justify-between gap-2 text-[11px]"><span className="truncate font-medium text-slate-600">{row.label}{rareLabels.has(row.label) && <span className="ml-2 rounded bg-amber-50 px-1 text-[9px] text-amber-700">RARE</span>}</span><span className="shrink-0 text-slate-400">{num(row.count)} · {row.percent}%</span></div><div className="h-1.5 rounded-full bg-slate-100"><div className={'h-full rounded-full ' + (rareLabels.has(row.label) ? 'bg-amber-400' : 'bg-teal-400')} style={{ width: Math.max(.7, row.percent) + '%' }} /></div></div>)}{!classes.length && <p className="text-xs text-slate-400">None.</p>}</div></section>
          <section className="panel overflow-hidden"><div className="px-5 py-4"><h3 className="font-semibold">All columns</h3></div><ColumnTable profile={profile} /></section>
        </>)}

        {loaded && page === 'Datasets' && <section className="space-y-4"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-2xl font-semibold">Dataset library</h2><p className="mt-1 text-sm text-slate-500">Uploaded and registered CSV sources with their profiling status.</p></div><div className="flex gap-2"><button className="secondary-btn" disabled={busy} onClick={addCic}>＋ Add CIC-IDS2017</button><button className="primary-btn" onClick={() => picker.current?.click()}>↑ Upload CSV</button></div></div>
          {datasets.map((d) => <div key={d.id} className={'panel flex flex-wrap items-center gap-4 p-4 ' + (d.id === datasetId ? 'ring-2 ring-indigo-100' : '')}><div className="big-icon small">▤</div><div className="min-w-0 flex-1"><b className="block truncate text-sm">{d.name}</b><span className="text-[10px] text-slate-400">{d.file_names.join(', ')} · {mb(d.size_bytes)} MB</span><span className="mt-1 block text-xs text-slate-500">{d.profile ? num(d.profile.rows) + ' rows · ' + d.profile.columns + ' columns' : 'Not profiled'}</span></div>
            <span className={'pill ' + (d.source_status === 'available' ? 'neutral' : '')}>{d.source_status === 'available' ? (d.profile ? 'Profiled' : 'Not profiled') : 'Source missing'}</span><span className="pill neutral">{d.kind === 'local_read_only' ? 'Read-only source' : 'Upload'}</span>
            {!d.profile && d.source_status === 'available' && <button className="secondary-btn" disabled={busy || running(job)} onClick={() => profileDataset(d.id)}>Profile</button>}
            <button className="secondary-btn" onClick={() => guard(() => selectDataset(d.id))}>Open</button>
            <button className="secondary-btn" aria-label={'Remove ' + d.name} onClick={() => setConfirm({ type: 'dataset', id: d.id, name: d.name })}>Remove</button></div>)}
          {!datasets.length && <Empty title="No datasets yet" action={<button className="primary-btn" onClick={() => picker.current?.click()}>Upload CSV</button>}>Upload a CSV to begin.</Empty>}</section>}

        {loaded && page === 'Prepare' && <section className="grid gap-5 xl:grid-cols-[.9fr_1.1fr]">
          <div className="space-y-4"><div><h2 className="text-2xl font-semibold">Preparation recipe</h2><p className="mt-1 text-sm text-slate-500">Choose each transform explicitly. Source files remain unchanged.</p></div>
            {needProfile(() => <div className="panel space-y-4 p-5"><div className="flex items-center justify-between gap-2 rounded-xl bg-slate-50 p-3 text-sm font-semibold"><span className="truncate">{dataset.name}<span className="ml-2 text-xs font-normal text-slate-400">{num(profile.rows)} rows</span></span><button className="text-xs font-semibold text-indigo-600" onClick={applyRecipe}>Use recommended</button></div>
              <div className="form-grid">
                <Select label="Target column" help={HELP.target} value={target} set={setTarget}><option value="">No target</option>{profile.column_names.map((c) => <option key={c}>{c}</option>)}</Select>
                <Select label="Dataset size" help={HELP.sample} value={sample} set={setSample}><option value="0.1">10% sample</option><option value="0.25">25% sample</option><option value="1">Full dataset</option></Select>
                <Select label="Test split" help={HELP.test} value={testSize} set={setTestSize}><option value="0.2">20% test</option><option value="0.25">25% test</option><option value="0.3">30% test</option></Select>
                <Select label="Duplicate policy" help={HELP.duplicate} value={duplicate} set={setDuplicate}><option value="keep">Keep all · report only</option><option value="drop_within_file">Remove within-file repeats</option><option value="drop_exact">Remove global exact repeats</option></Select>
                <Select label="Missing numeric values" help={HELP.imputer} value={imputer} set={setImputer}><option value="median">Median</option><option value="mean">Mean</option><option value="most_frequent">Most frequent</option></Select>
                <Select label="Categorical encoding" help={HELP.encoding} value={encoding} set={setEncoding}><option value="onehot">One-hot</option><option value="ordinal">Ordinal</option></Select>
                <Select label="Numeric scaling" help={HELP.scaler} value={scaler} set={setScaler}><option value="robust">Robust</option><option value="standard">Standard</option><option value="minmax">Min-max</option><option value="none">None</option></Select>
                <Select label="Feature selection" help={HELP.selection} value={selection} set={setSelection}><option value="none">None</option><option value="variance">Remove zero variance</option><option value="kbest_f" disabled={!target}>Top k · ANOVA F{target ? '' : ' (needs target)'}</option></Select>
                <label>Random seed<Tip text="Same seed and options always produce identical files." /><input type="number" min="0" value={seed} onChange={(e) => setSeed(e.target.value)} aria-label="Random seed" className="mt-1.5 block w-full rounded-[10px] border border-slate-200 bg-white px-2.5 py-2 text-xs text-slate-700" /></label>
              </div>
              <div className="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] leading-relaxed text-amber-900"><b>Review:</b> rows are removed only if you select a duplicate policy. A sample is not a full-data result. Rare classes may be missing from the test split; the run reports coverage per class.</div>
              <button onClick={prepare} disabled={busy || running(job)} className="primary-btn w-full">{running(job) ? 'Preparing…' : '✦ Prepare and validate'}</button></div>)}</div>
          <div className="space-y-4">
            <div className="panel p-5"><h3 className="font-semibold">Validation and comparison</h3><p className="mt-1 text-xs text-slate-400">Latest prepared run for this dataset.</p>
              {run ? <>
                <div className={'mt-4 rounded-xl p-3 text-xs font-semibold ' + (runOk ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700')}>{runOk ? '✓ Validation passed: no missing or infinite values in exported features.' : '✕ Validation found remaining missing or infinite feature values. See quality_report.json.'}</div>
                <div className="mt-4 grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-50 p-4"><span className="text-[10px] text-slate-400">Before · source sample</span><b className="mt-2 block text-lg">{num(run.comparison?.before_sample_preparation?.rows)} rows</b><span className="block text-xs text-slate-500">{run.comparison?.before_sample_preparation?.columns} columns</span><span className="block text-xs text-slate-500">{num(run.comparison?.before_sample_preparation?.missing_cells)} missing · {num(run.comparison?.before_sample_preparation?.infinite_cells)} infinite</span></div>
                  <div className="rounded-xl bg-indigo-50 p-4"><span className="text-[10px] text-indigo-500">After · prepared</span><b className="mt-2 block text-lg">{num(run.rows.train + run.rows.test)} rows</b><span className="block text-xs text-indigo-600">{num(run.rows.train)} train · {num(run.rows.test)} test</span><span className="block text-xs text-indigo-600">{num(run.comparison?.processed_sample?.transformed_features)} features · {num(run.comparison?.processed_sample?.duplicate_rows_removed)} duplicates removed</span><span className="block text-xs text-indigo-600">{num(run.comparison?.processed_sample?.missing_feature_cells_after)} missing · {num(run.comparison?.processed_sample?.infinite_feature_cells_after)} infinite</span></div></div>
                {run.config && <p className="mt-3 text-[11px] text-slate-500">Recipe: {run.config.duplicate_policy} duplicates · {run.config.numeric_imputer} imputer · {run.config.encoding} · {run.config.scaler} scaling · selection {run.config.feature_selection} · seed {run.config.seed} · {Math.round(run.sample_fraction * 100)}% of rows{run.target_column ? ' · target ' + run.target_column : ' · no target'}</p>}
                {run.train_test_overlap && run.train_test_overlap.test_rows > 0 && <p className="mt-2 text-[11px] text-slate-500">Train/test overlap: {num(run.train_test_overlap.test_rows_also_in_train)} of {num(run.train_test_overlap.test_rows)} test rows ({run.train_test_overlap.percent_of_test}%) are exact copies of training rows.</p>}
                {run.warnings?.length > 0 && <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] leading-relaxed text-amber-900"><b>{run.warnings.length} warning(s)</b><ul className="mt-1 space-y-1">{run.warnings.map((w) => <li key={w}>• {w}</li>)}</ul></div>}
                {run.class_coverage?.length > 0 && <details className="mt-4"><summary className="cursor-pointer text-xs font-semibold text-indigo-600">Class coverage ({run.class_coverage.length} classes)</summary><div className="soft-scroll mt-2 max-h-64 overflow-auto"><table className="w-full text-left text-[11px]"><thead className="text-[10px] uppercase text-slate-400"><tr><th className="py-1">Class</th><th className="py-1 text-right">Train</th><th className="py-1 text-right">Test</th><th className="py-1 pl-3">Flags</th></tr></thead><tbody>{run.class_coverage.map((c) => <tr key={c.label} className="border-t border-slate-100"><td className="py-1.5">{c.label}</td><td className="py-1.5 text-right">{num(c.train)}</td><td className="py-1.5 text-right">{num(c.test)}</td><td className={'py-1.5 pl-3 ' + (c.flags.length ? 'text-amber-700' : 'text-slate-400')}>{c.flags.join(', ') || 'ok'}</td></tr>)}</tbody></table></div></details>}
                <div className="mt-4 grid gap-2 sm:grid-cols-2">{FILES.map(([f, d]) => <a key={f} className="download-link" href={'/api/preparations/' + run.id + '/files/' + f} download title={d}>⇩ {f}</a>)}</div></>
                : <div className="mt-5 rounded-xl border border-dashed p-8 text-center"><div className="big-icon small mx-auto">◈</div><p className="mt-3 text-sm font-semibold">No prepared run yet</p><p className="mt-1 text-xs text-slate-400">Configure the recipe and prepare. Validation and comparison appear here.</p></div>}</div>
            <div className="panel p-5"><h3 className="font-semibold">Included in every run</h3><div className="mt-4 grid gap-3 text-xs text-slate-500">{FILES.map(([f, d]) => <div key={f} className="flex gap-2"><span className="text-teal-600">✓</span><span><b className="text-slate-700">{f}</b> · {d}</span></div>)}</div></div>
          </div></section>}

        {loaded && page === 'Exports' && <section className="space-y-4"><div><h2 className="text-2xl font-semibold">Prepared exports</h2><p className="mt-1 text-sm text-slate-500">Download data, recipe and validation reports.{dataset && datasetRuns.length ? ` ${datasetRuns.length} run(s) for the selected dataset.` : ''}</p></div>
          {runs.map((r) => <div key={r.id} className="panel space-y-3 p-4"><div className="flex flex-wrap items-center gap-4"><div className="big-icon small">⇩</div><div className="min-w-0 flex-1"><b className="block truncate">{r.dataset_name}</b><span className="text-xs text-slate-400">{when(r.created_at)} · {Math.round(r.sample_fraction * 100)}% {r.sample_fraction < 1 ? 'sample' : 'full'} · {num(r.rows.train)} train / {num(r.rows.test)} test{r.warnings?.length ? ' · ' + r.warnings.length + ' warning(s)' : ''}</span></div><button className="secondary-btn" aria-label={'Delete export ' + r.id} onClick={() => setConfirm({ type: 'run', id: r.id })}>Delete</button></div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{FILES.map(([f, d]) => <a key={f} className="download-link" href={'/api/preparations/' + r.id + '/files/' + f} download title={d}>⇩ {f}</a>)}</div></div>)}
          {!runs.length && <Empty icon="⇩" title="No prepared exports yet" action={<button className="primary-btn" onClick={() => go('Prepare')}>Go to Prepare</button>}>Create a run from a profiled dataset.</Empty>}</section>}
        <footer className="flex justify-between border-t border-slate-200 pt-4 text-[10px] text-slate-400"><span>DataLens · Local-first dataset intelligence</span><span>Original files stay untouched</span></footer>
      </div>
    </main>
  </div>
}

function Select({ label, help, value, set, children }) { return <label>{label}<Tip text={help} /><select value={value} onChange={(e) => set(e.target.value)} aria-label={label}>{children}</select></label> }

function ColumnTable({ profile }) {
  return <div className="soft-scroll overflow-x-auto"><table className="w-full min-w-[650px] text-left text-xs"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400"><tr>{['Column', 'Type', 'Missing', '+∞', '−∞', 'Signal'].map((x, i) => <th key={x} className={'px-4 py-3 font-semibold ' + (i > 1 && i < 5 ? 'text-right' : '')}>{x}</th>)}</tr></thead><tbody>{profile.dtypes.map((c) => <tr key={c.column} className="border-t border-slate-100"><td className="px-4 py-3 font-medium">{c.column}{c.column === profile.label_column && <span className="ml-2 rounded bg-indigo-50 px-1 text-[9px] text-indigo-600">TARGET</span>}</td><td className="px-4 py-3 text-slate-500">{c.dtype}</td><td className={'px-4 py-3 text-right ' + (c.missing_cells ? 'text-amber-700' : 'text-slate-400')}>{num(c.missing_cells)}</td><td className={'px-4 py-3 text-right ' + (c.positive_infinity_cells ? 'text-amber-700' : 'text-slate-400')}>{num(c.positive_infinity_cells)}</td><td className={'px-4 py-3 text-right ' + (c.negative_infinity_cells ? 'text-amber-700' : 'text-slate-400')}>{num(c.negative_infinity_cells)}</td><td className="px-4 py-3">{c.constant ? <span className="pill neutral">Constant</span> : '—'}</td></tr>)}</tbody></table></div>
}

export default App
