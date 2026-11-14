import { useState } from 'react'
import FlowConnector from '../../components/landing/FlowConnector.jsx'
import ModuleNode from '../../components/landing/ModuleNode.jsx'

export const MODULES = [
  { id: 'profile', n: 'PROFILE', line: 'Structure, types, missing, duplicates', color: '#60a5fa', page: 'Overview',
    text: 'A chunked scan of the full file: data types, missing and infinite values, constant columns, exact duplicates and class distribution. Source files are never modified.', example: 'A column with 4% missing cells and two constant columns are listed with their counts.' },
  { id: 'investigate', n: 'INVESTIGATE', line: 'Quality issues with evidence', color: '#818cf8', page: 'Investigate',
    text: 'Each finding says what was seen, how many rows are affected and what to do about it. Distributions, outliers and class imbalance are inspected from a seeded sample of up to 50,000 rows.', example: 'Rare classes with fewer than 100 rows are flagged before they vanish from the test split.' },
  { id: 'feature', n: 'FEATURE INTELLIGENCE', line: 'Correlation, redundancy, VIF', color: '#2dd4bf', page: 'Feature Intelligence',
    text: 'Pearson and Spearman correlation heatmaps, redundancy groups, feature-target association (mutual information, Cramér’s V) and multicollinearity via VIF.', example: 'Two features that are near copies of each other are grouped as redundant.' },
  { id: 'anomaly', n: 'ANOMALY ANALYSIS', line: 'Isolation Forest, LOF, IQR, DBSCAN', color: '#fbbf24', page: 'Anomaly Analysis',
    text: 'Choose a detector and inspect unusual observations in a PCA projection and a table of flagged records. Anomalies are inspected, never removed.', example: 'A handful of rows with extreme values appear apart from the main clusters.' },
  { id: 'leakage', n: 'LEAKAGE INTELLIGENCE', line: 'Overlap, proxies, risk evidence', color: '#f87171', page: 'Leakage Intelligence',
    text: 'Confirmed, potential and not-assessed findings: exact train/test overlap, near-duplicates, identifier-like columns, suspicious feature-target links. Every finding shows its evidence and the limits of the check.', example: 'A single feature that alone predicts the target is flagged as a potential leak.' },
  { id: 'health', n: 'DATASET HEALTH', line: 'Quality score and ML-readiness', color: '#4ade80', page: 'Dataset Health',
    text: 'A transparent, evidence-based score with a published formula, a radar of dimensions and a separate ML-readiness assessment. Serious leakage caps the result.', example: 'A complete dataset with confirmed leakage is still reported as high risk.' },
]
const L = [[10, 20], [10, 214], [10, 408]], R = [[820, 20], [820, 214], [820, 408]]
const POS = [L[0], L[1], L[2], R[0], R[1], R[2]]

export default function IntelligenceEngine({ onOpen }) {
  const [sel, setSel] = useState('feature')
  const m = MODULES.find((x) => x.id === sel)
  return <div>
    <div className="hidden lg:block">
      <svg viewBox="0 0 1100 520" className="block h-auto w-full" role="group" aria-label="Dataset connected to six analytical modules">
        <defs><pattern id="eg" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#162140" /></pattern></defs>
        <rect width="1100" height="520" rx="18" fill="url(#eg)" opacity=".7" />
        {MODULES.map((mod, i) => { const [x, y] = POS[i]; const left = i < 3; const sx = 550 + (left ? -90 : 90), sy = 260, ex = left ? x + 280 : x - 10, ey = y + 46
          const d = `M${sx} ${sy} C ${left ? sx - 90 : sx + 90} ${sy}, ${left ? ex + 90 : ex - 90} ${ey}, ${ex} ${ey}`
          return <FlowConnector key={mod.id} d={d} color={mod.color} active={sel === mod.id} dim={sel !== mod.id} /> })}
        <g><rect x="460" y="212" width="180" height="96" rx="16" fill="#1a1f4d" stroke="#818cf8" strokeWidth="2" /><text x="550" y="254" textAnchor="middle" fill="#fff" fontSize="18" fontWeight="600" fontFamily="Inter, sans-serif">Your dataset</text><text x="550" y="278" textAnchor="middle" fill="#a5b4fc" fontSize="12.5" fontFamily="Inter, sans-serif">CSV · stays on your machine</text></g>
        {MODULES.map((mod, i) => <ModuleNode key={mod.id} x={POS[i][0]} y={POS[i][1]} index={i + 1} name={mod.n} line={mod.line} color={mod.color} selected={sel === mod.id} dim={sel !== mod.id} onSelect={() => setSel(mod.id)} />)}
      </svg>
    </div>
    <ul className="grid gap-2 lg:hidden" aria-label="Analytical modules">{MODULES.map((mod, i) => <li key={mod.id}><button aria-pressed={sel === mod.id} onClick={() => setSel(mod.id)} className={'flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left ' + (sel === mod.id ? 'border-indigo-400 bg-[#17224a]' : 'border-slate-700 bg-[#101a33]')}>
      <span className="text-xs font-bold tracking-widest" style={{ color: mod.color }}>{String(i + 1).padStart(2, '0')}</span><span><b className="block text-[15px] text-white">{mod.n}</b><span className="text-[13px] text-slate-400">{mod.line}</span></span></button></li>)}</ul>
    <div className="mt-5 grid gap-6 rounded-2xl border border-slate-700/70 bg-[#0d1530] p-5 sm:p-7 md:grid-cols-[1.4fr_1fr]" role="region" aria-live="polite" aria-label={m.n + ' details'}>
      <div><div className="text-xs font-bold tracking-[.18em]" style={{ color: m.color }}>{m.n}</div><p className="mt-2 text-[16px] leading-relaxed text-slate-200">{m.text}</p>
        <button onClick={() => onOpen(m.page)} className="lp-link mt-4">Open {m.page} in the workspace →</button></div>
      <div className="rounded-xl border border-slate-700/70 bg-[#0a1022] p-4"><div className="text-[11px] font-semibold tracking-[.16em] text-slate-500">WHAT IT CAN REVEAL · EXAMPLE, ILLUSTRATIVE</div><p className="mt-2 text-[15px] leading-relaxed text-slate-300">{m.example}</p></div>
    </div>
  </div>
}
