# Dataset quality report

Sections marked **Measured** are computed from the data. Explanations and recommendations are **interpretation**.

## Dataset (measured)

- Files: 8; fingerprint `5c9706c5e8a18df7` (content hash included: True)
- Rows in files: 2,830,743; rows analysed: 283,074
- **Full dataset: False** (random sample, fraction 0.1, seed 42)
- Feature columns: 78; in-memory size: 185.73 MB
- Exact duplicate rows: 13,894; rows in label-conflicting feature groups: 71

## Class distribution (measured)

| class | rows | percent |
|---|---:|---:|
| BENIGN | 227,295 | 80.2953 |
| DoS Hulk | 23,096 | 8.159 |
| PortScan | 15,894 | 5.6148 |
| DDoS | 12,827 | 4.5313 |
| DoS GoldenEye | 1,020 | 0.3603 |
| FTP-Patator | 811 | 0.2865 |
| SSH-Patator | 604 | 0.2134 |
| DoS Slowhttptest | 566 | 0.1999 |
| DoS slowloris | 541 | 0.1911 |
| Bot | 181 | 0.0639 |
| Web Attack � Brute Force | 166 | 0.0586 |
| Web Attack � XSS | 66 | 0.0233 |
| Infiltration | 4 | 0.0014 |
| Web Attack � Sql Injection | 3 | 0.0011 |

## Findings per dimension and severity (measured counts)

No composite quality score is computed: a single number would hide trade-offs.

| dimension | high | medium | low | info |
|---|---:|---:|---:|---:|
| Class imbalance | 2 | 0 | 0 | 0 |
| Completeness | 0 | 0 | 1 | 0 |
| Consistency | 0 | 1 | 0 | 0 |
| Outliers | 0 | 0 | 0 | 1 |
| Provenance | 0 | 0 | 0 | 1 |
| Relevance | 0 | 9 | 4 | 0 |
| Uniqueness | 1 | 1 | 0 | 0 |
| Validity | 0 | 14 | 0 | 0 |

## Findings (measured value, then interpretation)

| severity | dimension | column | metric | value | explanation | recommendation |
|---|---|---|---|---|---|---|
| high | Class imbalance | - | imbalance_ratio | 75765.0 | Majority class 'BENIGN' vs minority 'Web Attack � Sql Injection'. Accuracy will be dominated by the majority class and can look high for a poor detector. | Report macro-F1, per-class recall and PR-AUC; use stratified splits; any resampling or class weighting must be applied to the training split only. |
| high | Class imbalance | - | classes_below_min_samples | {'Infiltration': 4, 'Web Attack � Sql Injection': 3} | Classes with fewer than 10 rows cannot be stratified across train/test/CV folds and give unreliable per-class metrics. | Merge with a related class, exclude from per-class claims, or evaluate separately; document it. |
| high | Uniqueness | - | label_conflict_rows | 71 | 21 feature vectors appear with more than one label (71 rows). No model can separate identical inputs, so this sets a floor on achievable error and may indicate label noise. | Inspect which classes conflict; decide (and document) whether to merge, drop, or keep them as irreducible error. |
| medium | Consistency | - | labels_with_non_ascii_chars | ['Web Attack � Brute Force', 'Web Attack � XSS', 'Web Attack � Sql Injection'] | Label names contain non-ASCII or replacement characters, usually a file-encoding artifact. | Normalize label text (decode with the right encoding or map to ASCII names). |
| medium | Relevance | Bwd Avg Bulk Rate | n_unique | 1 | Constant column: carries no information for classification. | Safe to drop (constant on all loaded data). Re-check if you are working from a sample. |
| medium | Relevance | Bwd Avg Bytes/Bulk | n_unique | 1 | Constant column: carries no information for classification. | Safe to drop (constant on all loaded data). Re-check if you are working from a sample. |
| medium | Relevance | Bwd Avg Packets/Bulk | n_unique | 1 | Constant column: carries no information for classification. | Safe to drop (constant on all loaded data). Re-check if you are working from a sample. |
| medium | Relevance | Bwd PSH Flags | n_unique | 1 | Constant column: carries no information for classification. | Safe to drop (constant on all loaded data). Re-check if you are working from a sample. |
| medium | Relevance | Bwd URG Flags | n_unique | 1 | Constant column: carries no information for classification. | Safe to drop (constant on all loaded data). Re-check if you are working from a sample. |
| medium | Relevance | Destination Port | identifier_like_name | True | Name suggests an identifier, address, port or timestamp. Such columns can act as shortcuts that reflect how the data was collected rather than attack behaviour. | Treat as a leakage risk: compare model performance with and without it before deciding. |
| medium | Relevance | Fwd Avg Bulk Rate | n_unique | 1 | Constant column: carries no information for classification. | Safe to drop (constant on all loaded data). Re-check if you are working from a sample. |
| medium | Relevance | Fwd Avg Bytes/Bulk | n_unique | 1 | Constant column: carries no information for classification. | Safe to drop (constant on all loaded data). Re-check if you are working from a sample. |
| medium | Relevance | Fwd Avg Packets/Bulk | n_unique | 1 | Constant column: carries no information for classification. | Safe to drop (constant on all loaded data). Re-check if you are working from a sample. |
| medium | Uniqueness | - | duplicate_rows_pct | 4.9083 | 13894 rows repeat an earlier row exactly (features and label). If duplicates land in both train and test, test scores are inflated. | Deduplicate BEFORE splitting, and report how many rows were removed. |
| medium | Validity | Bwd Header Length | negative_count | 2 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Flow Bytes/s | inf_count | 163 | Infinite values are not valid measurements; they typically come from a division by zero when the feature was computed (e.g. a rate over zero duration). | Convert inf to NaN, then handle like missing values (train-fit imputation). Investigate which rows are affected. |
| medium | Validity | Flow Bytes/s | negative_count | 7 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Flow Duration | negative_count | 10 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Flow IAT Max | negative_count | 10 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Flow IAT Mean | negative_count | 10 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Flow IAT Min | negative_count | 273 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Flow Packets/s | inf_count | 300 | Infinite values are not valid measurements; they typically come from a division by zero when the feature was computed (e.g. a rate over zero duration). | Convert inf to NaN, then handle like missing values (train-fit imputation). Investigate which rows are affected. |
| medium | Validity | Flow Packets/s | negative_count | 10 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Fwd Header Length | negative_count | 4 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Fwd Header Length.1 | negative_count | 4 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Fwd IAT Min | negative_count | 1 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Init_Win_bytes_backward | negative_count | 144112 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| medium | Validity | Init_Win_bytes_forward | negative_count | 100052 | Negative values in a column that should be non-negative by name. They may be legitimate sentinels (e.g. -1 meaning 'not set') or computation errors: SUSPICIOUS, not proven invalid. | Check the dataset documentation / feature definition before changing anything; do not drop these rows blindly. |
| low | Completeness | Flow Bytes/s | missing_pct | 0.0484 | 137 of 283074 values are missing. | Impute with statistics fitted on the training split only; check whether missingness differs by class before dropping rows. |
| low | Relevance | CWE Flag Count | top_value_share | 0.99988 | Near-constant column. In intrusion data a rare value can still mark an attack. | Do NOT drop automatically; judge with feature importance on training data. |
| low | Relevance | ECE Flag Count | top_value_share | 0.99977 | Near-constant column. In intrusion data a rare value can still mark an attack. | Do NOT drop automatically; judge with feature importance on training data. |
| low | Relevance | Fwd URG Flags | top_value_share | 0.99988 | Near-constant column. In intrusion data a rare value can still mark an attack. | Do NOT drop automatically; judge with feature importance on training data. |
| low | Relevance | RST Flag Count | top_value_share | 0.99977 | Near-constant column. In intrusion data a rare value can still mark an attack. | Do NOT drop automatically; judge with feature importance on training data. |
| info | Outliers | - | columns_with_iqr_outliers | 52 | IQR-flagged points are SUSPICIOUS, not wrong: in traffic data, extreme values are often legitimate bursts or the attacks themselves. | Do not remove by rule. If handling is needed, prefer robust scaling or tree models; largest counts: [('Fwd IAT Mean', 67188), ('Fwd Packet Length Max', 66914), ('Fwd IAT Max', 66625), ('Fwd IAT Total', 66544), ('Fwd Packet Length Std', 66257)] |
| info | Provenance | - | sample_fraction | 0.1 | All numbers in this report come from a random sample, not the full dataset. | Label every result with the sample fraction; rerun on the full data before concluding. |
