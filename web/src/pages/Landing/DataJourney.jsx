import { useState } from 'react'

const STAGES = [
  ['INGEST', '⇡', 'Upload and register datasets.', 'Upload a CSV, or register local CIC-IDS2017 files as read-only sources. DataLens never alters the originals.', 'You start it'],
  ['UNDERSTAND', '◫', 'Profile structure.', 'A chunked full-data profile: types, missing and infinite values, duplicates, constants and class distribution. It starts after an upload.', 'Starts after upload'],
  ['INVESTIGATE', '⌕', 'Discover quality issues.', 'Findings with explanations and recommended actions, plus distributions once the analysis has been run.', 'Profile + optional analysis'],
  ['ANALYSE', '⌗', 'Relationships, anomalies, leakage.', 'Run the analysis when you want it: Feature Intelligence, Anomaly Analysis, Leakage Intelligence and Dataset Health. It is on demand, not automatic.', 'Optional · you run it'],
  ['RECOMMEND', '✦', 'Evidence-based suggestions.', 'Accept, reject or customise each suggestion. Nothing changes until you apply accepted ones to the Prepare form.', 'You decide'],
  ['PREPARE', '◈', 'Configure the recipe.', 'Sampling, duplicate policy, missing-value treatment, encoding, scaling, feature selection, seed and train/test split. Fitting uses training rows only.', 'You configure'],
  ['VALIDATE', '✓', 'Inspect results.', 'Before/after comparison and a check that exported features hold no missing or infinite values. A leakage check runs on the prepared split. This is not a full ML-readiness verdict.', 'Runs with preparation'],
  ['EXPORT', '⇩', 'Download artifacts.', 'train.csv, test.csv, config.json, quality_report.json and .md, comparison.json, and leakage_report.json when available.', 'Per run'],
]

export default function DataJourney() {
  const [i, setI] = useState(5)
  const [name, icon, , detail, status] = STAGES[i]
  return <div>
    <ol className="relative grid gap-3 sm:grid-cols-2 lg:grid-cols-8 lg:gap-2" aria-label="DataLens stages">
      <div aria-hidden="true" className="absolute left-[6.25%] right-[6.25%] top-[26px] hidden h-0.5 bg-gradient-to-r from-sky-500/60 via-indigo-400/60 to-emerald-400/60 lg:block" />
      {STAGES.map(([n, ic, short], k) => <li key={n} className="relative">
        <button onClick={() => setI(k)} onMouseEnter={() => setI(k)} aria-current={i === k ? 'step' : undefined} className={'relative flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition lg:flex-col lg:gap-1.5 lg:px-2 lg:py-3 lg:text-center ' + (i === k ? 'border-indigo-400 bg-[#17224a]' : k < i ? 'border-emerald-500/40 bg-[#0f2a2a]' : 'border-slate-700 bg-[#101a33] hover:border-slate-500')}>
          <span className={'grid h-9 w-9 shrink-0 place-items-center rounded-full text-base ' + (i === k ? 'bg-indigo-500 text-white' : k < i ? 'bg-emerald-500/80 text-slate-900' : 'bg-slate-800 text-slate-300')}>{ic}</span>
          <span><span className="block text-[11px] font-bold tracking-[.14em] text-slate-500">{String(k + 1).padStart(2, '0')}</span><b className="block text-[13px] tracking-wide text-white">{n}</b><span className="mt-0.5 hidden text-[12px] leading-snug text-slate-400 xl:block">{short}</span></span>
        </button></li>)}
    </ol>
    <div className="mt-5 grid gap-4 rounded-2xl border border-slate-700/70 bg-[#0d1530] p-5 sm:p-7 md:grid-cols-[1fr_auto]" role="region" aria-live="polite" aria-label="Stage details">
      <div><div className="text-xs font-bold tracking-[.18em] text-indigo-300">STAGE {String(i + 1).padStart(2, '0')} · {name}</div><p className="mt-2 max-w-3xl text-[17px] leading-relaxed text-slate-200">{detail}</p></div>
      <div className="self-start rounded-full border border-slate-600 px-3 py-1.5 text-[13px] font-semibold text-slate-300"><i className="mr-2 inline-block h-2 w-2 rounded-full bg-amber-400" />{status}</div>
    </div>
  </div>
}
