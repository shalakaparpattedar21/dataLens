# DataLens progress log

| Phase | Status | Notes |
|---|---|---|
| 1. Foundation | Data present; prior verification reports present | Eight raw CSVs and the existing verification report are present locally; see the attached handoff for previously reported verification results |
| 2. Data Intelligence | Code complete; prior reports present | Ingestion loader, profiler, quality assessor, report writer, CLI; local report files are preserved |
| 3. Data Preparation | Phase 3 code integrated; local validation pending | Integration is complete; tests and real-data preparation have not been run in this environment |
| 4. Applied Machine Learning | Not started | |
| 5. Research and Optimization | Not started | |
| 6. Finalization | Not started | |

## Phase 2 verification (what was actually run)

- `pytest`: 47 passed (synthetic fixtures with planted, known problems).
- Scalability sanity check on a **synthetic** 511,500 x 78 dataset (5 files, ~145 MB each) on a 2-core / 7.8 GB sandbox: load 4.5 s, profile 7.4 s, peak RSS about 800 MB. This is NOT a CIC-IDS2017 result; real data may behave differently.
- The stress test found a real bug (latin-1 tried before cp1252 created a second spelling of one label). Fixed and covered by a regression test.

## Phase 1/2 follow-up from the earlier checkpoint

- [x] CIC-IDS2017 CSVs are present in `data/raw/`
- [x] Existing verification and profiling reports are present; rerun only when requested
- [ ] Review the existing real-data findings in `reports/tables/quality_report.md`; fix any rule that misfires on real data
- [ ] Notebooks 01/02 (exploration and quality) using real outputs

## Known issues / limits

- Dev sandbox cannot reach the dataset hosts, so the dataset must be downloaded on your machine.
- Quality thresholds in `config.yaml` are starting points, not tuned on real data.
- Negative-value and identifier checks are name-based heuristics; they flag, they do not decide.
- Row-hash duplicate detection has a negligible but non-zero collision probability.
- Multi-file loading holds the (optionally sampled) dataset in memory; very large full loads need enough RAM (measure first with `--sample-fraction`).
## Phase 3 integration status

The Phase 3 implementation from `DataLens_phase3.zip` has been selectively integrated. The ZIP's Git metadata was not copied. Existing Phase 1/2 modules, raw CSVs, reports, and the virtual environment were preserved. The Phase 3 tests have **not** been run in the local environment, and no Phase 3 dataset operation has been run here.

New functionality includes streaming dataset investigation, byte-level label decoding inspection, duplicate/conflicting-label analysis, random and day-aware splits, train-fitted imputation/encoding/scaling, feature analysis and optional selection, imbalance reporting/resampling helpers, and preparation/run reports. Model training remains unimplemented.

### Outstanding research-validity concerns

- The default exact-duplicate policy runs globally before splitting. This can alter day-aware holdout cohorts when duplicate feature vectors span files; the implementation reports cross-file vectors. The policy is unchanged by this integration.
- Identifier-like and unusually predictive features are flagged for review, but are not automatically excluded. Inspect candidate target leakage before modeling.
- Full preparation loads the dataset and creates working train/test frames. The resource estimate covers one feature-matrix copy and is not a memory guard. Start with an explicit 10% sample after tests and inspect measured memory before a full run.

### Validation provenance

The ZIP's development notes report 162 tests in two external environments and synthetic end-to-end/memory checks. Those are archive-reported results only; they were not rerun locally and are not CIC-IDS2017 results. No claim of local test success or real-data Phase 3 validation is made here.
