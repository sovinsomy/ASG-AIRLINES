# ASG Airlines — Flight Operations Data Pipeline

End-to-end data engineering case study: ingest raw flight/booking/passenger/payment data, clean it, mask PII, compute operational KPIs, and feed a Power BI dashboard.

Built locally in Python (pandas + SQLite) rather than on Azure — the brief explicitly allows this as an alternative, and I chose it for a faster, fully-working turnaround.

## What's actually in the data

The source workbook has four related tables, not just the single flight table the brief describes: `flights`, `bookings`, `passengers`, `payments`. Passengers and bookings carry real PII (Aadhaar ID, passport number, phone, email), which is why PII masking is a core part of this pipeline, not an afterthought.

## Repo structure

```
raw_data/          source Excel file (untouched)
scripts/
  pipeline.py      the full ETL pipeline — run this
cleaned_data/       output: cleaned CSVs, one consolidated Excel, SQLite db, KPI CSVs
notebooks/
  asg_airlines_pipeline.ipynb   annotated walkthrough of the same logic, with real output
docs/
  ASG_Airlines_Documentation.docx   architecture, data model, assumptions, cleaning logic
  PowerBI_Build_Guide.md            step-by-step dashboard build + DAX measures
  images/                           diagrams used in the docx
logs/               pipeline run logs (timestamped)
```

## Running it

```bash
cd scripts
python pipeline.py
```

Reads `../raw_data/UseCase_-_Airlines.xlsx`, writes cleaned CSVs + a SQLite DB to `../cleaned_data/`, and logs the run to `../logs/`.

## Data quality issues found and handled

| Issue | Count | Handling |
|---|---|---|
| Missing/UNKNOWN airline | 69 | Relabeled, flagged, kept |
| Duplicate flight rows | 15 | Only exact duplicates dropped |
| Overnight (cross-midnight) flights | 125 | Duration recalculated from full timestamps |
| Missing booking status | 45 | Filled as UNKNOWN, flagged |
| Duplicate passenger IDs | 39 | Kept first occurrence |
| Missing payment amount | 78 | Flagged, excluded from revenue sums |

Full reasoning for each is in the Word doc under Section 6.

## PII masking

- `aadhaar_id`, `passport_number`, `emergency_contact_name` → SHA-256 hashed
- `email`, `phone` → partially masked (e.g. `v***@gmail.com`, `+91-6896XXXX90`)

## KPIs

Average flight duration, route-wise traffic, duration anomalies, airline distribution (all required by the brief) — plus revenue-by-route and cancellation rate, added because a flight-ops dashboard felt incomplete without a revenue/reliability signal.

## Dashboard

Built in Power BI Desktop from the cleaned CSVs — see `docs/PowerBI_Build_Guide.md` for the exact build steps and DAX measures. `.pbix` file added separately once built locally (Power BI Desktop isn't available in this build environment).
