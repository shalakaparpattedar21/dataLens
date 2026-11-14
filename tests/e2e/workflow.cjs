// Browser end-to-end check of the full DataLens workflow against a running backend + Vite dev server.
// Usage: NODE_PATH=$(npm root -g) node tests/e2e/workflow.cjs <csv> <scratch-dir> [base-url]
// Requires Playwright (not a project dependency) and servers on :8000 (uvicorn) and :5173 (npm run dev).
const { chromium } = require('playwright')
const fs = require('fs')
const [csv, scratch, base = 'http://localhost:5173'] = process.argv.slice(2)
;(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1360, height: 900 } })
  const errs = []; p.on('console', (m) => { if (m.type() === 'error' && !/status of 400/.test(m.text())) errs.push(m.text()) }); p.on('pageerror', (e) => errs.push('PAGEERR ' + e.message))
  let failed = 0
  const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) failed++ }
  const nav = (n) => p.locator('aside .nav-item', { hasText: n }).first().click()
  const done = (t) => p.getByText(t).first().waitFor({ timeout: 120000 })
  // ---- landing page ----
  await p.goto(base); await p.getByRole('heading', { name: 'Your data has more to reveal.' }).waitFor(); ok(true, 'L1 landing renders at root')
  ok(await p.locator('canvas[aria-label^="Illustrative animated dataset"]').count() === 1, 'L2 hero canvas present')
  const sig = async () => p.locator('canvas').first().evaluate((c) => { const x = c.getContext('2d'); const d = x.getImageData(0, 0, c.width, c.height).data; let h = 0; for (let i = 0; i < d.length; i += 97) h = (h * 31 + d[i]) | 0; return h })
  await p.waitForTimeout(2500); const s1 = await sig(); await p.getByRole('button', { name: /Anomalies/ }).click(); await p.waitForTimeout(1500); const s2 = await sig()
  ok(s1 !== s2, 'L3 hero visualization changes when an analysis layer is selected')
  ok((await p.getByText('Anomalies', { exact: true }).first().isVisible()) && await p.getByRole('status').filter({ hasText: 'highlighted for inspection' }).count() > 0, 'L4 layer caption updates')
  await p.getByRole('button', { name: 'Show raw data' }).click(); await p.getByRole('button', { name: 'Show analysed' }).waitFor(); ok(true, 'L5 raw / analysed toggle')
  await p.getByRole('button', { name: 'Pause animation' }).click(); await p.getByRole('button', { name: 'Resume animation' }).waitFor(); ok(true, 'L6 pause / resume')
  await p.getByRole('button', { name: 'Explore the intelligence engine' }).click(); await p.waitForTimeout(900)
  await p.getByRole('button', { name: /LEAKAGE INTELLIGENCE/ }).first().click(); ok(await p.getByRole('region', { name: /LEAKAGE INTELLIGENCE details/ }).getByText(/exact train\/test overlap/).count() > 0, 'L7 engine: selecting a module shows its explanation')
  await p.getByRole('button', { name: /^ANOMALY ANALYSIS/ }).first().click(); ok(await p.getByRole('region', { name: /ANOMALY ANALYSIS details/ }).getByText(/Choose a detector/).count() > 0, 'L8 engine: module switch')
  await p.getByRole('button', { name: /VALIDATE/ }).click(); ok(await p.getByRole('region', { name: 'Stage details' }).getByText(/not a full ML-readiness verdict/).count() > 0, 'L9 journey stage selectable')
  const img0 = await p.locator('figure img').first().getAttribute('src'); await p.getByRole('button', { name: /Dataset Health/ }).first().click(); await p.waitForTimeout(300)
  ok((await p.locator('figure img').first().getAttribute('src')) !== img0, 'L10 showcase switches preview')
  ok(await p.getByText('ILLUSTRATIVE', { exact: true }).count() >= 3, 'L11 illustrative data labelled')
  for (const w of [1440, 1280, 768, 390]) { await p.setViewportSize({ width: w, height: 900 }); await p.waitForTimeout(250); ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `L12 landing: no horizontal overflow at ${w}px`) }
  await p.setViewportSize({ width: 390, height: 844 }); await p.getByRole('list', { name: 'Analytical modules' }).scrollIntoViewIfNeeded(); ok(await p.getByRole('list', { name: 'Analytical modules' }).isVisible(), 'L13 mobile: stacked module list')
  await p.setViewportSize({ width: 1360, height: 900 })
  await p.evaluate(() => window.scrollTo(0, 0)); await p.getByRole('button', { name: 'Enter DataLens →' }).first().click(); await p.getByRole('heading', { name: 'How DataLens works on your data' }).waitFor(); ok(p.url().endsWith('#/app'), 'L14 CTA enters the workspace (#/app)')
  await p.goBack(); await p.getByRole('heading', { name: 'Your data has more to reveal.' }).waitFor(); ok(true, 'L15 browser back returns to landing')
  await p.goForward(); await p.getByRole('heading', { name: 'How DataLens works on your data' }).waitFor(); ok(true, 'L16 browser forward returns to workspace')
  await p.reload(); await p.getByRole('heading', { name: 'How DataLens works on your data' }).waitFor(); ok(true, 'L17 refresh on #/app stays in workspace')
  await p.getByRole('link', { name: 'Back to home page' }).click(); await p.getByRole('heading', { name: 'Your data has more to reveal.' }).waitFor(); ok(true, 'L18 Home link returns to landing')
  await p.getByRole('button', { name: 'Explore how it works' }).click().catch(() => {}); await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await p.waitForTimeout(500)
  await p.getByRole('button', { name: 'Enter the DataLens workspace →' }).click(); await p.getByRole('heading', { name: 'How DataLens works on your data' }).waitFor(); ok(true, 'L19 final CTA enters workspace')
  // ---- workspace ----
  await p.getByRole('heading', { name: 'How DataLens works on your data' }).waitFor(); ok(await p.locator('[data-node]').count() === 14, 'process map renders 14 nodes')
  ok(await p.locator('[data-node=upload]').getAttribute('aria-label').then((t) => t.includes('Next')), 'map: upload is the next step with no dataset')
  await nav('Overview'); await p.getByText('Start with a dataset').waitFor(); ok(true, 'empty state')
  fs.writeFileSync(scratch + '/bad.csv', 'a,b\n'); await p.setInputFiles('input[type=file]', scratch + '/bad.csv')
  await p.getByRole('alert').first().waitFor(); ok((await p.getByRole('alert').first().innerText()).includes('no data rows'), '1 bad upload rejected with message')
  await p.getByLabel('Dismiss error').click()
  await p.setInputFiles('input[type=file]', csv); await done('Profile complete.'); ok(true, '1-2 upload + profile')
  await nav('Investigate'); await p.getByText('Analysis not run yet.').waitFor(); ok(true, '3 Investigate opens; analysis offered')
  for (const pg of ['Feature Intelligence', 'Anomaly Analysis', 'Leakage Intelligence', 'Dataset Health']) { await nav(pg); ok(await p.getByRole('button', { name: 'Run analysis' }).count() > 0, `${pg}: empty state offers analysis`) }
  await nav('Investigate'); await p.getByRole('button', { name: 'Run analysis' }).first().click(); await done('Analysis complete.'); ok(true, 'full analysis job complete')
  ok(await p.getByText('Recommended preprocessing').count() === 1, 'recommendations section')
  ok(await p.getByRole('img', { name: /Histogram of/ }).count() > 0 && await p.getByRole('img', { name: /Box plot of/ }).count() > 0, 'histogram + box plots from backend')
  // 8 accept + customise + apply recommendations
  await p.getByRole('button', { name: /Review recommendations/ }).click(); await p.getByRole('heading', { name: 'Recommendations', exact: true }).waitFor(); ok(true, 'Investigate links to Recommendations page')
  await p.getByRole('button', { name: 'Accept', exact: true }).first().click()
  await p.getByRole('button', { name: /Apply 1 accepted to Prepare/ }).click(); await p.getByText('Applied from recommendations:').waitFor(); ok(true, '8 recommendation accepted and applied to Prepare (explicit action)')
  // 4 feature intelligence
  await nav('Feature Intelligence'); await p.getByRole('img', { name: 'Correlation heatmap' }).waitFor()
  ok(await p.locator('svg[aria-label="Correlation heatmap"] rect').count() > 4, '4 heatmap rendered from backend matrix')
  await p.locator('svg[aria-label="Correlation heatmap"] text').nth(2).click(); ok(await p.getByRole('complementary', { name: 'Feature inspector' }).getByRole('heading').count() === 1, 'heatmap feature selection opens inspector')
  ok(await p.getByText('Highly correlated pairs').count() > 0 && await p.getByText('Multicollinearity').count() > 0 && await p.getByText('Redundancy findings').count() > 0, 'pairs / redundancy / VIF sections')
  // 5 anomalies
  await nav('Anomaly Analysis'); await p.getByLabel('Method').selectOption('lof'); await p.getByRole('button', { name: 'Run detection' }).click(); await done('Anomaly detection complete.')
  ok((await p.locator('svg[aria-label^="Scatter"] circle').count()) > 50, '5 anomaly scatter drawn')
  ok(await p.getByText('Local Outlier Factor').count() > 0, 'LOF result shown'); ok((await p.locator('table tbody tr').count()) > 0, 'flagged records table populated')
  await p.getByLabel('Search table').first().fill('zzzzzz'); ok(await p.getByText('No rows.').count() > 0, 'table search/empty state')
  // 6 leakage (source level)
  await nav('Leakage Intelligence'); ok(await p.getByText(/alone predicts the target/).count() > 0, '6 suspicious feature flagged')
  ok(await p.locator('.st-potential').count() > 0 && await p.locator('.st-not_assessed').count() > 0, 'potential and not-assessed distinguished')
  // 7 health
  await nav('Dataset Health'); ok(await p.getByText('DataLens Health Score').count() === 1 && await p.getByText('Is this dataset ready for machine learning?').count() === 1, '7 health score + readiness')
  await p.getByText('How the score is calculated').click(); ok(await p.getByText(/capped/).count() > 0, 'methodology documented')
  // 9-10 prepare + validate (keep duplicates so overlap is confirmed)
  await nav('Prepare data'); await p.getByLabel('Duplicate policy').selectOption('keep'); await p.getByLabel('Dataset size').selectOption('1'); await p.getByRole('button', { name: /Prepare and validate/ }).click(); await done('Preparation complete and validated.')
  ok(await p.getByText(/Preprocessing validation passed/).count() === 1, '10 validation derived from run')
  ok(await p.locator('a.download-link').count() >= 6, '11 download links visible')
  await nav('Leakage Intelligence'); await p.locator('.st-confirmed').first().waitFor({ timeout: 20000 }); ok(true, 'confirmed exact overlap after prepare')
  ok(await p.getByText(/Also in train/).count() > 0, 'overlap visualization')
  await nav('Dataset Health'); await p.getByText('High risk').first().waitFor({ timeout: 20000 }); ok(true, 'readiness = High risk (leakage not hidden by completeness)')
  // 11 exports
  await nav('Process Map'); ok((await p.locator('[data-node=prep]').getAttribute('aria-label')).includes('Done') && (await p.locator('[data-node=leak]').getAttribute('aria-label')).includes('Needs attention'), 'map reflects prepared run + confirmed leakage')
  await nav('Leakage Intelligence'); await p.getByRole('button', { name: 'Confirmed', exact: true }).click(); ok(await p.locator('details .st-potential').count() === 0 && await p.locator('details .st-confirmed').count() > 0, 'status filter: Confirmed only')
  await p.getByRole('button', { name: 'Low', exact: true }).click(); await p.getByText('No findings match these filters.').waitFor(); ok(true, 'severity filter narrows to empty with message')
  await p.getByRole('button', { name: 'All', exact: true }).first().click(); await p.getByRole('button', { name: 'All', exact: true }).nth(1).click()
  await nav('Dataset Health'); ok(await p.getByRole('img', { name: /Health dimensions/ }).count() === 1, 'health radar chart')
  await nav('Recommendations'); ok(await p.getByRole('heading', { name: 'Recommendations', exact: true }).count() > 0, 'recommendations page')
  await nav('Exports'); ok(await p.getByText('DATA', { exact: true }).count() > 0 && await p.getByText('REPORTS', { exact: true }).count() > 0, 'exports grouped')
  await nav('Datasets'); await p.getByLabel('Search datasets').fill('zzz-none'); await p.getByText('No datasets match this search.').waitFor(); await p.getByLabel('Search datasets').fill(''); ok(true, 'dataset search')
  await nav('Exports'); const names = ['train.csv', 'test.csv', 'config.json', 'quality_report.json', 'quality_report.md', 'comparison.json', 'leakage_report.json']
  for (const f of names) { const [d] = await Promise.all([p.waitForEvent('download'), p.locator(`a.download-link:has-text("${f}")`).first().click()]); ok(fs.statSync(await d.path()).size > 0, 'download ' + f) }
  // 12-13 delete
  await p.getByRole('button', { name: /Delete export/ }).click(); await p.getByRole('button', { name: 'Delete', exact: true }).click(); await p.getByText('No prepared exports yet').waitFor(); ok(true, '12 preparation deleted')
  // responsive sweep: every page at five widths; drawer navigation at 390px
  const PAGES = ['Process Map', 'Overview', 'Investigate', 'Datasets', 'Prepare data', 'Exports', 'Feature Intelligence', 'Anomaly Analysis', 'Leakage Intelligence', 'Dataset Health', 'Recommendations']
  for (const w of [1440, 1280, 1024, 768, 390]) {
    await p.setViewportSize({ width: w, height: 900 })
    for (const pg of PAGES) {
      if (w < 1024) { await p.getByRole('button', { name: 'Open navigation' }).click(); await p.locator('aside .nav-item', { hasText: pg }).first().click() } else await nav(pg)
      await p.waitForTimeout(120)
      ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `no horizontal overflow ${w}px: ${pg}`)
    }
  }
  ok(await p.locator('aside').evaluate((e) => e.getBoundingClientRect().right <= 0 || getComputedStyle(e).visibility === 'hidden'), 'drawer closed after navigating at 390px')
  await p.getByRole('button', { name: 'Open navigation' }).click(); await p.keyboard.press('Escape'); await p.waitForTimeout(300)
  ok(await p.locator('aside').evaluate((e) => getComputedStyle(e).visibility === 'hidden'), 'Escape closes the drawer')
  await p.screenshot({ path: scratch + '/mobile.png' }); await p.setViewportSize({ width: 1440, height: 900 }); await p.screenshot({ path: scratch + '/desktop.png' })
  ok(Math.round(await p.locator('aside').evaluate((e) => e.getBoundingClientRect().width)) === 272, 'sidebar is 272px')
  await nav('Leakage Intelligence'); await p.getByRole('link', { name: 'Back to home page' }).click(); await p.getByRole('heading', { name: 'Your data has more to reveal.' }).waitFor()
  await p.getByRole('button', { name: 'Enter DataLens →' }).first().click(); await p.getByRole('heading', { name: 'Leakage Intelligence' }).first().waitFor(); ok(await p.getByLabel('Selected dataset').getByText(/rows/).count() > 0, 'L20 dataset and page preserved after Home -> Enter')
  await nav('Datasets'); await p.getByRole('button', { name: /^Remove / }).click(); await p.getByRole('button', { name: 'Delete', exact: true }).click(); await p.getByText('No datasets yet').first().waitFor(); ok(true, '13 dataset deleted')
  console.log('console errors:', JSON.stringify(errs)); ok(errs.length === 0, 'no console errors')
  await b.close(); process.exit(failed ? 1 : 0)
})().catch((e) => { console.error('FAIL exception', e.message); process.exit(1) })
