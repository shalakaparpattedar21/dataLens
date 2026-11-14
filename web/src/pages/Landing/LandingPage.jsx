import { useState } from 'react'
import '../../styles/landing.css'
import ResolveText from '../../components/landing/ResolveText.jsx'
import { useInView } from '../../hooks/useMotion.js'
import DataJourney from './DataJourney.jsx'
import FinalCTA from './FinalCTA.jsx'
import HeroVisualization from './HeroVisualization.jsx'
import InsightVisuals from './InsightVisuals.jsx'
import IntelligenceEngine from './IntelligenceEngine.jsx'
import PreparationFlow from './PreparationFlow.jsx'
import ProductShowcase from './ProductShowcase.jsx'
import logo from '../../assets/logo.png'
function Reveal({ children, className = '' }) {
  const [ref, seen] = useInView(0.08)
  const [once, setOnce] = useState(false)
  if (seen && !once) setOnce(true)
  return <div ref={ref} className={'lp-reveal ' + (once ? 'lp-reveal-in ' : '') + className}>{children}</div>
}
const Head = ({ n, label, title, children }) => <div className="mb-10 max-w-4xl sm:mb-14"><div className="lp-eyebrow">{n} · {label}</div><h2 className="lp-h2 mt-3">{title}</h2>{children && <p className="mt-4 max-w-2xl text-[17px] leading-relaxed text-slate-400">{children}</p>}</div>
const Wrap = ({ children, id, className = '' }) => <section id={id} className={'lp-section scroll-mt-16 ' + className}><div className="mx-auto w-full max-w-[1280px] px-5 sm:px-8">{children}</div></section>

export default function LandingPage({ onEnter, onOpen }) {
  const go = (id) => document.getElementById(id)?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  return <div className="lp-root">
    <header className="lp-nav sticky top-0 z-30 border-b border-slate-800/80 bg-[#070c1a]/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1280px] items-center justify-between gap-4 px-5 sm:px-8">
        <a href="#/" className="flex items-center gap-2.5" aria-label="DataLens home"><span className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-500 text-white"><img src={logo} alt="DataLens" className="h-10 w-10 rounded-lg object-contain" /></span><span className="serif text-[21px] text-white">DataLens</span></a>
        <nav aria-label="Sections" className="hidden items-center gap-7 md:flex">{[['engine', 'Engine'], ['how-it-works', 'How it works'], ['product', 'Product'], ['insight', 'Insight'], ['output', 'Output']].map(([id, l]) => <button key={id} className="lp-navlink" onClick={() => go(id)}>{l}</button>)}</nav>
        <button onClick={onEnter} className="lp-chip !bg-indigo-500 !border-indigo-400 !text-white">Enter DataLens →</button></div></header>

    <main>
      <section className="lp-hero-glow relative">
        <div className="mx-auto grid w-full max-w-[1400px] items-center gap-10 px-5 py-12 sm:px-8 lg:min-h-[calc(100vh-56px)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-8 lg:py-10">
          <div>
            <div className="lp-eyebrow">DATA INTELLIGENCE PLATFORM</div>
            <h1 className="lp-h1 mt-5"><ResolveText text={'Your data has\nmore to reveal.'} /></h1>
            <p className="mt-6 max-w-xl text-[18px] leading-relaxed text-slate-300">Discover hidden patterns, expose data quality issues, investigate anomalies and transform raw datasets into validated machine-learning-ready outputs.</p>
            <div className="mt-8 flex flex-wrap gap-3"><button onClick={onEnter} className="lp-cta">Enter DataLens →</button><button onClick={() => go('engine')} className="lp-cta-2">Explore the intelligence engine ↓</button></div>
            <p className="mt-6 text-sm text-slate-500">Local-first. Your CSV files stay on this machine and the originals are never modified.</p>
          </div>
          <HeroVisualization />
        </div>
      </section>
      <div className="lp-rule" />

      <Wrap id="engine"><Reveal><Head n="01" label="THE ENGINE" title="One dataset. Multiple layers of intelligence.">Six connected modules examine the same data from different angles. Select one to see what it does.</Head><IntelligenceEngine onOpen={onOpen} /></Reveal></Wrap>
      <div className="lp-rule" />
      <Wrap id="how-it-works"><Reveal><Head n="02" label="THE JOURNEY" title="From raw data to informed decisions.">Eight stages. Some run on their own, others wait for you. Each stage below says which.</Head><DataJourney /></Reveal></Wrap>
      <div className="lp-rule" />
      <Wrap id="product"><Reveal><Head n="03" label="THE PRODUCT" title="A real application, not a concept.">Screenshots below come from the running workspace.</Head><ProductShowcase /></Reveal></Wrap>
      <div className="lp-rule" />
      <Wrap id="insight"><Reveal><Head n="04" label="THE INSIGHT" title="Don’t just clean data. Understand it.">Three kinds of insight DataLens surfaces. The visuals here use illustrative demonstration data, clearly marked, and are not results from any real dataset.</Head><InsightVisuals /></Reveal></Wrap>
      <div className="lp-rule" />
      <Wrap id="output"><Reveal><Head n="05" label="THE OUTPUT" title="Make your dataset ready for the next experiment.">Configure the recipe, split, validate and export. Every run keeps its configuration and reports.</Head><PreparationFlow /></Reveal></Wrap>
      <Wrap className="!pt-4"><Reveal><FinalCTA onEnter={onEnter} onExplore={() => go('how-it-works')} /></Reveal></Wrap>
    </main>
    <footer className="border-t border-slate-800 py-8 text-center text-[13px] text-slate-500">DataLens · Local-first dataset intelligence · Demonstration visuals on this page are illustrative</footer>
  </div>
}
