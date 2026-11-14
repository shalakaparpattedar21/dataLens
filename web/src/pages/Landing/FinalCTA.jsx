export default function FinalCTA({ onEnter, onExplore }) {
  return <div className="relative overflow-hidden rounded-3xl border border-slate-700/70 bg-[#0b1226] px-6 py-16 sm:px-12 sm:py-24">
    <svg aria-hidden="true" className="absolute inset-0 h-full w-full opacity-60" preserveAspectRatio="xMidYMid slice" viewBox="0 0 1000 400"><defs><pattern id="fc-g" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="#17213f" /></pattern></defs><rect width="1000" height="400" fill="url(#fc-g)" /></svg>
    <div className="relative max-w-3xl"><h2 className="lp-h2 !text-white">Your next dataset deserves a closer look.</h2>
      <p className="mt-5 max-w-2xl text-[18px] leading-relaxed text-slate-300">Bring your data into DataLens. Discover what is hidden, understand what needs attention and prepare with confidence.</p>
      <div className="mt-8 flex flex-wrap gap-3"><button onClick={onEnter} className="lp-cta">Enter the DataLens workspace →</button><button onClick={onExplore} className="lp-cta-2">Explore how it works</button></div></div>
  </div>
}
