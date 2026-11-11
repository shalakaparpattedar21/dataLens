import { useEffect, useRef } from 'react'

/** Modal confirmation. Escape and Cancel close it; focus starts on Cancel so a stray Enter never deletes. */
export default function ConfirmDialog({ title, children, confirmLabel = 'Delete', onConfirm, onCancel }) {
  const cancel = useRef(null)
  useEffect(() => {
    cancel.current?.focus()
    const key = (e) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onCancel])
  return <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 p-4" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
    <div role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
      <h3 id="confirm-title">{title}</h3><div className="mt-2 text-sm leading-relaxed text-slate-600">{children}</div>
      <div className="mt-5 flex justify-end gap-2"><button ref={cancel} className="secondary-btn" onClick={onCancel}>Cancel</button><button className="primary-btn !bg-rose-600 hover:!bg-rose-700" onClick={onConfirm}>{confirmLabel}</button></div>
    </div></div>
}
