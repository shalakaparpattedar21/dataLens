# DataLens

**From Raw Data to Reliable Machine Learning.**

An experimental framework for dataset intelligence, data quality assessment and predictive modeling, applied to network intrusion detection on CIC-IDS2017.

> **Status: Phase 1 (Foundation) in progress.** The repository skeleton, configuration, environment and a dataset verifier exist. No dataset statistics, models or results exist yet; this README will only report measured results.

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

Implemented so far: configuration loading and the first slice of Ingestion (`datalens.ingestion.verify`). Everything else is planned.

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
python scripts/verify_dataset.py
```

## Repository layout

See `src/datalens/` for modules, `config/config.yaml` for settings, `PROGRESS.md` for phase status.

## Limitations

Offline benchmark results will not demonstrate real-world production intrusion detection. Evaluation-validity limits will be documented as they are investigated.
