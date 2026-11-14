import { useEffect, useMemo, useRef, useState } from 'react'
import { gauss, rng, useInView, useReducedMotion } from '../../hooks/useMotion.js'

/*
 * Illustrative dataset: a bounded set of points (<= 900) that move between layouts as the analysis layer changes.
 * Nothing here is user data. Coordinates are logical 1000 x 700 and scaled to the canvas.
 */
const LW = 1000, LH = 700
const CENTERS = [[290, 230, 'A'], [640, 200, 'B'], [730, 470, 'C'], [330, 500, 'D']]
const COLORS = ['#818cf8', '#a78bfa', '#2dd4bf', '#60a5fa']
export const LAYERS = ['raw', 'clusters', 'relations', 'anomalies', 'leakage', 'prepared']

export function buildField(n, seed = 11) {
  const r = rng(seed)
  const pts = []
  const nAnom = Math.round(n * 0.045)
  for (let i = 0; i < n; i++) {
    const anom = i >= n - nAnom
    const cl = anom ? -1 : i % 4
    let cx, cy
    if (anom) {
      do { cx = 70 + r() * 860; cy = 60 + r() * 580 } while (CENTERS.some(([x, y]) => Math.hypot(x - cx, y - cy) < 150))
    } else { const [x, y] = CENTERS[cl]; cx = x + gauss(r) * 52; cy = y + gauss(r) * 46 }
    pts.push({ cl, anom, raw: [60 + r() * 880, 50 + r() * 600], clu: [cx, cy], ph: r() * 6.28, x: 0, y: LH / 2 })
  }
  // prepared layout: two lattices (train 80% / test 20%), ordered by cluster so colours stay grouped
  const order = [...pts.keys()].sort((a, b) => pts[a].cl - pts[b].cl)
  const test = order.filter((_, k) => k % 5 === 4), train = order.filter((_, k) => k % 5 !== 4)
  const lay = (ids, x0, x1, y0, y1) => { const cols = Math.ceil(Math.sqrt(ids.length * (x1 - x0) / (y1 - y0))); const rows = Math.ceil(ids.length / cols); ids.forEach((id, k) => { pts[id].prep = [x0 + ((k % cols) + .5) * (x1 - x0) / cols, y0 + (Math.floor(k / cols) + .5) * (y1 - y0) / rows]; pts[id].set = ids === test ? 'test' : 'train' }) }
  lay(train, 90, 640, 130, 570); lay(test, 740, 910, 130, 570)
  // links: intra-cluster (weak), A-B positive (strong), C-D negative (strong, dashed)
  const idx = (c) => pts.map((p, i) => (p.cl === c ? i : -1)).filter((i) => i >= 0)
  const by = [0, 1, 2, 3].map(idx)
  const pick = (a) => a[Math.floor(r() * a.length)]
  const links = []
  for (let c = 0; c < 4; c++) for (let k = 0; k < 26; k++) links.push({ a: pick(by[c]), b: pick(by[c]), strong: false })
  for (let k = 0; k < 14; k++) links.push({ a: pick(by[0]), b: pick(by[1]), strong: true, neg: false })
  for (let k = 0; k < 14; k++) links.push({ a: pick(by[2]), b: pick(by[3]), strong: true, neg: true })
  const leak = []
  for (let k = 0; k < 10; k++) leak.push({ a: pick(by[k % 2]), b: pick(by[2 + (k % 2)]) })
  const counts = [0, 1, 2, 3].map((c) => by[c].length)
  return { pts, links, leak, counts, total: n }
}

export default function ParticleField({ layer, analysed, running, ariaLabel }) {
  const canvas = useRef(null), box = useRef(null)
  const [wrap, inView] = useInView(0.05)
  const reduced = useReducedMotion()
  const [tip, setTip] = useState(null)
  const n = typeof window !== 'undefined' && window.innerWidth < 640 ? 420 : 900
  const field = useMemo(() => buildField(n), [n])
  const eff = analysed ? layer : 'raw'
  const live = useRef({ eff, reduced })
  live.current = { eff, reduced }
  const api = useRef(null)
  useEffect(() => { if (reduced || !running || !inView) api.current?.() }, [eff, reduced, running, inView])

  useEffect(() => {
    const cv = canvas.current, ctx = cv.getContext('2d')
    let raf = 0, w = 0, h = 0, scale = 1, t0 = performance.now(), dead = false
    const { pts, links, leak } = field
    const size = () => {
      const rect = box.current.getBoundingClientRect(); const dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = Math.max(1, rect.width); h = Math.max(1, rect.height); cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr)
      scale = Math.min(w / LW, h / LH); ctx.setTransform(dpr * scale, 0, 0, dpr * scale, ((w - LW * scale) / 2) * dpr, ((h - LH * scale) / 2) * dpr)
    }
    const target = (p, mode, t) => mode === 'raw' ? [p.raw[0] + Math.sin(t / 1400 + p.ph) * 5, p.raw[1] + Math.cos(t / 1700 + p.ph) * 5] : mode === 'prepared' ? p.prep : p.clu
    const draw = (t) => {
      const { eff: mode } = live.current
      ctx.clearRect(-LW, -LH, LW * 3, LH * 3)
      ctx.strokeStyle = 'rgba(148,163,184,.07)'; ctx.lineWidth = 1; ctx.beginPath()
      for (let x = 0; x <= LW; x += 50) { ctx.moveTo(x, 0); ctx.lineTo(x, LH) } for (let y = 0; y <= LH; y += 50) { ctx.moveTo(0, y); ctx.lineTo(LW, y) } ctx.stroke()
      // ingestion point
      ctx.fillStyle = 'rgba(129,140,248,.9)'; ctx.beginPath(); ctx.arc(2, LH / 2, 5, 0, 6.3); ctx.fill()
      if (mode === 'prepared') { ctx.strokeStyle = 'rgba(148,163,184,.25)'; ctx.setLineDash([4, 6]); ctx.strokeRect(70, 105, 590, 490); ctx.strokeRect(720, 105, 210, 490); ctx.setLineDash([]); ctx.fillStyle = '#94a3b8'; ctx.font = '600 13px Inter, sans-serif'; ctx.fillText('TRAIN · ~80%', 78, 98); ctx.fillText('TEST · ~20%', 728, 98) }
      if (mode === 'relations') {
        for (const l of links) { const a = pts[l.a], b = pts[l.b]; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y)
          ctx.strokeStyle = l.strong ? (l.neg ? 'rgba(251,191,36,.45)' : 'rgba(45,212,191,.5)') : 'rgba(129,140,248,.14)'; ctx.setLineDash(l.neg ? [5, 5] : []); ctx.lineWidth = l.strong ? 1.4 : 1; ctx.stroke() } ctx.setLineDash([])
      }
      if (mode === 'leakage') {
        for (const l of leak) { const a = pts[l.a], b = pts[l.b]; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.strokeStyle = 'rgba(248,113,113,.75)'; ctx.lineWidth = 1.5; ctx.stroke()
          ctx.fillStyle = '#f87171'; ctx.beginPath(); ctx.arc(a.x, a.y, 3.5, 0, 6.3); ctx.arc(b.x, b.y, 3.5, 0, 6.3); ctx.fill() }
      }
      const hot = mode === 'anomalies' || mode === 'leakage' || mode === 'prepared'
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i]
        ctx.fillStyle = mode === 'raw' ? 'rgba(148,163,184,.75)' : p.anom && hot ? '#fbbf24' : p.anom ? 'rgba(251,191,36,.55)' : COLORS[p.cl]
        const s = p.anom && hot ? 5.5 : 3.8; ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s)
        if (p.anom && hot && mode !== 'prepared') { ctx.strokeStyle = 'rgba(251,191,36,' + (0.35 + 0.25 * Math.sin(t / 380 + p.ph)) + ')'; ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(p.x, p.y, 9 + 2 * Math.sin(t / 380 + p.ph), 0, 6.3); ctx.stroke() }
      }
    }
    const step = (t) => {
      if (dead) return
      const { eff: mode } = live.current
      for (const p of pts) { const [tx, ty] = target(p, mode, t); p.x += (tx - p.x) * 0.07; p.y += (ty - p.y) * 0.07 }
      draw(t); raf = requestAnimationFrame(step)
    }
    const still = () => { const { eff: mode } = live.current; for (const p of pts) { const [tx, ty] = target(p, mode, 0); p.x = tx; p.y = ty } draw(0) }
    api.current = still
    size()
    const ro = new ResizeObserver(() => { size(); if (live.current.reduced || !running) still() })
    ro.observe(box.current)
    if (live.current.reduced || !running || !inView) still(); else raf = requestAnimationFrame(step)
    return () => { dead = true; cancelAnimationFrame(raf); ro.disconnect() }
  }, [field, running, inView, reduced])

  const onMove = (e) => {
    const rect = box.current.getBoundingClientRect(); const sc = Math.min(rect.width / LW, rect.height / LH)
    const lx = (e.clientX - rect.left - (rect.width - LW * sc) / 2) / sc, ly = (e.clientY - rect.top - (rect.height - LH * sc) / 2) / sc
    const mode = live.current.eff; let text = null
    if (mode !== 'raw') {
      const a = field.pts.find((p) => p.anom && Math.hypot(p.x - lx, p.y - ly) < 14)
      if (a && ['anomalies', 'leakage', 'prepared'].includes(mode)) text = 'Unusual observation · flagged for inspection (illustrative)'
      else if (mode !== 'prepared') { const c = CENTERS.findIndex(([x, y]) => Math.hypot(x - lx, y - ly) < 85); if (c >= 0) text = `Cluster ${CENTERS[c][2]} · ${Math.round(100 * field.counts[c] / field.total)}% of observations (illustrative)` }
      else if (lx > 70 && lx < 660 && ly > 105 && ly < 595) text = 'Training set · fitted on, never evaluated on'
      else if (lx > 720 && lx < 930 && ly > 105 && ly < 595) text = 'Test set · held out for evaluation'
    } else if (Math.hypot(lx, ly - LH / 2) < 30) text = 'Ingestion point'
    setTip(text ? { x: e.clientX - rect.left, y: e.clientY - rect.top, text } : null)
  }
  return <div ref={(el) => { box.current = el; wrap.current = el }} className="relative h-full w-full" onMouseMove={onMove} onMouseLeave={() => setTip(null)}>
    <canvas ref={canvas} role="img" aria-label={ariaLabel} className="block h-full w-full" />
    {tip && <div className="pointer-events-none absolute z-10 max-w-[240px] rounded-md border border-slate-600 bg-slate-900/95 px-2.5 py-1.5 text-xs text-slate-100 shadow-lg" style={{ left: Math.min(tip.x + 14, (box.current?.clientWidth || 400) - 250), top: Math.max(tip.y - 38, 4) }}>{tip.text}</div>}
  </div>
}
