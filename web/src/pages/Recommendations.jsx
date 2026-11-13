import { useState } from 'react'
import { Details, InfoBox, Tip } from '../components/ui.jsx'

const PRI = { high: 'sev-critical', medium: 'sev-medium', low: 'sev-low' }
const LABEL = { sample_fraction: 'Dataset size', duplicate_policy: 'Duplicate policy', numeric_imputer: 'Numeric imputer', encoding: 'Categorical encoding', scaler: 'Scaling', feature_selection: 'Feature selection' }

/** Accept / reject / customise recommendations. Nothing changes the Prepare form until "Apply accepted". */
export default function Recommendations({ recs, decisions, customs, setDecision, setCustom, onApply }) {
  const [filter, setFilter] = useState('open')
  const items = recs?.items || []
  if (!recs) return null
  const accepted = items.filter((i) => decisions[i.id] === 'accept' && i.can_apply)
  const shown = items.filter((i) => (filter === 'all' ? true : filter === 'applicable' ? i.can_apply : decisions[i.id] !== 'reject'))
  return <div>
    <div className="mb-3 flex flex-wrap items-center gap-3 text-sm"><div className="flex gap-1" role="group" aria-label="Recommendation filter">{[['open', 'Open'], ['applicable', 'Can apply'], ['all', 'All']].map(([k, l]) => <button key={k} className={filter === k ? 'primary-btn !py-1.5' : 'secondary-btn !py-1.5'} onClick={() => setFilter(k)}>{l}</button>)}</div>
      <span className="text-xs text-slate-400">{items.length} recommendation(s) · {recs.applicable} can be applied to the Prepare form</span>
      <button className="primary-btn ml-auto" disabled={!accepted.length} onClick={onApply}>Apply {accepted.length || ''} accepted to Prepare →</button></div>
    {!items.length && <InfoBox tone="ok">No preprocessing recommendations: nothing in the findings calls for one.</InfoBox>}
    <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">{shown.map((r) => { const d = decisions[r.id]
      return <li key={r.id} className={'px-4 py-4 ' + (d === 'reject' ? 'opacity-60' : '')}>
        <div className="flex flex-wrap items-start gap-3"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className={'tag ' + PRI[r.priority]}>{r.priority}</span><span className="text-xs uppercase tracking-wide text-slate-400">{r.category}</span></div>
          <h4 className="mt-1.5 text-[15px] font-semibold">{r.finding}</h4></div>
          <div className="flex gap-2" role="group" aria-label={'Decision for ' + r.finding}>
            <button className={d === 'accept' ? 'primary-btn !py-1.5' : 'secondary-btn !py-1.5'} onClick={() => setDecision(r.id, d === 'accept' ? null : 'accept')} aria-pressed={d === 'accept'}>{r.can_apply ? 'Accept' : 'Acknowledge'}</button>
            <button className={d === 'reject' ? 'primary-btn !bg-slate-600 !py-1.5' : 'secondary-btn !py-1.5'} onClick={() => setDecision(r.id, d === 'reject' ? null : 'reject')} aria-pressed={d === 'reject'}>Reject</button></div></div>
        <p className="mt-2 text-sm text-slate-600">{r.why}</p>
        <p className="mt-2 text-sm"><b>Suggested:</b> {r.suggested_action}</p>
        {r.can_apply ? <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md bg-slate-50 px-3 py-2 text-xs">{Object.keys(r.apply).map((field) => <label key={field} className="flex items-center gap-2">{LABEL[field]}<Tip text="Customise the value before applying." /><select aria-label={`${LABEL[field]} for ${r.finding}`} value={customs[r.id]?.[field] ?? r.apply[field]} onChange={(e) => setCustom(r.id, field, e.target.value)} className="rounded border border-slate-300 bg-white px-2 py-1">{r.choices[field].map((c) => <option key={c} value={c}>{c === '0.1' ? '10% sample' : c === '0.25' ? '25% sample' : c === '1' ? 'Full dataset' : c}</option>)}</select></label>)}<span className="text-slate-400">Applies to the Prepare form only when you accept and apply.</span></div>
          : r.manual_step && <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600"><b>Manual step:</b> {r.manual_step}</p>}
        <div className="mt-2 grid gap-x-8 gap-y-1 text-xs text-slate-500 sm:grid-cols-2"><p><b className="text-slate-600">Benefit:</b> {r.expected_benefit}</p><p><b className="text-slate-600">Trade-off:</b> {r.tradeoffs}</p></div>
        {Object.keys(r.evidence).length > 0 && <Details summary="Evidence"><pre className="soft-scroll overflow-auto text-xs">{JSON.stringify(r.evidence, null, 1)}</pre></Details>}
      </li> })}
      {!shown.length && items.length > 0 && <li className="px-4 py-6 text-center text-sm text-slate-400">Nothing in this view.</li>}</ul>
  </div>
}
