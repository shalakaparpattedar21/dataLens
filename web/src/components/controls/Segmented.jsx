/** Pill-style segmented filter. options: [[value, label], ...]. Optional counts: {value: n}. */
export default function Segmented({ label, value, onChange, options, counts }) {
  return <div role="group" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-full bg-slate-100 p-1">
    {options.map(([v, l]) => <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
      className={'rounded-full px-3 py-1 text-[13px] font-semibold transition ' + (value === v ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-800')}>
      {l}{counts && counts[v] !== undefined && <span className="ml-1.5 text-xs font-normal text-slate-400">{counts[v]}</span>}</button>)}
  </div>
}
