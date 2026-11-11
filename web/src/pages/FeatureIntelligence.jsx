import { useMemo, useState } from 'react'
import { Heatmap, BarList } from '../components/charts.jsx'
import { DataTable, Details, Figure, InfoBox, NeedsAnalysis, Section, Tip, fmt, num } from '../components/ui.jsx'

const strength = (v) => (v >= .9 ? 'very strong' : v >= .7 ? 'strong' : v >= .4 ? 'moderate' : 'weak')

export default function FeatureIntelligence({ ctx }) {
  const { analysis, dataset, profile, busy, runAnalysis, job } = ctx
  const rel = analysis?.relationships
  const [kind, setKind] = useState('pearson')
  const [view, setView] = useState('relevant')
  const [selected, setSelected] = useState(null)
  const heat = rel?.heatmap
  const relevant = useMemo(() => {
    if (!heat?.columns?.length) return []
    const want = new Set()
    rel.high_correlation_pairs.slice(0, 40).forEach((p) => { want.add(p.a); want.add(p.b) })
    rel.feature_target.slice(0, 10).forEach((r) => want.add(r.column))
    heat.columns.forEach((c) => { if (want.size < 20) want.add(c) })
    return heat.columns.filter((c) => want.has(c)).slice(0, 25)   // keeps the clustered order
  }, [rel, heat])
  if (!rel) return <NeedsAnalysis dataset={dataset} profile={profile} busy={busy || ['queued', 'running'].includes(job?.status)} onRun={runAnalysis} what="Feature intelligence" />

  const cols = view === 'all' || heat.columns.length <= 25 ? heat.columns : relevant
  const idx = cols.map((c) => heat.columns.indexOf(c))
  const matrix = idx.map((i) => idx.map((j) => heat[kind][i][j]))
  const sel = selected && heat.columns.includes(selected) ? selected : null
  const selRow = sel ? heat.columns.map((c, j) => ({ column: c, pearson: heat.pearson[heat.columns.indexOf(sel)][j], spearman: heat.spearman[heat.columns.indexOf(sel)][j] })).filter((r) => r.column !== sel).sort((a, b) => Math.abs(b[kind] ?? 0) - Math.abs(a[kind] ?? 0)).slice(0, 8) : []
  const selTarget = rel.feature_target.find((r) => r.column === sel)
  const severe = rel.vif.filter((v) => v.perfect_collinearity || (v.vif ?? 0) >= rel.vif_thresholds.severe)
  const warn = rel.vif.filter((v) => !v.perfect_collinearity && (v.vif ?? 0) >= rel.vif_thresholds.warning && (v.vif ?? 0) < rel.vif_thresholds.severe)
  const ft = rel.feature_target
  const mi = ft.filter((r) => r.type === 'numeric')
  return <div className="space-y-2">
    <div className="flex flex-wrap gap-x-10 gap-y-4 border-b border-slate-200 pb-5">
      <Figure label="Numeric columns analysed" value={num(heat.columns.length)} note={`sample of ${num(rel.sample.rows_sampled)} / ${num(rel.sample.rows_total)} rows`} />
      <Figure label={`Pairs with |r| ≥ ${rel.threshold}`} value={num(rel.high_correlation_pairs_total)} tone={rel.high_correlation_pairs_total ? 'warn' : undefined} />
      <Figure label="Redundancy groups" value={num(rel.redundancy_groups.length)} />
      <Figure label="VIF ≥ 10" value={num(severe.length)} tone={severe.length ? 'warn' : undefined} />
      <Figure label="Target" value={rel.target ?? 'none'} note={rel.target_kind} />
    </div>
    {rel.cap_note && <InfoBox tone="warn">{rel.cap_note}</InfoBox>}

    <Section title="Correlation heatmap" subtitle="Columns are ordered by hierarchical clustering so correlated features sit together. Indigo is positive, amber is negative, pale is weak.">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        <div className="flex gap-1" role="group" aria-label="Correlation method">{['pearson', 'spearman'].map((k) => <button key={k} onClick={() => setKind(k)} className={k === kind ? 'primary-btn !py-1.5' : 'secondary-btn !py-1.5'}>{k === 'pearson' ? 'Pearson (linear)' : 'Spearman (rank)'}</button>)}</div>
        {heat.columns.length > 25 && <label className="flex items-center gap-2 text-slate-600">Show<select aria-label="Heatmap columns" value={view} onChange={(e) => setView(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1 text-sm"><option value="relevant">Most relevant ({relevant.length})</option><option value="all">All {heat.columns.length}</option></select></label>}
        {sel && <button className="secondary-btn !py-1.5" onClick={() => setSelected(null)}>Clear selection: {sel}</button>}
      </div>
      {cols.length >= 2 ? <div className="grid gap-5 xl:grid-cols-[1fr_300px]">
        <Heatmap cell={cols.length <= 12 ? 34 : cols.length <= 30 ? 24 : 20} columns={cols} matrix={matrix} selected={sel} onSelect={(c) => setSelected(c === sel ? null : c)} />
        <aside className="text-sm" aria-label="Feature inspector">{sel ? <><h3 className="mb-2">{sel}</h3>
          {selTarget && <p className="mb-2 text-xs text-slate-500">Target association: {selTarget.mutual_information !== undefined ? `MI ${selTarget.mutual_information}` : `Cramér's V ${selTarget.cramers_v}`}</p>}
          <p className="mb-1 text-xs text-slate-500">Strongest relationships ({kind}):</p>
          <ul className="space-y-1">{selRow.map((r) => <li key={r.column} className="flex justify-between gap-2 text-xs"><button className="truncate text-left text-indigo-700 hover:underline" onClick={() => setSelected(r.column)} title={r.column}>{r.column}</button><span className="num text-slate-600">{fmt(r[kind])} <span className="text-slate-400">{r[kind] != null ? strength(Math.abs(r[kind])) : ''}</span></span></li>)}</ul></>
          : <p className="text-xs text-slate-400">Click a label or a row of the heatmap to inspect one feature: its strongest relationships and target association appear here.</p>}</aside>
      </div> : <p className="text-sm text-slate-400">At least two numeric, non-constant columns are needed for a correlation matrix.</p>}
    </Section>

    <Section title="Highly correlated pairs" subtitle={`Pairs where either Pearson or Spearman reaches ${rel.threshold}. ${rel.high_correlation_pairs_total > rel.high_correlation_pairs.length ? `Showing the strongest ${rel.high_correlation_pairs.length} of ${num(rel.high_correlation_pairs_total)}.` : ''}`}>
      <DataTable caption="Highly correlated pairs" rows={rel.high_correlation_pairs} searchKeys={['a', 'b']} initialSort={{ key: 'abs_max', dir: 'desc' }} empty="No pair reaches the threshold."
        columns={[{ key: 'a', label: 'Feature A', render: (r) => <button className="text-indigo-700 hover:underline" onClick={() => setSelected(r.a)}>{r.a}</button> }, { key: 'b', label: 'Feature B', render: (r) => <button className="text-indigo-700 hover:underline" onClick={() => setSelected(r.b)}>{r.b}</button> },
          { key: 'pearson', label: 'Pearson', num: true }, { key: 'spearman', label: 'Spearman', num: true }, { key: 'abs_max', label: '|max|', num: true, render: (r) => <>{fmt(r.abs_max)} <span className="text-slate-400">{strength(r.abs_max)}</span></> }]} />
    </Section>

    <Section title="Redundancy findings" subtitle="Correlated columns are grouped; one column per group is suggested to keep. This is a heuristic starting point, not a verdict.">
      {rel.redundancy_groups.length ? <div className="space-y-2">{rel.redundancy_groups.map((g) => <Details key={g.keep} summary={<>Keep <b>{g.keep}</b> · review {g.candidates.length} other{g.candidates.length > 1 ? 's' : ''}</>}>
        <p>Group: {g.members.join(', ')}</p><p className="mt-1 text-xs text-slate-500">Basis: {g.basis}. DataLens cannot yet drop selected columns; remove them from the CSV or select features while modelling.</p></Details>)}</div> : <p className="text-sm text-slate-400">No redundant groups at this threshold.</p>}
    </Section>

    <Section title="Feature–target relationships" subtitle={rel.target ? `Association of each feature with “${rel.target}” (${rel.target_kind}). Mutual information is unit-free and sign-less; Cramér's V is 0–1.` : 'No usable target, so no feature–target ranking.'}>
      {rel.target && ft.length ? <div className="grid gap-6 lg:grid-cols-2"><div><h4 className="mb-3 text-sm font-semibold text-slate-700">Numeric: mutual information<Tip text="k-NN estimator on ≤20,000 rows. Higher = more information about the target. It does not say whether the relationship is causal or legitimate." /></h4>
        <BarList rows={mi.slice(0, 15).map((r) => ({ label: r.column, value: r.mutual_information, display: r.mutual_information.toFixed(4) }))} /></div>
        <DataTable caption="Feature target association" rows={ft} searchKeys={['column']} pageSize={8} columns={[{ key: 'column', label: 'Feature' }, { key: 'type', label: 'Type' }, { key: 'mutual_information', label: 'MI', num: true }, { key: 'cramers_v', label: "Cramér's V", num: true }]} /></div>
        : <p className="text-sm text-slate-400">Choose a target on the Prepare page, then re-run the analysis.</p>}
    </Section>

    <Section title="Multicollinearity" subtitle="Variance Inflation Factor: how much a feature's variance is inflated by the others. Above 5 is a warning, above 10 is severe.">
      {rel.vif.length ? <div className="grid gap-6 lg:grid-cols-2"><div>{severe.length > 0 && <InfoBox tone="warn" title={`${severe.length} severe:`}>{severe.slice(0, 6).map((v) => v.column).join(', ')}{severe.length > 6 ? '…' : ''}</InfoBox>}
        {!severe.length && warn.length > 0 && <InfoBox tone="warn">{warn.length} feature(s) above VIF 5.</InfoBox>}{!severe.length && !warn.length && <InfoBox tone="ok">No VIF above 5.</InfoBox>}
        <div className="mt-4"><BarList max={Math.max(10, ...rel.vif.map((v) => v.vif ?? 0))} rows={rel.vif.slice(0, 10).map((v) => ({ label: v.column, value: v.vif ?? 100, display: v.perfect_collinearity ? 'perfect collinearity' : v.vif.toFixed(1), color: v.perfect_collinearity || v.vif >= 10 ? '#b45309' : '#6b7bd6' }))} /></div></div>
        <DataTable caption="VIF" rows={rel.vif} searchKeys={['column']} pageSize={8} columns={[{ key: 'column', label: 'Feature' }, { key: 'vif', label: 'VIF', num: true, render: (r) => (r.perfect_collinearity ? '∞' : fmt(r.vif)) }]} /></div>
        : <p className="text-sm text-slate-400">Not enough usable numeric columns or rows for VIF.</p>}
    </Section>

    {rel.categorical_pairs.length > 0 && <Section title="Categorical association" subtitle="Bias-corrected Cramér's V between categorical features (≥ 0.5 shown).">
      <DataTable rows={rel.categorical_pairs} columns={[{ key: 'a', label: 'Feature A' }, { key: 'b', label: 'Feature B' }, { key: 'cramers_v', label: "Cramér's V", num: true }]} /></Section>}
    {rel.skipped.length > 0 && <Details summary={`${rel.skipped.length} column(s) skipped, with reasons`}><ul className="space-y-1 text-xs">{rel.skipped.slice(0, 40).map((s) => <li key={s.column}><b>{s.column}</b>: {s.reason}</li>)}</ul></Details>}
    <Details summary="Methodology and limits"><ul className="space-y-1 text-xs">{Object.entries(rel.methodology).map(([k, v]) => <li key={k}><b>{k}:</b> {v}</li>)}</ul></Details>
  </div>
}
