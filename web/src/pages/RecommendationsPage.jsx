import Recommendations from './Recommendations.jsx'
import { Figure, NeedsAnalysis, PageHeader, num } from '../components/ui.jsx'

export default function RecommendationsPage({ ctx }) {
  const { analysis, dataset, profile, busy, job, runAnalysis, decisions } = ctx
  const recs = analysis?.recommendations
  const head = <PageHeader crumbs={['Workspace', dataset?.name || 'no dataset', 'Recommendations']} title="Recommendations" description="Preprocessing suggestions derived from measured findings. Accept, reject or customise each one; nothing changes until you apply it to the Prepare form." />
  if (!recs) return <div className="space-y-6">{head}<NeedsAnalysis dataset={dataset} profile={profile} busy={busy || ['queued', 'running'].includes(job?.status)} onRun={runAnalysis} what="Recommendations" /></div>
  const items = recs.items || []
  const acc = items.filter((i) => decisions[i.id] === 'accept').length
  return <div className="space-y-6">{head}
    <div className="flex flex-wrap gap-x-12 gap-y-4 border-b border-slate-200 pb-5">
      <Figure label="Recommendations" value={num(items.length)} /><Figure label="High priority" value={num(items.filter((i) => i.priority === 'high').length)} tone={items.some((i) => i.priority === 'high') ? 'crit' : undefined} />
      <Figure label="Can apply to Prepare" value={num(recs.applicable)} /><Figure label="Accepted" value={num(acc)} tone={acc ? 'ok' : undefined} /></div>
    <Recommendations recs={recs} decisions={decisions} customs={ctx.customs} setDecision={ctx.setDecision} setCustom={ctx.setCustom} onApply={ctx.applyRecommendations} />
  </div>
}
