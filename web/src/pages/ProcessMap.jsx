import { useState } from 'react'
import { PageHeader, num } from '../components/ui.jsx'
import { running } from '../api.js'

/*
 * Process map: how DataLens operations connect, drawn on a dark technical canvas.
 * Every node's state and caption is derived from real backend state (dataset, profile, analysis, run, leakage); nothing is decorative data.
 * Shapes: rounded rectangle = process module · pill = start/end · diamond = decision · folded-corner document = deliverable.
 */
const W = 1180, H = 580
const LANES = [['INGEST', 30, 180], ['ANALYSE', 210, 190], ['PREPARE · VALIDATE · DELIVER', 400, 170]]
const STATE = {
  done: { stroke: 'var(--c-done)', fill: '#0f2a22', label: 'Done' },
  ready: { stroke: 'var(--c-action)', fill: '#1b1f4d', label: 'Next' },
  attention: { stroke: 'var(--c-critical)', fill: '#3a1218', label: 'Needs attention' },
  pending: { stroke: '#3a4a6b', fill: 'var(--canvas-node)', label: 'Waiting' },
}
const KIND = { ingest: 'var(--c-ingest)', analysis: 'var(--c-analysis)', decision: 'var(--c-decision)', deliver: 'var(--c-done)', plain: 'var(--c-action)' }

export function mapState(ctx) {
  const { dataset, profile, analysis, run, runOk, runLeakage, runs } = ctx
  const a = analysis || {}
  const confirmed = (runLeakage?.findings || []).concat(a.leakage?.findings || []).filter((f) => f.status === 'confirmed').length
  const next = !dataset ? 'upload' : !profile ? 'profile' : !a.health ? 'analyse' : !run ? 'prepare' : 'export'
  const st = (done, key, bad) => bad ? 'attention' : done ? 'done' : next === key ? 'ready' : 'pending'
  const rec = a.recommendations?.items?.length
  return { next, confirmed, nodes: {
    start: { s: dataset ? 'done' : 'ready', sub: '' },
    upload: { s: st(!!dataset, 'upload'), sub: dataset ? dataset.name : 'Upload CSV or register CIC-IDS2017', page: 'Datasets' },
    profile: { s: st(!!profile, 'profile'), sub: profile ? `${num(profile.rows)} rows · ${profile.columns} cols` : 'chunked full-data scan', page: 'Overview' },
    analyse: { s: st(!!a.health, 'analyse'), sub: a.health ? 'analysis stored' : 'seeded ≤50k-row sample', page: 'Investigate' },
    fi: { s: a.relationships ? 'done' : 'pending', sub: a.relationships ? `${a.relationships.high_correlation_pairs_total} correlated pairs` : 'not run', page: 'Feature Intelligence' },
    an: { s: a.anomalies ? 'done' : 'pending', sub: a.anomalies ? `${num(a.anomalies.summary.flagged)} flagged` : 'not run', page: 'Anomaly Analysis' },
    lk: { s: a.leakage ? (confirmed ? 'attention' : 'done') : 'pending', sub: a.leakage ? `${confirmed} confirmed` : 'not run', page: 'Leakage Intelligence' },
    hl: { s: a.health ? 'done' : 'pending', sub: a.health?.overall != null ? `score ${Math.round(a.health.overall)} / 100` : 'not run', page: 'Dataset Health' },
    rec: { s: a.recommendations ? 'done' : 'pending', sub: a.recommendations ? `${rec} recommendation${rec === 1 ? '' : 's'}` : 'needs analysis', page: 'Recommendations' },
    prep: { s: st(!!run, 'prepare'), sub: run ? `${num(run.rows.train)} train / ${num(run.rows.test)} test` : 'fit on train split only', page: 'Prepare' },
    leak: { s: !run ? 'pending' : confirmed ? 'attention' : 'done', sub: !run ? 'after preparation' : confirmed ? `${confirmed} confirmed` : 'none confirmed', page: 'Leakage Intelligence' },
    val: { s: !run ? 'pending' : runOk ? 'done' : 'attention', sub: !run ? 'after preparation' : runOk ? 'no missing / infinite' : 'values remain', page: 'Prepare' },
    exp: { s: run ? 'done' : 'pending', sub: run ? `${runs.filter((r) => r.dataset_id === dataset.id).length} run(s)` : 'train · test · reports', page: 'Exports' },
    end: { s: run && runOk ? 'done' : 'pending', sub: '' },
  } }
}

function Node({ id, kind, shape = 'rect', x, y, w = 170, h = 66, title, n, onGo, onFocus, active }) {
  const S = STATE[n.s]
  const go = () => n.page && onGo(n.page)
  const cx = x + w / 2, cy = y + h / 2
  let body
  if (shape === 'pill') body = <rect x={x} y={y} width={w} height={h} rx={h / 2} fill={S.fill} stroke={S.stroke} strokeWidth="2" />
  else if (shape === 'diamond') body = <polygon points={`${cx},${y} ${x + w},${cy} ${cx},${y + h} ${x},${cy}`} fill={S.fill} stroke={n.s === 'pending' ? S.stroke : S.stroke} strokeWidth="2" />
  else if (shape === 'doc') body = <path d={`M${x},${y} H${x + w - 18} L${x + w},${y + 18} V${y + h - 6} Q${x + w * .75},${y + h + 8} ${cx},${y + h - 4} T${x},${y + h - 2} Z`} fill={S.fill} stroke={S.stroke} strokeWidth="2" />
  else body = <><rect x={x} y={y} width={w} height={h} rx="12" fill={S.fill} stroke={S.stroke} strokeWidth="2" /><rect x={x} y={y + 10} width="4" height={h - 20} rx="2" fill={KIND[kind]} /></>
  const lines = shape === 'diamond' ? title.split(' / ') : [title]
  const interactive = !!n.page
  return <g role={interactive ? 'link' : 'img'} tabIndex={interactive ? 0 : undefined} aria-label={`${title.replace(' / ', ' ')}: ${STATE[n.s].label}${n.sub ? '. ' + n.sub : ''}`}
    className={'pm-node' + (active ? ' pm-active' : '')} data-node={id} onClick={go} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), go())} onFocus={() => onFocus(id)} onMouseEnter={() => onFocus(id)}>
    {n.s === 'ready' && <rect x={x - 4} y={y - 4} width={w + 8} height={h + 8} rx={shape === 'pill' ? (h + 8) / 2 : 15} fill="none" stroke="var(--c-action)" strokeOpacity=".45" strokeDasharray="4 4" />}
    {body}
    {lines.map((t, i) => <text key={t} x={cx + (shape === 'rect' ? 4 : 0)} y={cy - (n.sub && shape !== 'diamond' ? 6 : 0) + (lines.length > 1 ? (i - .5) * 15 + 5 : 5)} textAnchor="middle" fill="var(--canvas-text)" fontSize="15" fontFamily="Inter, sans-serif" fontWeight="600">{t}</text>)}
    {n.sub && shape !== 'diamond' && <text x={cx + (shape === 'rect' ? 4 : 0)} y={cy + 16} textAnchor="middle" fill="var(--canvas-muted)" fontSize="12" fontFamily="Inter, sans-serif">{n.sub.length > 28 ? n.sub.slice(0, 27) + '…' : n.sub}</text>}
  </g>
}

const Arrow = ({ d, dashed, label, lx, ly, color = '#5b6f96' }) => <g><path d={d} fill="none" stroke={color} strokeWidth="2" strokeDasharray={dashed ? '5 5' : undefined} markerEnd="url(#pm-arrow)" />{label && <text x={lx} y={ly} fill="var(--canvas-muted)" fontSize="11.5" fontFamily="Inter, sans-serif">{label}</text>}</g>

export default function ProcessMap({ ctx }) {
  const { dataset, profile, job, busy, go } = ctx
  const { nodes: N, next, confirmed } = mapState(ctx)
  const [focus, setFocus] = useState(null)
  const busyNow = busy || running(job)
  const action = { upload: ['Upload CSV', () => ctx.pick()], profile: ['Run profile', () => ctx.profileDataset(dataset?.id)], analyse: ['Run analysis', ctx.runAnalysis], prepare: ['Prepare data', () => go('Prepare')], export: ['Open exports', () => go('Exports')] }[next]
  const props = (id, extra) => ({ id, n: N[id], onGo: go, onFocus: setFocus, active: focus === id, ...extra })
  const hint = focus && N[focus]
  return <div className="space-y-6">
    <PageHeader crumbs={['Workspace', dataset?.name || 'no dataset', 'Process Map']} title="How DataLens works on your data"
      description="Each node is a real step. Its colour and caption come from the current dataset, analysis and prepared run, and selecting it opens that step."
      actions={<button className="primary-btn" disabled={busyNow || (next === 'profile' && !dataset)} onClick={action[1]}>{busyNow ? 'Working…' : action[0] + ' →'}</button>} />
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-500" aria-label="Legend">
      {Object.entries(STATE).map(([k, v]) => <span key={k} className="inline-flex items-center gap-1.5"><i className="inline-block h-3 w-3 rounded-sm border-2" style={{ borderColor: v.stroke, background: v.fill }} />{v.label}</span>)}
      <span>▭ process · ⬭ start/end · ◇ decision · ▱ deliverable</span></div>
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-[var(--canvas)]">
      <div className="soft-scroll overflow-x-auto" tabIndex={0} aria-label="Process map canvas (scrolls horizontally on small screens)">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto min-w-[980px] w-full" role="group" aria-label="DataLens process map">
          <defs>
            <pattern id="pm-grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="var(--canvas-grid)" strokeWidth="1" /></pattern>
            <marker id="pm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" orient="auto"><path d="M0 0L10 5L0 10z" fill="#7f93bb" /></marker>
          </defs>
          <rect width={W} height={H} fill="url(#pm-grid)" />
          {LANES.map(([name, y, h], i) => <g key={name}><rect x="12" y={y} width={W - 24} height={h} rx="10" fill={i % 2 ? 'transparent' : 'var(--canvas-lane)'} stroke="#223253" strokeDasharray="3 5" /><text x={W - 28} y={y + 22} textAnchor="end" fill="var(--canvas-muted)" fontSize="11.5" letterSpacing="2.2" fontFamily="Inter, sans-serif" fontWeight="700">{name}</text></g>)}
          <rect x="252" y="236" width="772" height="140" rx="12" fill="none" stroke="var(--c-analysis)" strokeOpacity=".4" strokeDasharray="6 5" />
          <text x="268" y="256" fill="var(--c-analysis)" fillOpacity=".85" fontSize="11.5" letterSpacing="1.6" fontFamily="Inter, sans-serif" fontWeight="700">PRODUCED BY ONE ANALYSIS JOB</text>
          {/* connectors */}
          <Arrow d="M170 110 H230" /><Arrow d="M400 110 H470" />
          <Arrow d="M555 143 V198 H120 V281" /><Arrow d="M205 316 H280" />
          <Arrow d="M450 316 H470" /><Arrow d="M640 316 H660" /><Arrow d="M830 316 H850" />
          <Arrow d="M640 376 V392 H120 V442" />
          <Arrow d="M205 477 H260" /><Arrow d="M430 477 H495" />
          <Arrow d="M610 477 H640" label="no" lx="618" ly="468" /><Arrow d="M735 477 H775" />
          <Arrow d="M925 477 H950" />
          {/* branch arrows */}
          <Arrow d="M552 513 V540" dashed label="yes" lx="560" ly="530" color="#ef4444" />
          <Arrow d="M688 513 V540" dashed label="fail" lx="696" ly="530" color="#f59e0b" />
          {/* nodes: lane 1 */}
          <Node {...props('start', { shape: 'pill', x: 40, y: 92, w: 130, h: 36, title: 'Start', kind: 'plain' })} />
          <Node {...props('upload', { x: 230, y: 77, w: 170, title: 'Upload / register', kind: 'ingest' })} />
          <Node {...props('profile', { x: 470, y: 77, w: 170, title: 'Understand', kind: 'ingest' })} />
          {/* lane 2 */}
          <Node {...props('analyse', { x: 40, y: 283, w: 165, title: 'Investigate', kind: 'analysis' })} />
          <Node {...props('fi', { x: 280, y: 283, w: 170, title: 'Feature Intelligence', kind: 'analysis' })} />
          <Node {...props('an', { x: 470, y: 283, w: 170, title: 'Anomaly Analysis', kind: 'analysis' })} />
          <Node {...props('lk', { x: 660, y: 283, w: 170, title: 'Leakage Intelligence', kind: 'analysis' })} />
          <Node {...props('hl', { x: 850, y: 283, w: 160, title: 'Dataset Health', kind: 'analysis' })} />
          {/* lane 3 */}
          <Node {...props('rec', { x: 40, y: 444, w: 165, title: 'Recommend', kind: 'plain' })} />
          <Node {...props('prep', { x: 260, y: 444, w: 170, title: 'Prepare', kind: 'plain' })} />
          <Node {...props('leak', { shape: 'diamond', x: 495, y: 437, w: 115, h: 76, title: 'Leakage / found?', kind: 'decision' })} />
          <Node {...props('val', { shape: 'diamond', x: 640, y: 437, w: 95, h: 76, title: 'Valid?', kind: 'decision' })} />
          <Node {...props('exp', { shape: 'doc', x: 775, y: 448, w: 150, h: 58, title: 'Export', kind: 'deliver' })} />
          <Node {...props('end', { shape: 'pill', x: 950, y: 459, w: 100, h: 36, title: 'End', kind: 'plain' })} />
          <text x="552" y="558" textAnchor="middle" fill={confirmed ? '#fca5a5' : 'var(--canvas-muted)'} fontSize="12" fontFamily="Inter, sans-serif">Review leakage</text>
          <text x="688" y="558" textAnchor="middle" fill="var(--canvas-muted)" fontSize="12" fontFamily="Inter, sans-serif">Adjust recipe</text>
        </svg>
      </div>
      <div className="border-t border-slate-800 px-4 py-2.5 text-[13px] text-slate-300" role="status" aria-live="polite">
        {hint ? <span><b>{STATE[hint.s].label}</b>{hint.sub ? ' · ' + hint.sub : ''}{hint.page ? ` · opens ${hint.page}` : ''}</span> : <span className="text-slate-400">Hover or focus a node to see its state. {profile ? '' : 'Start by uploading a CSV.'}</span>}
      </div>
    </div>
    <p className="text-xs text-slate-500">The diamonds are decisions made from measured results: leakage is flagged only when a finding is <b>confirmed</b>, and validation passes only when the prepared features hold no missing or infinite values. Passing validation is not a full ML-readiness verdict.</p>
  </div>
}
