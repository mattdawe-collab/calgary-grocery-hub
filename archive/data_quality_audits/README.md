# Data Quality Audits

Generated audit reports from `tools/data_quality_audit.py` live here.

Run from the project root:

```powershell
python tools/data_quality_audit.py
```

These reports are intentionally separate from `current_flyers.csv` and
`historical_archive.csv`: they document what the quality rules would filter,
repair, or flag without rewriting the source data.
