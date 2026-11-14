import { useState } from 'react'

const DOCS = [['train.csv', 'Transformed training rows'], ['test.csv', 'Transformed test rows'], ['config.json', 'Exact recipe and seed'], ['quality_report.json', 'Machine-readable findings'], ['quality_report.md', 'Human-readable report'], ['comparison.json', 'Before / after figures']]
const STEPS = ['Sampling', 'Duplicates', 'Missing values', 'Encoding', 'Scaling', 'Selection']

export default function PreparationFlow() {
  const [doc, setDoc] = useState(null)
  return <div>
    <div className="overflow-x-auto rounded-2xl border border-slate-700/70 bg-[#0a1022]"><svg viewBox="0 0 1100 400" className="block h-auto w-full min-w-[820px]" role="group" aria-label="Preparation journey: raw dataset, configurable preprocessing, train/test split, validation and exported artifacts">
      <defs><marker id="pf-a" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" orient="auto"><path d="M0 0L10 5L0 10z" fill="#7f93bb" /></marker></defs>
      <g fill="none" stroke="#5b6f96" strokeWidth="2" markerEnd="url(#pf-a)"><path d="M150 200 H205" /><path d="M455 200 H500" /><path d="M640 200 C690 200 690 120 740 120" /><path d="M640 200 C690 200 690 290 740 290" /><path d="M900 120 C940 120 940 200 975 200" /><path d="M900 290 C940 290 940 200 975 200" /></g>
      <g><rect x="20" y="160" width="130" height="80" rx="12" fill="#101a33" stroke="#3b82f6" strokeWidth="2" /><text x="85" y="196" textAnchor="middle" fill="#fff" fontSize="15" fontWeight="600">Raw dataset</text><text x="85" y="218" textAnchor="middle" fill="#93a4c6" fontSize="12.5">your CSV</text></g>
      <g><rect x="205" y="60" width="250" height="280" rx="14" fill="#101a33" stroke="#818cf8" strokeWidth="2" /><text x="330" y="90" textAnchor="middle" fill="#a5b4fc" fontSize="12" letterSpacing="2" fontWeight="700">CONFIGURABLE</text>
        {STEPS.map((s, k) => <g key={s}><rect x="225" y={105 + k * 36} width="210" height="28" rx="14" fill="#1b2650" /><text x="330" y={124 + k * 36} textAnchor="middle" fill="#e6ecf7" fontSize="13.5">{s}</text></g>)}</g>
      <g><rect x="500" y="160" width="140" height="80" rx="12" fill="#0f2a22" stroke="#22c55e" strokeWidth="2" /><text x="570" y="196" textAnchor="middle" fill="#fff" fontSize="15" fontWeight="600">Prepared</text><text x="570" y="218" textAnchor="middle" fill="#93a4c6" fontSize="12.5">fit on train only</text></g>
      <g><rect x="740" y="85" width="160" height="70" rx="12" fill="#101a33" stroke="#2dd4bf" strokeWidth="2" /><text x="820" y="116" textAnchor="middle" fill="#fff" fontSize="15" fontWeight="600">Training set</text><text x="820" y="138" textAnchor="middle" fill="#93a4c6" fontSize="12.5">~80% (default 20% test)</text></g>
      <g><rect x="740" y="255" width="160" height="70" rx="12" fill="#101a33" stroke="#2dd4bf" strokeWidth="2" /><text x="820" y="286" textAnchor="middle" fill="#fff" fontSize="15" fontWeight="600">Test set</text><text x="820" y="308" textAnchor="middle" fill="#93a4c6" fontSize="12.5">held out</text></g>
      <g><polygon points="1025,150 1085,200 1025,250 965,200" fill="#0f2a22" stroke="#22c55e" strokeWidth="2" /><text x="1025" y="196" textAnchor="middle" fill="#fff" fontSize="13.5" fontWeight="600">Valid?</text><text x="1025" y="213" textAnchor="middle" fill="#93a4c6" fontSize="10.5">no missing/∞</text></g>
      <text x="40" y="380" fill="#7889aa" fontSize="12.5">Before / after comparison and a leakage check on the split are recorded with every run.</text>
    </svg></div>
    <ul className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-6" aria-label="Exported artifacts">{DOCS.map(([n, d]) => <li key={n}><button onClick={() => setDoc(n)} onMouseEnter={() => setDoc(n)} aria-pressed={doc === n} className={'lp-doc w-full text-left ' + (doc === n ? 'lp-doc-on' : '')}><span className="block text-[13.5px] font-semibold text-white">{n}</span><span className="mt-1 block text-[12px] text-slate-400">{d}</span></button></li>)}</ul>
    <p className="mt-3 text-[13px] text-slate-400">Also written when available: <b className="text-slate-300">leakage_report.json</b>. Successful preprocessing does not by itself make a dataset ML-ready; Dataset Health and Leakage Intelligence give that assessment.</p>
    <div className="mt-4 grid gap-4 rounded-xl border border-slate-700/70 bg-[#0d1530] p-4 sm:grid-cols-3" aria-label="Illustrative before and after comparison">
      <div className="sm:col-span-3 flex items-center justify-between"><b className="text-sm text-white">Before / after, as DataLens reports it</b><span className="rounded-full border border-slate-600 px-2 py-0.5 text-[11px] font-semibold tracking-wider text-slate-400">ILLUSTRATIVE VALUES</span></div>
      {[['Missing cells', '4,210', '0'], ['Infinite values', '36', '0'], ['Columns', '62', '71 (one-hot + indicators)']].map(([k, a, b]) => <div key={k}><div className="text-xs text-slate-500">{k}</div><div className="mt-1 text-[18px] text-white"><span className="text-slate-400">{a}</span> <span className="text-slate-600">→</span> {b}</div></div>)}
    </div>
  </div>
}
