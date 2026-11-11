import { useEffect } from 'react'
import { num } from '../ui.jsx'
import logo from '../../assets/logo.png'
export const GROUPS = [
  ['WORKSPACE', ['Process Map', 'Overview', 'Investigate', 'Datasets', 'Prepare', 'Exports']],
  ['ANALYSIS', ['Feature Intelligence', 'Anomaly Analysis', 'Leakage Intelligence', 'Dataset Health', 'Recommendations']],
]
export const ALL = GROUPS.flatMap(([, p]) => p)
const ICON = { 'Process Map': '⌬', Overview: '◫', Investigate: '⌕', Datasets: '▤', Prepare: '◈', Exports: '⇩', 'Feature Intelligence': '⌗', 'Anomaly Analysis': '◌', 'Leakage Intelligence': '⚑', 'Dataset Health': '♡', Recommendations: '✦' }
export const LABEL = { Prepare: 'Prepare data' }

/** 272px fixed sidebar on desktop; off-canvas drawer below lg. */
export default function Sidebar({ page, go, badge, dataset, profile, datasets, datasetId, loaded, onPick, onSelect, open, setOpen }) {
  useEffect(() => {
    if (!open) return undefined
    const key = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [open, setOpen])
  const nav = (p) => { go(p); setOpen(false) }
  return <>
    {open && <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={() => setOpen(false)} aria-hidden="true" data-testid="drawer-scrim" />}
    <aside id="app-sidebar" aria-label="Primary" className={'fixed inset-y-0 left-0 z-40 flex w-[272px] flex-col border-r border-slate-200 bg-white px-4 py-5 transition-transform duration-200 lg:translate-x-0 lg:visible ' + (open ? 'translate-x-0 visible' : '-translate-x-full invisible')}>
      <div className="flex items-center gap-3 px-2"><img src={logo} alt="DataLens" className="h-10 w-10 rounded-lg object-contain" /><div className="flex-1"><div className="serif text-[21px]">DataLens</div><div className="eyebrow">DATASET INTELLIGENCE</div></div>
        <button className="text-2xl leading-none text-slate-400 lg:hidden" aria-label="Close navigation" onClick={() => setOpen(false)}>×</button></div>
      <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5" aria-label="Selected dataset"><div className="eyebrow">SELECTED DATASET</div>{dataset ? <><div className="mt-1 truncate text-sm font-semibold" title={dataset.name}>{dataset.name}</div><div className="text-xs text-slate-500">{profile ? num(profile.rows) + ' rows · ' + profile.columns + ' columns' : 'Not profiled'}</div></> : <div className="mt-1 text-xs text-slate-400">None selected</div>}</div>
      <div className="soft-scroll mt-5 flex-1 overflow-y-auto">{GROUPS.map(([g, pages]) => <div key={g} className="mb-5"><div className="eyebrow px-3">{g}</div>
        <nav className="mt-2 space-y-0.5" aria-label={g}>{pages.map((n) => { const b = badge(n); const o = b === null || b === undefined ? null : typeof b === 'object' ? b : { text: b, cls: 'bg-slate-100 text-slate-500' }
          return <button key={n} onClick={() => nav(n)} aria-current={page === n ? 'page' : undefined} className={'nav-item ' + (page === n ? 'nav-active' : '')}><span className="w-5 text-center text-base">{ICON[n]}</span>{LABEL[n] || n}{o && <span className={'ml-auto rounded-full px-2 text-[11px] ' + o.cls}>{o.text}</span>}</button> })}</nav></div>)}
        <div className="flex items-center justify-between px-3"><span className="eyebrow">YOUR DATASETS</span><button title="Upload CSV" aria-label="Upload CSV" onClick={onPick} className="text-indigo-600">＋</button></div>
        <div className="mt-2 space-y-0.5">{datasets.map((d) => <button key={d.id} onClick={() => { onSelect(d.id); setOpen(false) }} className={'dataset-link ' + (datasetId === d.id ? 'dataset-link-active' : '')}><span className="block truncate text-[13.5px] font-medium">{d.name}</span><span className="mt-0.5 block text-[11.5px] text-slate-400">{d.profile ? num(d.profile.rows) + ' rows' : 'Ready to profile'}</span></button>)}{loaded && !datasets.length && <p className="px-3 text-xs text-slate-400">No datasets yet.</p>}</div></div>
      <div className="mt-3 flex items-center gap-2 px-3 text-xs text-slate-500"><i className="online-dot" />Local workspace · data stays on this machine</div>
    </aside></>
}
