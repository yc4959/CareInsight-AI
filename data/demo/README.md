# Packaged Synthea demo data

These four compressed CSV files are a column subset of the public **1K Sample Synthetic Patient Records, CSV** under **Previous Versions (2019–2021)** on the [Synthea downloads page](https://synthetichealth.github.io/downloads.html). They contain synthetic records, not real patients.

`scripts/build_demo_data.py` selects only the columns listed in `manifest.json`, preserves all source rows and their order, and writes gzip CSVs. The manifest records row counts and SHA-256 hashes of both the original local CSVs and packaged files. Patient and encounter IDs remain because the analysis joins records across tables; names, addresses, and other unused fields are excluded.

The packaged files are used when the original `data/csv/` download is absent. They can also be selected locally with `CAREINSIGHT_USE_DEMO_DATA=1` to check that results match the original files. This is a portable demonstration subset, not a new or independently representative dataset.

Synthea's [download page](https://synthetichealth.github.io/downloads.html) describes the generated data as available for unrestricted secondary use and asks users to cite: Walonoski J, et al. *Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health care record.* JAMIA. 2018;25(3):230–238. [doi:10.1093/jamia/ocx079](https://doi.org/10.1093/jamia/ocx079).
