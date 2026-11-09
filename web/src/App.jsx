import { useCallback, useEffect, useRef, useState } from 'react'

const api = '/api'
async function call(path, options = {}) {
  const res = await fetch(api + path, options)
  const data = res.headers.get('content-type')?.includes('json') ? await res.json() : null
  if (!res.ok) throw new Error(data?.detail || 'Request failed')
  return data
}
const icons = { Overview: '◫', Datasets: '▤', Prepare: '◈', Exports: '⇩' }
const num = (n) => Number(n || 0).toLocaleString()

function App() {
  const [datasets, setDatasets] = useState([])
  const [runs, setRuns] = useState([])
  const [datasetId, setDatasetId] = useState('')
  const [dataset, setDataset] = useState(null)
  const [page, setPage] = useState('Overview')
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [target, setTarget] = useState('')
  const [sample, setSample] = useState('0.1')
  const [duplicate, setDuplicate] = useState('keep')
  const [imputer, setImputer] = useState('median')
  const [encoding, setEncoding] = useState('onehot')
  const [scaler, setScaler] = useState('robust')
  const [selection, setSelection] = useState('none')
  const [testSize, setTestSize] = useState('0.2')
  const picker = useRef(null)
  const profile = dataset?.profile

  const refresh = useCallback(async (id = datasetId) => {
    const [ds, pr] = await Promise.all([call('/datasets'), call('/preparations')])
    setDatasets(ds.datasets); setRuns(pr.preparations)
    if (id) {
      const result = await call('/datasets/' + id)
      setDataset(result.dataset)
    }
  }, [datasetId])
  useEffect(() => { refresh('').catch((e) => setError(e.message)) }, [])
  useEffect(() => {
    if (!job?.id || ['complete', 'failed'].includes(job.status)) return
    const timer = setInterval(async () => {
      try {
        const result = await call('/jobs/' + job.id)
        setJob(result.job)
        if (result.job.status === 'complete') await refresh(result.job.kind === 'profile' ? result.job.dataset_id : datasetId)
      } catch (e) { setError(e.message) }
    }, 1100)
    return () => clearInterval(timer)
  }, [job?.id, job?.status, datasetId, refresh])
  useEffect(() => { if (profile?.label_column && !target) setTarget(profile.label_column) }, [profile, target])

  const selectDataset = async (id) => {
    const result = await call('/datasets/' + id)
    setDatasetId(id); setDataset(result.dataset); setPage('Overview')
    if (result.dataset.profile?.label_column) setTarget(result.dataset.profile.label_column)
  }
  const profileDataset = async (id) => {
    setError(''); setJob(null)
    const result = await call('/datasets/' + id + '/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    setJob(result.job); await selectDataset(id)
  }
  const upload = async (file) => {
    if (!file) return
    setBusy(true); setError('')
    try {
      const result = await call('/datasets/upload?filename=' + encodeURIComponent(file.name), { method: 'POST', headers: { 'Content-Type': 'text/csv' }, body: file })
      await refresh(result.dataset.id); await profileDataset(result.dataset.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const addCic = async () => {
    setBusy(true); setError('')
    try {
      const result = await call('/datasets/import-cicids', { method: 'POST' })
      await refresh(result.dataset.id); await profileDataset(result.dataset.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const prepare = async () => {
    setError(''); setJob(null)
    try {
      const body = { target_column: target || null, sample_fraction: Number(sample), test_size: Number(testSize), seed: 42,
        duplicate_policy: duplicate, numeric_imputer: imputer, encoding, scaler, feature_selection: selection, missing_indicator: true }
      const result = await call('/datasets/' + datasetId + '/prepare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      setJob(result.job)
    } catch (e) { setError(e.message) }
  }

  const nav = ['Overview', 'Datasets', 'Prepare', 'Exports']
  const latestRun = runs.find((r) => r.dataset_id === datasetId) || runs[0]
  const metric = (label, value, detail, glyph, tint) => <div className="panel p-5"><div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-500">{label}</span><span className={'metric-icon ' + tint}>{glyph}</span></div><div className="mt-4 text-[27px] font-semibold tracking-tight">{value}</div><div className="mt-1 text-[11px] text-slate-400">{detail}</div></div>

  return <div className="min-h-screen bg-[#f5f7fb] text-[#142338]">
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-[244px] flex-col border-r border-slate-200 bg-white px-4 py-5 lg:flex">
      <div className="flex items-center gap-3 px-2"><div className="brand-mark">✦</div><div><div className="text-[17px] font-bold">DataLens</div><div className="eyebrow">DATA WORKSPACE</div></div></div>
      <div className="eyebrow mt-10 px-3">WORKSPACE</div><nav className="mt-3 space-y-1">{nav.map((n) => <button key={n} onClick={() => setPage(n)} className={'nav-item ' + (page === n ? 'nav-active' : '')}><span className="w-5 text-center text-base">{icons[n]}</span>{n === 'Prepare' ? 'Prepare data' : n}{n === 'Datasets' && <span className="ml-auto rounded-full bg-white px-2 text-[10px] text-slate-400">{datasets.length}</span>}</button>)}</nav>
      <div className="mt-9 flex items-center justify-between px-3"><span className="eyebrow">YOUR DATASETS</span><button title="Upload CSV" onClick={() => picker.current?.click()} className="text-indigo-600">＋</button></div>
      <div className="soft-scroll mt-3 flex-1 space-y-1 overflow-y-auto">{datasets.map((d) => <button key={d.id} onClick={() => selectDataset(d.id)} className={'dataset-link ' + (datasetId === d.id ? 'dataset-link-active' : '')}><span className="block truncate text-xs font-semibold">{d.name}</span><span className="mt-1 block text-[10px] text-slate-400">{d.profile ? num(d.profile.rows) + ' rows' : 'Ready to profile'}</span></button>)}</div>
      <div className="mt-4 rounded-2xl bg-slate-50 p-3"><div className="flex items-center gap-2 text-xs font-semibold"><i className="online-dot"/>Local workspace</div><p className="mt-1 text-[10px] leading-relaxed text-slate-500">Your data stays on this machine.</p></div>
    </aside>
    <main className="min-h-screen lg:pl-[244px]">
      <header className="sticky top-0 z-10 flex h-[72px] items-center justify-between border-b border-slate-200/70 bg-[#f5f7fb]/90 px-5 backdrop-blur-xl sm:px-8">
        <div className="flex items-center gap-3"><div className="brand-mark lg:hidden">✦</div><div><div className="text-[10px] text-slate-400">Workspace <span className="mx-1">/</span> {page}</div><h1 className="text-[17px] font-semibold">{page === 'Prepare' ? 'Prepare a dataset' : page === 'Datasets' ? 'Dataset library' : page === 'Exports' ? 'Prepared exports' : 'Dataset overview'}</h1></div></div>
        <div className="flex gap-2"><button onClick={addCic} disabled={busy} className="hidden rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 sm:block">＋ Add CIC-IDS2017</button><button onClick={() => picker.current?.click()} disabled={busy} className="rounded-xl bg-indigo-600 px-3.5 py-2.5 text-xs font-semibold text-white shadow-md shadow-indigo-200 hover:bg-indigo-700 disabled:opacity-50">↑ Upload CSV</button><input ref={picker} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => upload(e.target.files?.[0])}/></div>
      </header>
      <div className="mx-auto max-w-[1460px] space-y-5 px-5 py-6 sm:px-8 sm:py-8">
        {error && <div className="flex justify-between rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}<button onClick={() => setError('')}>×</button></div>}
        {job && !['complete', 'failed'].includes(job.status) && <div className="panel flex items-center gap-4 p-4"><span className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-100 border-t-indigo-600"/><div className="flex-1"><div className="flex justify-between text-xs font-semibold"><span>{job.kind === 'profile' ? 'Profiling dataset' : 'Preparing data'}</span><span>{Math.round(job.progress * 100)}%</span></div><p className="mt-1 text-[11px] text-slate-500">{job.message}</p><div className="mt-2 h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-600" style={{ width: (job.progress * 100) + '%' }}/></div></div></div>}
        {job?.status === 'failed' && <div className="rounded-xl bg-rose-50 p-3 text-xs text-rose-700">{job.error}</div>}

        {page === 'Overview' && <><section className="flex flex-wrap items-end justify-between gap-4"><div><span className="pill"><i className="online-dot"/> DATA QUALITY, MADE VISIBLE</span><h2 className="mt-4 text-3xl font-semibold tracking-[-.04em] sm:text-[36px]">Know your data before you model.</h2><p className="mt-2 max-w-2xl text-sm text-slate-500">Profile a dataset, understand its quality signals, then prepare a reproducible train/test export.</p></div><button onClick={addCic} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold">Use local CIC-IDS2017</button></section>
          {!dataset ? <section className="panel grid min-h-[260px] place-items-center border-dashed p-8 text-center"><div><div className="big-icon">▤</div><h3 className="mt-4 text-lg font-semibold">Start with a dataset</h3><p className="mx-auto mt-1 max-w-md text-sm text-slate-500">Upload a CSV or register local CIC-IDS2017 files. Profiling scans in chunks and never changes your source data.</p><div className="mt-5 flex justify-center gap-2"><button onClick={() => picker.current?.click()} className="primary-btn">Upload CSV</button><button onClick={addCic} className="secondary-btn">Use local dataset</button></div></div></section>
            : !profile ? <section className="panel flex flex-wrap items-center justify-between gap-4 p-5"><div><div className="eyebrow text-indigo-600">SELECTED DATASET</div><h3 className="mt-1 text-xl font-semibold">{dataset.name}</h3><p className="mt-1 text-xs text-slate-500">{dataset.file_names?.join(', ')} · {(dataset.size_bytes / 1048576).toFixed(1)} MB</p></div><button onClick={() => profileDataset(dataset.id)} className="primary-btn">Run profile</button></section>
              : <>
                <section className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-3"><div className="flex items-center gap-3"><div className="big-icon small">▤</div><div><div className="text-sm font-semibold">{dataset.name}</div><div className="text-[10px] text-slate-400">{dataset.file_names.length} file(s) · Profiled {new Date(profile.created_at).toLocaleString()}</div></div></div><div className="flex gap-2"><button onClick={() => profileDataset(dataset.id)} className="secondary-btn">Refresh profile</button><button onClick={() => setPage('Prepare')} className="primary-btn">Prepare data　→</button></div></section>
                <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">{metric('Rows scanned', num(profile.rows), 'Full dataset · chunked scan', '▤', 'indigo')}{metric('Columns', profile.columns, 'Fields detected', '▦', 'teal')}{metric('Missing + infinite', num(profile.missing_cells + profile.positive_infinity_cells + profile.negative_infinity_cells), num(profile.missing_cells) + ' missing · ' + num(profile.positive_infinity_cells + profile.negative_infinity_cells) + ' infinite', '!', 'amber')}{metric('Exact duplicates', num(profile.duplicate_rows), 'Repeated feature and label rows', '⧉', 'slate')}</section>
                <section className="grid gap-5 xl:grid-cols-[1.2fr_.8fr]"><div className="panel p-5"><div className="flex items-start justify-between"><div><h3 className="font-semibold">Quality signals</h3><p className="mt-1 text-xs text-slate-400">Findings are explained and never auto-corrected.</p></div><span className="pill neutral">{profile.issues.length} findings</span></div><div className="mt-4 space-y-2">{profile.issues.slice(0, 7).map((issue, i) => <div key={i} className="flex items-start gap-3 rounded-xl border border-slate-100 p-3"><span className={issue.severity === 'warning' ? 'text-amber-600' : 'text-indigo-500'}>{issue.severity === 'warning' ? '⚠' : '✦'}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap gap-2 text-xs font-semibold">{issue.title}{issue.column && <span className="rounded bg-slate-100 px-1.5 text-slate-500">{issue.column}</span>}</div><p className="mt-1 text-[11px] leading-relaxed text-slate-500">{issue.explanation}</p></div><b className="text-xs text-slate-600">{num(issue.count)}</b></div>)}{!profile.issues.length && <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800">No issues detected.</div>}</div></div>
                  <div className="panel p-5"><div className="flex justify-between"><div><h3 className="font-semibold">Class distribution</h3><p className="mt-1 text-xs text-slate-400">{profile.label_column ? 'Target: ' + profile.label_column : 'No target detected'}</p></div><span className="pill">{profile.class_distribution.length} classes</span></div><div className="mt-5 space-y-3">{profile.class_distribution.slice(0, 8).map((row, i) => <div key={row.label}><div className="mb-1 flex justify-between gap-2 text-[10px]"><span className="truncate font-medium text-slate-600">{row.label}</span><span className="shrink-0 text-slate-400">{num(row.count)} · {row.percent}%</span></div><div className="h-1.5 rounded-full bg-slate-100"><div className={'h-full rounded-full ' + (i ? 'bg-teal-400' : 'bg-indigo-500')} style={{ width: Math.max(.7, row.percent) + '%' }}/></div></div>)}</div><div className="mt-5 border-t border-slate-100 pt-3 text-[10px] text-slate-400">IQR outliers estimated on {num(profile.outlier_sample_rows)} deterministic sample rows; none are removed.</div></div></section>
                <section className="panel overflow-hidden"><div className="flex items-center justify-between px-5 py-4"><div><h3 className="font-semibold">Column profile</h3><p className="mt-1 text-xs text-slate-400">Data types, missingness, infinity and constants</p></div><span className="text-xs text-slate-400">{profile.dtypes.length} columns</span></div><div className="soft-scroll overflow-x-auto"><table className="w-full min-w-[650px] text-left text-xs"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400"><tr>{['Column','Type','Missing','+∞','Signal'].map((x) => <th key={x} className="px-4 py-3 font-semibold">{x}</th>)}</tr></thead><tbody>{profile.dtypes.map((c) => <tr key={c.column} className="border-t border-slate-100"><td className="px-4 py-3 font-medium">{c.column}{c.column === profile.label_column && <span className="ml-2 rounded bg-indigo-50 px-1 text-[9px] text-indigo-600">TARGET</span>}</td><td className="px-4 py-3 text-slate-500">{c.dtype}</td><td className={'px-4 py-3 text-right ' + (c.missing_cells ? 'text-amber-700' : 'text-slate-400')}>{num(c.missing_cells)}</td><td className={'px-4 py-3 text-right ' + (c.positive_infinity_cells ? 'text-amber-700' : 'text-slate-400')}>{num(c.positive_infinity_cells)}</td><td className="px-4 py-3 text-right">{c.constant ? <span className="pill neutral">Constant</span> : '—'}</td></tr>)}</tbody></table></div></section>
              </>}
        </>}

        {page === 'Datasets' && <section className="space-y-4"><div><h2 className="text-2xl font-semibold">Dataset library</h2><p className="mt-1 text-sm text-slate-500">Local CSV sources and their profiling status.</p></div>{datasets.map((d) => <div key={d.id} className="panel flex flex-wrap items-center gap-4 p-4"><div className="big-icon small">▤</div><div className="min-w-0 flex-1"><b className="block truncate text-sm">{d.name}</b><span className="text-[10px] text-slate-400">{d.file_names.join(', ')} · {(d.size_bytes / 1048576).toFixed(1)} MB</span><span className="mt-1 block text-xs text-slate-500">{d.profile ? num(d.profile.rows) + ' rows · ' + d.profile.columns + ' columns' : 'Not profiled'}</span></div><span className="pill neutral">{d.kind === 'local_read_only' ? 'Read only source' : 'Local upload'}</span><button className="secondary-btn" onClick={() => selectDataset(d.id)}>Open</button></div>)}{!datasets.length && <div className="panel p-12 text-center text-sm text-slate-500">Upload a CSV to begin.</div>}</section>}

        {page === 'Prepare' && <section className="grid gap-5 xl:grid-cols-[.9fr_1.1fr]"><div className="space-y-4"><div><h2 className="text-2xl font-semibold">Preparation recipe</h2><p className="mt-1 text-sm text-slate-500">Choose each transform explicitly. Source files remain unchanged.</p></div>{!profile ? <div className="panel p-6"><b>Profile a dataset first</b><p className="mt-1 text-sm text-slate-500">Select a profiled dataset to configure preparation.</p></div> : <div className="panel space-y-4 p-5"><div className="rounded-xl bg-slate-50 p-3 text-sm font-semibold">{dataset.name}<span className="ml-2 text-xs font-normal text-slate-400">{num(profile.rows)} rows</span></div><div className="form-grid">
          <label>Target column<select value={target} onChange={(e) => setTarget(e.target.value)}>{profile.column_names.map((c) => <option key={c}>{c}</option>)}<option value="">No target</option></select></label>
          <label>Dataset size<select value={sample} onChange={(e) => setSample(e.target.value)}><option value="0.1">10% sample</option><option value="0.25">25% sample</option><option value="1">Full dataset</option></select></label>
          <label>Test split<select value={testSize} onChange={(e) => setTestSize(e.target.value)}><option value="0.2">20% test</option><option value="0.25">25% test</option><option value="0.3">30% test</option></select></label>
          <label>Duplicate policy<select value={duplicate} onChange={(e) => setDuplicate(e.target.value)}><option value="keep">Keep all · report only</option><option value="drop_within_file">Remove within-file repeats</option><option value="drop_exact">Remove global exact repeats</option></select></label>
          <label>Missing numeric values<select value={imputer} onChange={(e) => setImputer(e.target.value)}><option value="median">Median</option><option value="mean">Mean</option><option value="most_frequent">Most frequent</option></select></label>
          <label>Categorical encoding<select value={encoding} onChange={(e) => setEncoding(e.target.value)}><option value="onehot">One-hot</option><option value="ordinal">Ordinal</option></select></label>
          <label>Numeric scaling<select value={scaler} onChange={(e) => setScaler(e.target.value)}><option value="robust">Robust</option><option value="standard">Standard</option><option value="minmax">Min-max</option><option value="none">None</option></select></label>
          <label>Feature selection<select value={selection} onChange={(e) => setSelection(e.target.value)}><option value="none">None</option><option value="variance">Remove zero variance</option><option value="kbest_f" disabled={!target}>Top k · ANOVA F</option></select></label>
        </div><div className="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] leading-relaxed text-amber-900"><b>Review:</b> rows are removed only if you select a duplicate policy. A sample is not a full-data result. Rare classes may be underrepresented.</div><button onClick={prepare} disabled={!!job && ['queued','running'].includes(job.status)} className="primary-btn w-full">✦　Prepare and validate</button></div>}</div>
          <div className="space-y-4"><div className="panel p-5"><h3 className="font-semibold">Before / after comparison</h3><p className="mt-1 text-xs text-slate-400">Prepared outputs are checked for missing and infinite feature values.</p>{latestRun && latestRun.dataset_id === datasetId ? <><div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-50 p-4"><span className="text-[10px] text-slate-400">Before · selected sample</span><b className="mt-2 block text-lg">{num(latestRun.comparison?.before_sample_preparation?.rows)} rows</b><span className="text-xs text-slate-500">{latestRun.comparison?.before_sample_preparation?.columns} columns</span></div><div className="rounded-xl bg-indigo-50 p-4"><span className="text-[10px] text-indigo-500">After · selected run</span><b className="mt-2 block text-lg">{num(latestRun.rows.train + latestRun.rows.test)} rows</b><span className="text-xs text-indigo-600">{num(latestRun.rows.train)} train · {num(latestRun.rows.test)} test</span><span className="mt-1 block text-xs text-indigo-600">{latestRun.comparison?.processed_sample?.transformed_features} transformed features</span></div></div><div className="mt-4 text-xs font-semibold text-emerald-700">✓ Feature validation passed</div><div className="mt-4 flex flex-wrap gap-2">{['train.csv','test.csv','config.json','quality_report.json','quality_report.md','comparison.json'].map((f) => <a className="download-link" key={f} href={'/api/preparations/' + latestRun.id + '/files/' + f} download>{f}</a>)}</div></> : <div className="mt-5 rounded-xl border border-dashed p-8 text-center"><div className="big-icon small mx-auto">◈</div><p className="mt-3 text-sm font-semibold">Your recipe is ready</p><p className="mt-1 text-xs text-slate-400">Train-only fitting, transformed exports and validation appear here.</p></div>}</div><div className="panel p-5"><h3 className="font-semibold">Included in every run</h3><div className="mt-4 grid gap-3 text-xs text-slate-500">{['Train and test CSV exports','Reproducible preparation config','Quality report with explanations','Before/after comparison'].map((x) => <div key={x} className="flex gap-2"><span className="text-teal-600">✓</span>{x}</div>)}</div></div></div></section>}

        {page === 'Exports' && <section className="space-y-4"><div><h2 className="text-2xl font-semibold">Prepared exports</h2><p className="mt-1 text-sm text-slate-500">Download data, recipe and validation reports.</p></div>{runs.map((r) => <div key={r.id} className="panel flex flex-wrap items-center gap-4 p-4"><div className="big-icon small">⇩</div><div className="min-w-0 flex-1"><b className="block">{r.dataset_name}</b><span className="text-xs text-slate-400">{new Date(r.created_at).toLocaleString()} · {Math.round(r.sample_fraction * 100)}% {r.sample_fraction < 1 ? 'sample' : 'full'} · {num(r.rows.train)} train / {num(r.rows.test)} test</span></div><a className="primary-btn" href={'/api/preparations/' + r.id + '/files/train.csv'} download>Train CSV</a><a className="secondary-btn" href={'/api/preparations/' + r.id + '/files/quality_report.md'} download>Quality report</a></div>)}{!runs.length && <div className="panel p-12 text-center text-sm text-slate-500">No prepared exports yet. Create a run from a profiled dataset.</div>}</section>}
        <footer className="flex justify-between border-t border-slate-200 pt-4 text-[10px] text-slate-400"><span>DataLens · Local-first dataset intelligence</span><span>Original files stay untouched</span></footer>
      </div>
    </main>
  </div>
}

export default App
