import { useEffect } from 'react'

/** Stack of transient notices. Each toast: {id, tone, text, actions?: [{label, onClick}]}. Errors persist until dismissed. */
export default function ToastHost({ toasts, dismiss }) {
  return <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(92vw,420px)] flex-col gap-2" aria-live="polite">
    {toasts.map((t) => <Toast key={t.id} t={t} dismiss={dismiss} />)}
  </div>
}

function Toast({ t, dismiss }) {
  useEffect(() => {
    if (t.tone === 'error') return undefined
    const timer = setTimeout(() => dismiss(t.id), t.ms || 9000)
    return () => clearTimeout(timer)
  }, [t, dismiss])
  const tone = { success: 'border-emerald-200 bg-emerald-50 text-emerald-900', info: 'border-indigo-200 bg-indigo-50 text-indigo-900', error: 'border-rose-200 bg-rose-50 text-rose-900' }[t.tone] || 'border-slate-200 bg-white'
  return <div role={t.tone === 'error' ? 'alert' : 'status'} className={'pointer-events-auto rounded-lg border p-3 text-sm shadow-lg ' + tone}>
    <div className="flex items-start gap-3"><span className="flex-1">{t.tone === 'success' ? '✓ ' : ''}{t.text}</span><button aria-label="Dismiss" className="text-base leading-none" onClick={() => dismiss(t.id)}>×</button></div>
    {t.actions?.length > 0 && <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">{t.actions.map((a) => <button key={a.label} className="font-semibold underline" onClick={() => { a.onClick(); dismiss(t.id) }}>{a.label}</button>)}</div>}
  </div>
}
