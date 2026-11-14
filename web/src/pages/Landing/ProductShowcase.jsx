import { useState } from 'react'
import PreviewPanel from '../../components/landing/PreviewPanel.jsx'
import processMap from '../../assets/landing/process-map.jpg'
import feature from '../../assets/landing/feature-intelligence.jpg'
import anomaly from '../../assets/landing/anomaly-analysis.jpg'
import leakage from '../../assets/landing/leakage-intelligence.jpg'
import prepare from '../../assets/landing/prepare-data.jpg'
import health from '../../assets/landing/dataset-health.jpg'

const ITEMS = [
  ['Process Map', processMap, 'Overview and process map', 'A dark map of the workflow whose nodes reflect the real state of your dataset, analysis and prepared run. Select a node to open that step.'],
  ['Correlation heatmap', feature, 'Feature Intelligence', 'Hierarchically ordered Pearson and Spearman heatmaps, redundancy groups and multicollinearity. Click a label to inspect a feature.'],
  ['Anomaly Analysis', anomaly, 'Anomaly Analysis', 'Choose Isolation Forest, LOF, IQR or DBSCAN. Inspect the score distribution, a PCA projection and why each record was flagged. Nothing is removed.'],
  ['Leakage Intelligence', leakage, 'Leakage Intelligence', 'Confirmed, potential and not-assessed findings with evidence: exact train/test overlap and near-duplicate distances.'],
  ['Prepare data', prepare, 'Prepare data', 'Configure each transform explicitly. Fitting uses training rows only, and the run is validated and compared before and after.'],
  ['Dataset Health', health, 'Dataset Health', 'A transparent score with a published method, per-dimension evidence and a separate ML-readiness assessment.'],
]

export default function ProductShowcase() {
  const [i, setI] = useState(0)
  const [name, src, alt, text] = ITEMS[i]
  return <div className="grid gap-8 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)] xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
    <div>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1" aria-label="Product views">{ITEMS.map(([n], k) => <li key={n}><button onClick={() => setI(k)} aria-pressed={i === k} className={'flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left text-[15px] font-semibold transition ' + (i === k ? 'border-indigo-400 bg-[#17224a] text-white' : 'border-slate-700 bg-[#101a33] text-slate-300 hover:border-slate-500')}><span className="text-xs tracking-widest text-slate-500">{String(k + 1).padStart(2, '0')}</span>{n}</button></li>)}</ul>
      <div className="mt-5 rounded-xl border border-slate-700/70 bg-[#0d1530] p-5" role="status" aria-live="polite"><b className="text-white">{name}</b><p className="mt-2 text-[15px] leading-relaxed text-slate-300">{text}</p></div>
    </div>
    <PreviewPanel src={src} alt={alt + ' screenshot of the DataLens workspace'} caption="Real screenshot of the application running on a small synthetic demo dataset (3,150 rows). Values are from that demo, not from your data." />
  </div>
}
