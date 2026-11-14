import { useEffect, useState } from 'react'
import { useReducedMotion } from '../../hooks/useMotion.js'

const GLYPHS = 'abcdefghijklmnopqrstuvwxyz0123456789·:/'
/** Headline whose letters resolve from noise into the final text. Screen readers and reduced-motion users get the final text immediately. */
export default function ResolveText({ text, ms = 1100 }) {
  const reduced = useReducedMotion()
  const [shown, setShown] = useState(reduced ? text : '')
  useEffect(() => {
    if (reduced) { setShown(text); return undefined }
    let raf = 0; const t0 = performance.now()
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / ms)
      const settled = Math.floor(p * text.length * 1.15)
      setShown(text.split('').map((c, i) => (c === ' ' || c === '\n' || i < settled ? c : GLYPHS[(Math.random() * GLYPHS.length) | 0])).join(''))
      if (p < 1 || settled < text.length) raf = requestAnimationFrame(tick); else setShown(text)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [text, ms, reduced])
  return <><span className="sr-only">{text.replace('\n', ' ')}</span><span aria-hidden="true" className="whitespace-pre-line">{shown || ' '}</span></>
}
