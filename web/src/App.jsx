import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { call, post, running, mb } from './api.js'
import { num } from './components/ui.jsx'
const LandingPage = lazy(() => import('./pages/Landing/LandingPage.jsx'))
import ToastHost from './components/feedback/Toast.jsx'
import ConfirmDialog from './components/feedback/ConfirmDialog.jsx'
import Sidebar from './components/navigation/Sidebar.jsx'
import ProcessMap from './pages/ProcessMap.jsx'
import RecommendationsPage from './pages/RecommendationsPage.jsx'
import AnomalyAnalysis from './pages/AnomalyAnalysis.jsx'
import DatasetHealth from './pages/DatasetHealth.jsx'
import FeatureIntelligence from './pages/FeatureIntelligence.jsx'
import LeakageIntelligence from './pages/LeakageIntelligence.jsx'
import { Datasets, Exports, Investigate, Overview, Prepare } from './pages/Workspace.jsx'

const DESC = {
  'Feature Intelligence': 'How columns relate to each other and to the target: correlations, redundancy, multicollinearity.',
  'Anomaly Analysis': 'Unusual records found with Isolation Forest, LOF, IQR or DBSCAN. Anomalies are inspected, never removed.',
  'Leakage Intelligence': 'Evidence that information from outside the training data may reach the evaluation.',
  'Dataset Health': 'A transparent, evidence-based score and an ML-readiness assessment.',
}
const JOB_LABEL = { profile: 'Profiling dataset', prepare: 'Preparing data', analyze: 'Analysing dataset', anomaly: 'Detecting anomalies', leakage: 'Checking leakage' }
const DEFAULT_FORM = { sample: '0.1', testSize: '0.2', duplicate: 'keep', imputer: 'median', encoding: 'onehot', scaler: 'robust', selection: 'none', seed: '42' }
const FIELD_TO_FORM = { sample_fraction: 'sample', duplicate_policy: 'duplicate', numeric_imputer: 'imputer', encoding: 'encoding', scaler: 'scaler', feature_selection: 'selection' }

const viewFromHash = () => (typeof location !== 'undefined' && location.hash.startsWith('#/app') ? 'app' : 'landing')

function App() {
  // Landing <-> workspace is a hash route (#/ and #/app) so refresh and browser back/forward behave; workspace state stays mounted in this component.
  const [view, setView] = useState(viewFromHash)
  useEffect(() => {
    const on = () => { setView(viewFromHash()); window.scrollTo?.(0, 0) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const enterWorkspace = () => { window.location.hash = '#/app' }
  const [datasets, setDatasets] = useState([])
  const [runs, setRuns] = useState([])
  const [datasetId, setDatasetId] = useState('')
  const [dataset, setDataset] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [runLeakage, setRunLeakage] = useState(null)
  const [page, setPage] = useState('Process Map')
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const [drawer, setDrawer] = useState(false)
  const [toasts, setToasts] = useState([])
  const dismissToast = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const [severity, setSeverity] = useState('all')
  const [target, setTarget] = useState('')
  const [form, setForm] = useState(DEFAULT_FORM)
  const [decisions, setDecisions] = useState({})
  const [customs, setCustoms] = useState({})
  const [applied, setApplied] = useState([])
  const picker = useRef(null)
  const profile = dataset?.profile

  const loadAnalysis = useCallback(async (id) => {
    if (!id) { setAnalysis(null); return }
    try { setAnalysis((await call('/datasets/' + id + '/analysis')).analysis) } catch (e) { if (e.status !== 404) throw e; setAnalysis(null) }
  }, [])
  const refresh = useCallback(async (id) => {
    const [ds, pr] = await Promise.all([call('/datasets'), call('/preparations')])
    setDatasets(ds.datasets); setRuns(pr.preparations)
    if (id) {
      try { setDataset((await call('/datasets/' + id)).dataset); await loadAnalysis(id) } catch (e) {
        if (e.status === 404) { setDatasetId(''); setDataset(null); setAnalysis(null) } else throw e
      }
    }
  }, [loadAnalysis])
  useEffect(() => { refresh('').catch((e) => setError(e.message)).finally(() => setLoaded(true)) }, [refresh])

  useEffect(() => {
    if (!job?.id || !running(job)) return
    const timer = setInterval(async () => {
      try {
        const { job: next } = await call('/jobs/' + job.id)
        setJob(next)
        if (next.status === 'complete') {
          await refresh(next.dataset_id === datasetId || next.kind === 'profile' ? next.dataset_id : datasetId)
          const text = { profile: 'Profile complete.', prepare: 'Preparation complete and validated.', analyze: 'Analysis complete.', anomaly: 'Anomaly detection complete.', leakage: 'Leakage check complete.' }[next.kind]
          setNotice({ kind: next.kind, text })
        }
      } catch (e) {
        setJob(null)
        setError(e.status === 404 ? 'The job is no longer known to the backend (it may have restarted). Run the action again.' : e.message)
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [job, refresh, datasetId])

  const latestRun = runs.find((r) => r.dataset_id === datasetId)
  useEffect(() => {
    let live = true
    if (!latestRun?.id || !latestRun.has_leakage) { setRunLeakage(null); return }
    call('/preparations/' + latestRun.id + '/leakage').then((r) => live && setRunLeakage(r.leakage)).catch(() => live && setRunLeakage(null))
    return () => { live = false }
  }, [latestRun?.id, latestRun?.has_leakage, analysis?.health?.created_at])

  // A fresh profile may arrive after the dataset was selected: adopt its detected label unless the current choice is still valid.
  useEffect(() => {
    const cols = profile?.column_names
    if (cols && target && !cols.includes(target)) setTarget(profile.label_column || '')
    else if (cols && !target && profile.label_column) setTarget(profile.label_column)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.created_at, datasetId])

  const guard = async (fn) => { setError(''); setBusy(true); try { await fn() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const go = (p) => { setPage(p); window.scrollTo?.(0, 0) }
  const selectDataset = async (id, to = 'Overview') => {
    const { dataset: ds } = await call('/datasets/' + id)
    setDatasetId(id); setDataset(ds); setTarget(ds?.profile?.label_column || ''); setNotice(null); setDecisions({}); setCustoms({}); setApplied([]); go(to)
    await loadAnalysis(id)
    return ds
  }
  const startJob = async (path, body) => { setJob(null); setNotice(null); const { job: j } = await post(path, body); setJob(j) }
  const startProfile = (id) => startJob('/datasets/' + id + '/profile', {})
  const profileDataset = (id) => guard(async () => { await selectDataset(id, page === 'Datasets' ? 'Overview' : page); await startProfile(id) })
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
    await startJob('/datasets/' + datasetId + '/prepare', { target_column: target || null, sample_fraction: Number(form.sample), test_size: Number(form.testSize), seed: Number(form.seed) || 0,
      duplicate_policy: form.duplicate, numeric_imputer: form.imputer, encoding: form.encoding, scaler: form.scaler, feature_selection: form.selection, missing_indicator: true })
  })
  const runAnalysis = () => guard(() => startJob('/datasets/' + datasetId + '/analyze', { target_column: target || null, seed: Number(form.seed) || 0, test_size: Number(form.testSize) }))
  const runAnomaly = (cfg) => guard(() => startJob('/datasets/' + datasetId + '/anomalies', { ...cfg, target_column: target || null }))
  const runLeakageCheck = (runId, threshold) => guard(() => startJob('/preparations/' + runId + '/leakage', { threshold, seed: Number(form.seed) || 0 }))

  const setDecision = (id, v) => setDecisions((d) => ({ ...d, [id]: v }))
  const setCustom = (id, field, v) => setCustoms((c) => ({ ...c, [id]: { ...(c[id] || {}), [field]: v } }))
  const applyRecommendations = () => {
    const next = { ...form }; const lines = []
    for (const item of analysis?.recommendations?.items || []) {
      if (decisions[item.id] !== 'accept' || !item.can_apply) continue
      for (const [field, value] of Object.entries(item.apply)) {
        const v = customs[item.id]?.[field] ?? value
        next[FIELD_TO_FORM[field]] = v; lines.push(`${field.replace(/_/g, ' ')} → ${v}`)
      }
    }
    setForm(next); setApplied(lines); go('Prepare')
  }
  const doDelete = () => guard(async () => {
    const c = confirm; setConfirm(null)
    if (c.type === 'dataset') {
      await call('/datasets/' + c.id, { method: 'DELETE' })
      if (c.id === datasetId) { setDatasetId(''); setDataset(null); setTarget(''); setAnalysis(null) }
      setNotice({ kind: 'info', text: 'Dataset removed from the workspace. Source CSV files were not touched.' })
    } else {
      await call('/preparations/' + c.id, { method: 'DELETE' })
      setNotice({ kind: 'info', text: 'Prepared export deleted.' })
    }
    await refresh(c.type === 'dataset' && c.id === datasetId ? '' : datasetId)
  })

  useEffect(() => {
    if (!notice || running(job)) return
    const actions = { profile: [['Investigate', () => go('Investigate')], ['Run full analysis', runAnalysis]], analyze: [['Health score', () => go('Dataset Health')], ['Recommendations', () => go('Recommendations')]], prepare: [['Leakage findings', () => go('Leakage Intelligence')], ['Exports', () => go('Exports')]] }[notice.kind] || []
    setToasts((t) => [...t, { id: Date.now() + Math.random(), tone: notice.kind === 'info' ? 'info' : 'success', text: notice.text, actions: actions.map(([label, onClick]) => ({ label, onClick })) }])
    setNotice(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notice, job])

  const run = latestRun
  const ps = run?.comparison?.processed_sample
  const runOk = !!run && (ps?.missing_feature_cells_after ?? 1) === 0 && (ps?.infinite_feature_cells_after ?? 1) === 0
  const ctx = { datasets, runs, datasetId, dataset, profile, analysis, runLeakage, latestRun, run, runOk, job, busy, target, setTarget, form, setForm, decisions, customs, applied, setApplied,
    severity, setSeverity, go, pick: () => picker.current?.click(), addCic, profileDataset, prepare, runAnalysis, runAnomaly, runLeakageCheck, setDecision, setCustom, applyRecommendations,
    setConfirm, openDataset: (id) => guard(() => selectDataset(id)) }
  const confirmedCount = [...(analysis?.leakage?.findings || []), ...(runLeakage?.findings || [])].filter((f) => f.status === 'confirmed').length
  const badge = (p) => p === 'Datasets' ? datasets.length : p === 'Exports' ? runs.length : p === 'Leakage Intelligence' && analysis?.leakage ? (confirmedCount ? { text: confirmedCount, cls: 'bg-rose-100 text-rose-700' } : null)
    : p === 'Dataset Health' && analysis?.health?.overall != null ? Math.round(analysis.health.overall) : p === 'Recommendations' && analysis?.recommendations?.items?.length ? analysis.recommendations.items.length : null
  const analysisPage = ['Feature Intelligence', 'Anomaly Analysis', 'Leakage Intelligence', 'Dataset Health'].includes(page)
  const analysisHeader = analysisPage && <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-5">
    <div className="max-w-3xl"><nav aria-label="Breadcrumb" className="text-xs text-slate-400">Workspace  /  {dataset?.name || 'no dataset'}  /  {page}</nav><h1 className="mt-1.5">{page}</h1><p className="mt-2 text-sm leading-relaxed text-slate-500">{DESC[page]}</p></div>
    {profile && <button className="secondary-btn" disabled={busy || running(job)} onClick={runAnalysis}>{analysis?.health ? 'Re-run analysis' : 'Run analysis'}</button>}</div>

  if (view === 'landing') return <Suspense fallback={<div className="min-h-screen bg-[#070c1a]" role="status" aria-label="Loading" />}><LandingPage onEnter={enterWorkspace} onOpen={(p) => { setPage(p); enterWorkspace() }} /></Suspense>

  return <div className="min-h-screen bg-[#f5f7fb] text-[#142338]">
    <Sidebar page={page} go={go} badge={badge} dataset={dataset} profile={profile} datasets={datasets} datasetId={datasetId} loaded={loaded} onPick={() => picker.current?.click()} onSelect={(id) => guard(() => selectDataset(id, page))} open={drawer} setOpen={setDrawer} />
    <main className="min-h-screen lg:pl-[272px]">
      <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-[#f5f7fb]/90 backdrop-blur-xl">
        <div className="flex h-[56px] items-center justify-between px-5 sm:px-8"><div className="flex items-center gap-3"><button className="secondary-btn !px-2.5 lg:hidden" aria-label="Open navigation" aria-expanded={drawer} aria-controls="app-sidebar" onClick={() => setDrawer(true)}>☰</button><a href="#/" className="secondary-btn !px-3" aria-label="Back to home page">← Home</a><span className="truncate text-sm text-slate-500">{dataset ? dataset.name : 'No dataset selected'}</span></div>
          <div className="flex gap-2"><button onClick={addCic} disabled={busy} className="secondary-btn hidden sm:inline-flex">＋ Add CIC-IDS2017</button><button onClick={() => picker.current?.click()} disabled={busy} className="primary-btn">{busy ? 'Working…' : '↑ Upload CSV'}</button><input ref={picker} type="file" accept=".csv,text/csv" aria-label="CSV file" className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = '' }} /></div></div>
      </header>
      <div className="mx-auto max-w-[1360px] space-y-5 px-5 py-7 sm:px-8 sm:py-8">
        {error && <div role="alert" className="flex items-start justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
        {running(job) && <div className="flex items-center gap-4 rounded-lg border border-slate-200 bg-white p-4" role="status"><span className="h-7 w-7 shrink-0 animate-spin rounded-full border-2 border-indigo-100 border-t-indigo-600" /><div className="flex-1"><div className="flex justify-between text-sm font-medium"><span>{JOB_LABEL[job.kind] || 'Working'}</span><span className="num">{Math.round(job.progress * 100)}%</span></div><p className="mt-0.5 text-xs text-slate-500">{job.message}</p><div className="mt-2 h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: (job.progress * 100) + '%' }} /></div></div></div>}
        {job?.status === 'failed' && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"><b>{JOB_LABEL[job.kind] || 'Job'} failed:</b> {job.error}</div>}
        {confirm && <ConfirmDialog title={confirm.type === 'dataset' ? 'Remove dataset?' : 'Delete prepared export?'} onCancel={() => setConfirm(null)} onConfirm={doDelete}>{confirm.type === 'dataset' ? `Remove “${confirm.name}” from the workspace? Its analyses and prepared exports are deleted; source CSV files of registered datasets are not.` : 'Delete this prepared export and its files? This cannot be undone.'}</ConfirmDialog>}
        {!loaded && <div className="rounded-lg border border-slate-200 bg-white p-10 text-center text-sm text-slate-500" role="status">Loading workspace…</div>}
        {loaded && <>
          {analysisHeader}
          {page === 'Process Map' && <ProcessMap ctx={ctx} />}
          {page === 'Overview' && <Overview ctx={ctx} />}
          {page === 'Investigate' && <Investigate ctx={ctx} />}
          {page === 'Datasets' && <Datasets ctx={ctx} />}
          {page === 'Prepare' && <Prepare ctx={ctx} />}
          {page === 'Exports' && <Exports ctx={ctx} />}
          {page === 'Feature Intelligence' && <FeatureIntelligence ctx={ctx} />}
          {page === 'Anomaly Analysis' && <AnomalyAnalysis ctx={ctx} />}
          {page === 'Leakage Intelligence' && <LeakageIntelligence ctx={ctx} />}
          {page === 'Dataset Health' && <DatasetHealth ctx={ctx} />}
          {page === 'Recommendations' && <RecommendationsPage ctx={ctx} />}
        </>}
        <footer className="flex flex-wrap justify-between gap-2 border-t border-slate-200 pt-4 text-xs text-slate-400"><span>DataLens · Local-first dataset intelligence</span><span>Original files stay untouched{dataset ? ` · ${mb(dataset.size_bytes)} MB selected` : ''}</span></footer>
      </div>
    </main>
    <ToastHost toasts={toasts} dismiss={dismissToast} />
  </div>
}

export default App
