import { useMemo, useState } from 'react'

export const num = (n, d = 0) => (n === null || n === undefined || Number.isNaN(Number(n)) ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }))
export const pct = (n, d = 1) => (n === null || n === undefined ? '—' : Number(n).toFixed(d) + '%')
export const fmt = (v) => (v === null || v === undefined ? '—' : typeof v === 'number' ? (Math.abs(v) >= 1000 || Number.isInteger(v) ? num(v, 2) : Number(v.toPrecision(4)).toString()) : String(v))

export function Tip({ text }) { return <span title={text} aria-label={text} className="ml-1 cursor-help text-slate-300">ⓘ</span> }

export function Skeleton({ lines = 3, className = '' }) {
  return <div className={'space-y-2 ' + className} role="status" aria-label="Loading">{Array.from({ length: lines }, (_, i) => <div key={i} className="skeleton h-4" style={{ width: (95 - i * 12) + '%' }} />)}</div>
}

export function Empty({ title, children, action }) {
  return <div className="rounded-lg border border-dashed border-slate-300 bg-white/60 px-6 py-10 text-center"><h3>{title}</h3><p className="mx-auto mt-2 max-w-lg text-sm text-slate-500">{children}</p>{action && <div className="mt-4 flex justify-center gap-2">{action}</div>}</div>
}

export function InfoBox({ tone = 'info', title, children }) {
  const cls = { info: 'border-indigo-200 bg-indigo-50 text-indigo-900', warn: 'border-amber-200 bg-amber-50 text-amber-900', crit: 'border-rose-200 bg-rose-50 text-rose-900', ok: 'border-emerald-200 bg-emerald-50 text-emerald-900' }[tone]
  return <div className={'rounded-lg border px-4 py-3 text-sm leading-relaxed ' + cls}>{title && <b className="mr-1">{title}</b>}{children}</div>
}

export function SevTag({ severity }) { return <span className={'tag sev-' + severity}>{severity}</span> }
export function StatusTag({ status }) { return <span className={'tag st-' + status}>{status === 'not_assessed' ? 'not assessed' : status}</span> }

export function PageHeader({ crumbs, title, description, actions }) {
  return <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-5">
    <div className="min-w-0 max-w-3xl"><nav aria-label="Breadcrumb" className="text-xs text-slate-400">{crumbs.join('  /  ')}</nav><h1 className="mt-1.5">{title}</h1>{description && <p className="mt-2 text-sm leading-relaxed text-slate-500">{description}</p>}</div>
    {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
  </div>
}

export function Section({ title, subtitle, actions, children, id }) {
  return <section id={id} className="pt-7 first:pt-0"><div className="mb-4 flex flex-wrap items-end justify-between gap-2"><div><h2>{title}</h2>{subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-500">{subtitle}</p>}</div>{actions}</div>{children}</section>
}

export function Figure({ label, value, note, tone }) {
  const color = { crit: 'text-rose-700', warn: 'text-amber-700', ok: 'text-emerald-700' }[tone] || 'text-ink'
  return <div className="min-w-[120px]"><div className="text-xs text-slate-500">{label}</div><div className={'num mt-1 text-2xl font-medium tracking-tight ' + color}>{value}</div>{note && <div className="mt-0.5 text-xs text-slate-400">{note}</div>}</div>
}

/** Sortable, searchable, paginated table. columns: {key,label,num,render,sortValue,className} */
export function DataTable({ columns, rows, pageSize = 10, searchKeys, initialSort, empty = 'No rows.', caption, filters }) {
  const [sort, setSort] = useState(initialSort || null)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    let out = q && searchKeys ? rows.filter((r) => searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(q))) : rows
    if (sort) {
      const col = columns.find((c) => c.key === sort.key)
      const val = (r) => (col?.sortValue ? col.sortValue(r) : r[sort.key])
      out = [...out].sort((a, b) => { const x = val(a), y = val(b); if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * (sort.dir === 'asc' ? 1 : -1) })
    }
    return out
  }, [rows, query, sort, columns, searchKeys])
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const cur = Math.min(page, pages - 1)
  const shown = filtered.slice(cur * pageSize, cur * pageSize + pageSize)
  const toggle = (key) => { setPage(0); setSort((s) => (s?.key === key ? (s.dir === 'desc' ? { key, dir: 'asc' } : null) : { key, dir: 'desc' })) }
  return <div>
    {(searchKeys || filters) && <div className="mb-3 flex flex-wrap items-center gap-3">{searchKeys && <input value={query} onChange={(e) => { setQuery(e.target.value); setPage(0) }} placeholder="Search…" aria-label="Search table" className="w-56 rounded-md border border-slate-300 px-3 py-1.5 text-sm" />}{filters}<span className="ml-auto text-xs text-slate-400">{num(filtered.length)} of {num(rows.length)}</span></div>}
    <div className="soft-scroll overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="data-table">{caption && <caption className="sr-only">{caption}</caption>}
        <thead><tr>{columns.map((c) => <th key={c.key} scope="col" className={(c.num ? 'r ' : '') + 'sortable'} style={c.num ? { textAlign: 'right' } : undefined} onClick={() => toggle(c.key)} aria-sort={sort?.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>{c.label}{sort?.key === c.key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>)}</tr></thead>
        <tbody>{shown.map((r, i) => <tr key={r.id ?? r.row_id ?? r.column ?? i}>{columns.map((c) => <td key={c.key} className={(c.num ? 'r ' : '') + (c.className || '')}>{c.render ? c.render(r) : fmt(r[c.key])}</td>)}</tr>)}
          {!shown.length && <tr><td colSpan={columns.length} className="py-8 text-center text-slate-400">{empty}</td></tr>}</tbody>
      </table>
    </div>
    {pages > 1 && <div className="mt-2 flex items-center justify-end gap-2 text-xs text-slate-500"><button className="secondary-btn !px-2.5 !py-1" disabled={cur === 0} onClick={() => setPage(cur - 1)}>Prev</button>Page {cur + 1} of {pages}<button className="secondary-btn !px-2.5 !py-1" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)}>Next</button></div>}
  </div>
}

export function Details({ summary, children, open }) {
  return <details open={open} className="rounded-lg border border-slate-200 bg-white"><summary className="cursor-pointer px-4 py-2.5 text-sm font-medium text-slate-700">{summary}</summary><div className="border-t border-slate-100 px-4 py-3 text-sm text-slate-600">{children}</div></details>
}

export function NeedsAnalysis({ dataset, profile, busy, onRun, what }) {
  if (!dataset) return <Empty title="No dataset selected">Select a dataset from the sidebar or the Datasets page.</Empty>
  if (!profile) return <Empty title="Profile the dataset first">Analysis builds on the dataset profile. Run the profile from the Overview page.</Empty>
  return <Empty title={`${what} has not been computed`} action={<button className="primary-btn" disabled={busy} onClick={onRun}>Run analysis</button>}>
    The analysis samples up to 50,000 rows (seeded) and runs in the background. Your source data is never modified.</Empty>
}
