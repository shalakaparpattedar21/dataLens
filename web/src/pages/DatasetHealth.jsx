import { Details, Figure, InfoBox, NeedsAnalysis, Section, SevTag, StatusTag, fmt, num } from '../components/ui.jsx'
import { ScoreBar, Trend } from '../components/charts.jsx'
import Radar from '../components/charts/Radar.jsx'

const READY = { ready_for_experimentation: ['ok', 'Ready for experimentation'], needs_improvement: ['warn', 'Needs improvement'], high_risk: ['crit', 'High risk'], insufficient_evidence: ['info', 'Insufficient evidence'] }

export default function DatasetHealth({ ctx }) {
  const { analysis, dataset, profile, busy, runAnalysis, job } = ctx
  const h = analysis?.health
  if (!h || !h.dimensions?.length) return <NeedsAnalysis dataset={dataset} profile={profile} busy={busy || ['queued', 'running'].includes(job?.status)} onRun={runAnalysis} what="Dataset health" />
  const [tone, label] = READY[h.readiness.status] || ['info', h.readiness.label]
  const band = h.overall === null ? '' : h.overall >= 80 ? 'Healthy' : h.overall >= 60 ? 'Fair' : 'Poor'
  const trend = (analysis.health_history || []).map((s) => ({ label: new Date(s.created_at).toLocaleString(), value: s.overall }))
  return <div className="space-y-2">
    <div className="grid gap-8 border-b border-slate-200 pb-7 lg:grid-cols-[260px_1fr]">
      <div><div className="text-xs uppercase tracking-wide text-slate-400">DataLens Health Score</div>
        <div className="mt-2 flex items-baseline gap-2"><span className="serif num text-[76px] leading-none">{h.overall === null ? '—' : Math.round(h.overall)}</span>{h.overall !== null && <span className="text-slate-400">/ 100</span>}</div>
        <div className="mt-2 text-sm text-slate-600">{h.overall === null ? 'Insufficient data' : band}</div>
        {h.overall_cap && <p className="mt-2 text-xs text-rose-700">{h.overall_cap}.</p>}</div>
      <div><div className="text-xs uppercase tracking-wide text-slate-400">Is this dataset ready for machine learning?</div>
        <h2 className={'mt-2 ' + ({ ok: 'text-emerald-700', warn: 'text-amber-700', crit: 'text-rose-700', info: 'text-indigo-700' }[tone])}>{label}</h2>
        {h.readiness.blockers?.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">{h.readiness.blockers.slice(0, 8).map((b) => <li key={b}>{b}</li>)}</ul>}
        <p className="mt-3 text-xs text-slate-500">{h.readiness.note}{h.readiness.preparation_validation !== null && h.readiness.preparation_validation !== undefined ? ` Latest preparation validation: ${h.readiness.preparation_validation ? 'passed' : 'failed'}.` : ''}</p></div>
    </div>

    <Section title="Dimension profile" subtitle="Each axis is one dimension's 0–100 score; dimensions without enough evidence are left out rather than plotted as zero.">
      <Radar title="Health dimensions" axes={h.dimensions.filter((d) => d.score !== null && d.score !== undefined).map((d) => ({ label: d.name, value: d.score }))} /></Section>

    <Section title="Dimensions" subtitle="Each score is computed from backend findings with a published formula. Expand a row for its factors, actions and method.">
      <div className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">{h.dimensions.map((d) => <details key={d.name} className="group">
        <summary className="grid cursor-pointer grid-cols-[1fr] items-center gap-x-6 gap-y-1 px-4 py-3 sm:grid-cols-[170px_minmax(0,1fr)_60px]"><span className="text-sm font-medium capitalize">{d.name}</span><ScoreBar score={d.score} label={d.label} /><span className="num text-right text-xs text-slate-400">w {Math.round((d.weight || 0) * 100)}%</span></summary>
        <div className="space-y-3 border-t border-slate-100 px-4 py-3 text-sm"><p>{d.summary}</p>
          {d.factors.length > 0 && <table className="data-table"><thead><tr><th>Factor</th><th className="r">Value</th><th className="r">Penalty / deduction</th></tr></thead><tbody>{d.factors.map((f, i) => <tr key={i}><td>{f.factor}{f.status ? <> <StatusTag status={f.status} /> <SevTag severity={f.severity} /></> : ''}</td><td className="r">{f.note || fmt(f.value)}{f.of ? ` / ${f.of}` : ''}</td><td className="r">{f.deduction !== undefined ? '−' + f.deduction : f.penalty !== undefined ? fmt(f.penalty) : '—'}</td></tr>)}</tbody></table>}
          {d.actions.length > 0 && <ul className="list-disc pl-5 text-slate-600">{d.actions.map((a, i) => <li key={i}>{a}</li>)}</ul>}
          <p className="text-xs text-slate-400"><b>Method:</b> {d.methodology}</p></div></details>)}</div>
    </Section>

    <div className="grid gap-8 lg:grid-cols-2">
      <Section title="Critical findings">{h.critical_findings.length ? <ul className="space-y-2">{h.critical_findings.map((f) => <li key={f.id + f.scope} className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm"><div className="mb-1 flex gap-2"><StatusTag status={f.status} /><SevTag severity={f.severity} /></div><b>{f.title}</b><p className="mt-1 text-slate-600">{f.evidence_text}</p></li>)}</ul> : <InfoBox tone="ok">No critical or high-severity leakage findings.</InfoBox>}</Section>
      <Section title="Top recommended actions">{h.top_actions.length ? <ol className="list-decimal space-y-2 pl-5 text-sm">{h.top_actions.map((a, i) => <li key={i}><span className="text-xs uppercase tracking-wide text-slate-400">{a.dimension}</span><br />{a.action}</li>)}</ol> : <p className="text-sm text-slate-400">No outstanding actions.</p>}</Section>
    </div>
    <Section title="Health trend" subtitle="One snapshot is stored each time the analysis or a preparation updates the score.">
      <div className="max-w-md"><Trend points={trend} /></div></Section>
    <Details summary="How the score is calculated"><div className="space-y-2 text-xs leading-relaxed">{Object.entries(h.methodology).map(([k, v]) => <p key={k}><b className="capitalize">{k.replace('_', ' ')}:</b> {v}</p>)}</div></Details>
    <p className="pt-2 text-xs text-slate-400">Computed {new Date(h.created_at).toLocaleString()} from the profile ({num(profile?.rows)} rows) and stored analyses.</p>
  </div>
}
