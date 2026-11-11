export const api = '/api'

export async function call(path, options = {}) {
  let res
  try { res = await fetch(api + path, options) } catch {
    throw new Error('Cannot reach the DataLens backend. Start it with: python -m uvicorn datalens.api:app --port 8000')
  }
  const data = res.headers.get('content-type')?.includes('json') ? await res.json().catch(() => null) : null
  if (!res.ok) {
    const detail = data?.detail
    const text = Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : detail
    const err = new Error(text || `Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}
export const post = (path, body) => call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })

export const FILES = [
  ['train.csv', 'Transformed training rows'], ['test.csv', 'Transformed test rows'],
  ['config.json', 'Exact recipe, seed and fitted parameters'], ['quality_report.json', 'Machine-readable findings and validation'],
  ['quality_report.md', 'Human-readable quality report'], ['comparison.json', 'Before / after figures'],
]
export const EXTRA_FILE = ['leakage_report.json', 'Leakage findings for this run']
export const running = (j) => !!j && ['queued', 'running'].includes(j.status)
export const infinite = (p) => (p?.positive_infinity_cells || 0) + (p?.negative_infinity_cells || 0)
export const when = (v) => { const d = new Date(v); return isNaN(d) ? '' : d.toLocaleString() }
export const mb = (b) => (Number(b || 0) / 1048576).toFixed(1)
