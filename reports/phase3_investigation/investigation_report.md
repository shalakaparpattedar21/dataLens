# Dataset investigation (measured from raw files)

Files (8): Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv, Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv, Friday-WorkingHours-Morning.pcap_ISCX.csv, Monday-WorkingHours.pcap_ISCX.csv, Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv, Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv, Tuesday-WorkingHours.pcap_ISCX.csv, Wednesday-workingHours.pcap_ISCX.csv

Hardware: {'platform': 'Windows-10-10.0.26200-SP0', 'python': '3.11.9', 'machine': 'AMD64', 'cpu_count': 8, 'total_ram_gb': 13.89, 'available_ram_gb': 1.88}

## C. Label encoding

- Distinct raw label byte-strings: 15
- Kinds found: {'ascii': 19, 'utf8_replacement_char_in_file': 3}
- **Original files contain a UTF-8 replacement character: True**
- **Class counts split by inconsistent encoding: False**
- Interpretation hint: If kind is 'cp1252_dash_byte', the file stores a single byte 0x96; the replacement character only appears when a reader decodes it wrongly (the loader decodes cp1252). If kind is 'utf8_replacement_char_in_file', the character is baked into the file.

| file | bytes_hex | kind | rows | loader_style_decoding |
|---|---|---|---|---|
| Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv | 5765622041747461636b20efbfbd20427275746520466f726365 | utf8_replacement_char_in_file | 1507 | Web Attack � Brute Force |
| Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv | 5765622041747461636b20efbfbd20585353 | utf8_replacement_char_in_file | 652 | Web Attack � XSS |
| Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv | 5765622041747461636b20efbfbd2053716c20496e6a656374696f6e | utf8_replacement_char_in_file | 21 | Web Attack � Sql Injection |

Label counts after artifact removal:

| index | rows |
|---|---|
| BENIGN | 2273097 |
| DoS Hulk | 231073 |
| PortScan | 158930 |
| DDoS | 128027 |
| DoS GoldenEye | 10293 |
| FTP-Patator | 7938 |
| SSH-Patator | 5897 |
| DoS slowloris | 5796 |
| DoS Slowhttptest | 5499 |
| Bot | 1966 |
| Web Attack Brute Force | 1507 |
| Web Attack XSS | 652 |
| Infiltration | 36 |
| Web Attack Sql Injection | 21 |
| Heartbleed | 11 |

## A. Missing values

- Total NaN cells: 1,358  (rows scanned: 2,830,743)
- Cells that were non-numeric text and failed to parse: 0

| index | nan_cells |
|---|---|
| Flow Bytes/s | 1358 |

## B. Infinite values

- +inf cells: 4,376   -inf cells: 0

| index | pos_inf | neg_inf | inf_with_flow_duration_0 |
|---|---|---|---|
| Flow Bytes/s | 1509 | 0 | 1509 |
| Flow Packets/s | 2867 | 0 | 2867 |

`inf_with_flow_duration_0` counts inf cells in rows whose Flow Duration is 0: evidence for/against the division-by-zero explanation.

### By file

| index | rows | nan_cells | inf_cells |
|---|---|---|---|
| Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv | 225745 | 4 | 64 |
| Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv | 286467 | 15 | 727 |
| Friday-WorkingHours-Morning.pcap_ISCX.csv | 191033 | 28 | 216 |
| Monday-WorkingHours.pcap_ISCX.csv | 529918 | 64 | 810 |
| Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv | 288602 | 18 | 396 |
| Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv | 170366 | 20 | 250 |
| Tuesday-WorkingHours.pcap_ISCX.csv | 445909 | 201 | 327 |
| Wednesday-workingHours.pcap_ISCX.csv | 692703 | 1008 | 1586 |

### By class (share of that class's rows)

| index | rows | rows_with_inf | rows_with_nan | pct_rows_with_inf | pct_rows_with_nan |
|---|---|---|---|---|---|
| BENIGN | 2273097.0 | 1777.0 | 409.0 | 0.0782 | 0.018 |
| DoS Hulk | 231073.0 | 949.0 | 949.0 | 0.4107 | 0.4107 |
| PortScan | 158930.0 | 126.0 | 0.0 | 0.0793 | 0.0 |
| DDoS | 128027.0 | 2.0 | 0.0 | 0.0016 | 0.0 |
| DoS GoldenEye | 10293.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| FTP-Patator | 7938.0 | 3.0 | 0.0 | 0.0378 | 0.0 |
| SSH-Patator | 5897.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| DoS slowloris | 5796.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| DoS Slowhttptest | 5499.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Bot | 1966.0 | 10.0 | 0.0 | 0.5086 | 0.0 |
| Web Attack Brute Force | 1507.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack XSS | 652.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Infiltration | 36.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack Sql Injection | 21.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Heartbleed | 11.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## D. Duplicates

- rows: 2,830,743
- exact_duplicate_rows_global: 308,381
- exact_duplicate_rows_within_file: 256,479
- exact_duplicates_only_across_files: 51,902
- label_conflict_groups: 698
- label_conflict_rows: 7,020
- vectors_spanning_multiple_files: 34,208
- rows_in_spanning_vectors: 146,363
- spanning_vectors_with_label_disagreement: 664

### Per class (what `drop_exact` would remove)

| index | rows | exact_duplicate_rows | rows_in_label_conflicts | rows_in_cross_file_vectors | pct_removed_by_drop_exact |
|---|---|---|---|---|---|
| BENIGN | 2273097.0 | 176613.0 | 736.0 | 140499.0 | 7.77 |
| DoS Hulk | 231073.0 | 58224.0 | 5224.0 | 4804.0 | 25.197 |
| PortScan | 158930.0 | 68111.0 | 1053.0 | 1053.0 | 42.856 |
| DDoS | 128027.0 | 11.0 | 6.0 | 6.0 | 0.009 |
| DoS GoldenEye | 10293.0 | 7.0 | 0.0 | 0.0 | 0.068 |
| FTP-Patator | 7938.0 | 2005.0 | 0.0 | 0.0 | 25.258 |
| SSH-Patator | 5897.0 | 2678.0 | 0.0 | 0.0 | 45.413 |
| DoS slowloris | 5796.0 | 411.0 | 1.0 | 1.0 | 7.091 |
| DoS Slowhttptest | 5499.0 | 271.0 | 0.0 | 0.0 | 4.928 |
| Bot | 1966.0 | 13.0 | 0.0 | 0.0 | 0.661 |
| Web Attack Brute Force | 1507.0 | 37.0 | 0.0 | 0.0 | 2.455 |
| Web Attack XSS | 652.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Infiltration | 36.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Web Attack Sql Injection | 21.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Heartbleed | 11.0 | 0.0 | 0.0 | 0.0 | 0.0 |

