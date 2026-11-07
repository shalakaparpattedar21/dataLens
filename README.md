# DataLens

**From Raw Data to Reliable Machine Learning.**

An experimental framework for dataset intelligence, data quality assessment and predictive modeling, applied to network intrusion detection on CIC-IDS2017.

> **Status: Phases 1-2 code written; not yet run on real CIC-IDS2017.** Ingestion, profiling and quality assessment are implemented and unit-tested on synthetic data. No dataset statistics, models or results exist yet; this README will only report measured results. See `PROGRESS.md`.

## Motivation

Real datasets are rarely ML-ready: missing values, duplicates, invalid values, imbalance and redundant features all distort model results. Intrusion-detection benchmarks add temporal dependence and collection artifacts that can inflate scores. DataLens makes those issues visible and measures how data-preparation choices change model behavior.

## Research questions

1. What data quality problems exist in the selected network traffic dataset?
2. How do preprocessing and feature engineering decisions affect model performance?
3. How do different classifiers perform on the same prepared dataset?
4. How does class imbalance affect accuracy, precision, recall and F1?
5. Can systematic hyperparameter optimization improve performance?
6. Which features contribute most to predictions?
7. How do computational requirements differ between models?

## Planned architecture

```mermaid
flowchart LR
    A[Raw CSVs] --> B[Ingestion]
    B --> C[Profiling]
    C --> D[Quality assessment]
    D --> E[Preprocessing<br/>fit on train only]
    E --> F[Feature engineering]
    F --> G[Models]
    G --> H[Evaluation]
    H --> I[Experiments<br/>log + tuning]
    I --> J[Reports]
    C --> J
    D --> J
```

Implemented so far: configuration, ingestion (`verify`, `loader`), profiling, quality assessment and the quality report writer. Preprocessing onward is planned.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
pytest
```

## Dataset

CIC-IDS2017 is **not** included. See [`data/README.md`](data/README.md) for download steps and citation/terms notes, then:

```bash
python scripts/verify_dataset.py                          # file-level checks
python scripts/profile_dataset.py                         # profile + quality report (full data)
python scripts/profile_dataset.py --sample-fraction 0.1   # development sample (recorded in outputs)
```

Outputs go to `reports/tables/` (`quality_report.md`, `quality_findings.csv`, `profile_columns.csv`, `profile_summary.json`). Every output records whether it came from the full dataset or a sample.

## Repository layout

See `src/datalens/` for modules, `config/config.yaml` for settings, `PROGRESS.md` for phase status.

## Limitations

Offline benchmark results will not demonstrate real-world production intrusion detection. Evaluation-validity limits will be documented as they are investigated.
