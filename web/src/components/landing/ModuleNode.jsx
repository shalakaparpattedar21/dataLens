/** Rounded-rectangle analytical module for the engine diagram (SVG group). */
export default function ModuleNode({ x, y, w = 270, h = 92, index, name, line, color, selected, dim, onSelect }) {
  return <g role="button" tabIndex={0} aria-pressed={selected} aria-label={`${name}: ${line}`} className="lp-node" opacity={dim ? 0.78 : 1}
    onClick={onSelect} onMouseEnter={onSelect} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect())}>
    <rect x={x} y={y} width={w} height={h} rx="14" fill={selected ? '#17224a' : '#101a33'} stroke={selected ? color : '#2a3a5f'} strokeWidth={selected ? 2.2 : 1.4} />
    <rect x={x} y={y + 14} width="4" height={h - 28} rx="2" fill={color} />
    <text x={x + 22} y={y + 30} fill={color} fontSize="12" fontWeight="700" letterSpacing="1.6" fontFamily="Inter, sans-serif">{String(index).padStart(2, '0')}</text>
    <text x={x + 22} y={y + 54} fill="#f1f5ff" fontSize="17" fontWeight="600" fontFamily="Inter, sans-serif">{name}</text>
    <text x={x + 22} y={y + 76} fill="#93a4c6" fontSize="13" fontFamily="Inter, sans-serif">{line}</text>
  </g>
}
