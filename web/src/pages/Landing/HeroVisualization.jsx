import { useEffect, useState } from 'react'
import ParticleField, { LAYERS } from '../../components/landing/ParticleField.jsx'
import { useReducedMotion } from '../../hooks/useMotion.js'

const INFO = {
  raw: ['Raw observations', 'Rows arrive through ingestion. Without analysis, structure, risks and relationships are invisible.'],
  clusters: ['Structure emerges', 'Observations group into regions of similar behaviour. Hover a cluster.'],
  relations: ['Relationships', 'Feature Intelligence links: teal = positive association, dashed amber = negative.'],
  anomalies: ['Anomalies', 'Unusual observations are highlighted for inspection. DataLens flags them; it never removes them silently.'],
  leakage: ['Leakage risk', 'Leakage Intelligence looks for rows shared between train and test, shown here as red links.'],
  prepared: ['Prepared outputs', 'A fitted-on-train, validated train/test split. Passing validation is not a full ML-readiness verdict.'],
}
const LABEL = { raw: 'Raw', clusters: 'Clusters', relations: 'Relations', anomalies: 'Anomalies', leakage: 'Leakage', prepared: 'Prepared' }

export default function HeroVisualization() {
  const reduced = useReducedMotion()
  const [layer, setLayer] = useState('clusters')
  const [analysed, setAnalysed] = useState(true)
  const [playing, setPlaying] = useState(true)
  const [auto, setAuto] = useState(true)
  useEffect(() => {
    if (reduced || !playing || !auto) return undefined
    let i = LAYERS.indexOf(layer)
    const id = setInterval(() => { i = (i + 1) % LAYERS.length; setLayer(LAYERS[i]); setAnalysed(true) }, 4200)
    return () => clearInterval(id)
  // restart the timer only when autoplay state changes, not on each layer tick
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced, playing, auto])
  const pick = (l) => { setAuto(false); setLayer(l); setAnalysed(true) }
  const cur = analysed ? layer : 'raw'
  return <div className="flex h-full flex-col">
    <div className="relative aspect-[10/7] w-full min-h-[300px] flex-1 overflow-hidden rounded-2xl border border-slate-700/60 bg-[#0a1022]">
      <ParticleField layer={layer} analysed={analysed} running={playing && !reduced} ariaLabel={`Illustrative animated dataset, layer: ${INFO[cur][0]}`} />
      <div className="pointer-events-none absolute left-4 top-3 text-[11px] font-semibold tracking-[.18em] text-slate-400">LIVE EXAMPLE · ILLUSTRATIVE DATA</div>
      <div className="pointer-events-none absolute bottom-3 left-4 right-4 sm:right-auto sm:max-w-[420px]" role="status" aria-live="polite"><div className="rounded-lg bg-slate-900/80 px-3 py-2"><b className="text-sm text-white">{INFO[cur][0]}</b><p className="mt-0.5 text-[13px] leading-snug text-slate-300">{INFO[cur][1]}</p></div></div>
    </div>
    <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label="Analysis layers">
      {LAYERS.map((l, i) => <button key={l} aria-pressed={analysed && layer === l} onClick={() => pick(l)} className={'lp-chip ' + (analysed && layer === l ? 'lp-chip-on' : '')}><span className="opacity-60">{i + 1}</span> {LABEL[l]}</button>)}
      <span className="mx-1 hidden h-5 w-px bg-slate-700 sm:block" />
      <button aria-pressed={!analysed} onClick={() => setAnalysed(!analysed)} className="lp-chip">{analysed ? 'Show raw data' : 'Show analysed'}</button>
      {!reduced && <button onClick={() => { setPlaying(!playing); if (!playing) setAuto(true) }} className="lp-chip" aria-label={playing ? 'Pause animation' : 'Resume animation'}>{playing ? '❚❚ Pause' : '▶ Play'}</button>}
    </div>
  </div>
}
