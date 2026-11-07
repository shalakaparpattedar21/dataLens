# DataLens progress log

| Phase | Status | Notes |
|---|---|---|
| 1. Foundation | **Open** | Code/env done. Real CIC-IDS2017 not yet obtained: no real-data verification or exploration yet |
| 2. Data Intelligence | **Code complete, unit-tested; NOT validated on real data** | Ingestion loader, profiler, quality assessor, report writer, CLI |
| 3. Data Preparation | Not started | |
| 4. Applied Machine Learning | Not started | |
| 5. Research and Optimization | Not started | |
| 6. Finalization | Not started | |

## Phase 2 verification (what was actually run)

- `pytest`: 47 passed (synthetic fixtures with planted, known problems).
- Scalability sanity check on a **synthetic** 511,500 x 78 dataset (5 files, ~145 MB each) on a 2-core / 7.8 GB sandbox: load 4.5 s, profile 7.4 s, peak RSS about 800 MB. This is NOT a CIC-IDS2017 result; real data may behave differently.
- The stress test found a real bug (latin-1 tried before cp1252 created a second spelling of one label). Fixed and covered by a regression test.

## Still needed before Phase 1/2 can be called complete

- [ ] Put CIC-IDS2017 CSVs in `data/raw/`
- [ ] `python scripts/verify_dataset.py`, then `python scripts/profile_dataset.py`
- [ ] Review the real findings in `reports/tables/quality_report.md`; fix any rule that misfires on real data
- [ ] Notebooks 01/02 (exploration and quality) using real outputs

## Known issues / limits

- Dev sandbox cannot reach the dataset hosts, so the dataset must be downloaded on your machine.
- Quality thresholds in `config.yaml` are starting points, not tuned on real data.
- Negative-value and identifier checks are name-based heuristics; they flag, they do not decide.
- Row-hash duplicate detection has a negligible but non-zero collision probability.
- Multi-file loading holds the (optionally sampled) dataset in memory; very large full loads need enough RAM (measure first with `--sample-fraction`).
