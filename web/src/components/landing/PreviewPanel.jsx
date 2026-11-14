/** Browser-style frame around a real application screenshot. */
export default function PreviewPanel({ src, alt, caption, w = 1440, h = 900 }) {
  return <figure className="overflow-hidden rounded-xl border border-slate-700/80 bg-slate-900 shadow-2xl shadow-black/40">
    <div className="flex items-center gap-1.5 border-b border-slate-700/80 bg-slate-900 px-3 py-2" aria-hidden="true"><i className="h-2.5 w-2.5 rounded-full bg-slate-600" /><i className="h-2.5 w-2.5 rounded-full bg-slate-600" /><i className="h-2.5 w-2.5 rounded-full bg-slate-600" /><span className="ml-3 text-[11px] text-slate-500">DataLens workspace</span></div>
    <img key={src} src={src} alt={alt} width={w} height={h} loading="lazy" className="lp-fade block h-auto w-full" />
    {caption && <figcaption className="border-t border-slate-700/80 px-4 py-2 text-xs text-slate-400">{caption}</figcaption>}
  </figure>
}
