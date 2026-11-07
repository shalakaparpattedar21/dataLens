# Data directory

Raw and processed data are **git-ignored**. Do not commit them: the files are large, and redistribution is governed by the dataset owner's terms.

```
data/raw/        <- place the CIC-IDS2017 CSV files here
data/processed/  <- DataLens writes cleaned/cached data here (parquet)
```

## Getting CIC-IDS2017

Official page: https://www.unb.ca/cic/datasets/ids-2017.html

1. Open the page and follow its download link (it may ask you to fill in a short form).
2. Download the **CSV flow-feature release** ("MachineLearningCVE", one CSV per capture day).
3. Unzip and copy the `.csv` files into `data/raw/`.
4. Verify:
   ```bash
   python scripts/verify_dataset.py
   ```
   This prints measured file sizes, row counts, schema consistency, NaN/inf counts and the label distribution, and writes `reports/tables/dataset_verification.json`.

Notes (confirm against the official page; these come from general knowledge, not from files checked in this repo):

- The "MachineLearningCVE" release has one file per capture period, so the **file name identifies the collection day**. This is what makes day-aware evaluation possible (Research Validity, Section 5 of the build prompt).
- A second release ("GeneratedLabelledFlows" / "TrafficLabelling") reportedly adds identifier and timestamp columns (flow ID, IPs, timestamp). Those columns are leakage risks and are useful for temporal analysis. We start with the CSV release and decide later whether to add this one.
- Some files reportedly contain non-UTF-8 characters in label names; the loader tries `utf-8`, then `cp1252`, then `latin-1` (last, because it accepts any byte) and reports which one worked.

## Citation and terms

Check the usage and citation terms on the official page before use or publication. The dataset paper, which the owners ask users to cite:

> I. Sharafaldin, A. Habibi Lashkari, A. A. Ghorbani, "Toward Generating a New Intrusion Detection Dataset and Intrusion Traffic Characterization," ICISSP 2018.
