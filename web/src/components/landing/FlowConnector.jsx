/** Directional connector. `active` animates a flowing dash; reduced motion is handled in CSS (.lp-flow). */
export default function FlowConnector({ d, color = '#5b6f96', active, dim }) {
  return <g opacity={dim ? 0.35 : 1}>
    <path d={d} fill="none" stroke={color} strokeWidth={active ? 2.4 : 1.4} strokeOpacity={active ? 1 : 0.55} />
    {active && <path d={d} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" className="lp-flow" />}
  </g>
}
