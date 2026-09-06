"""ASG Airlines data pipeline - cleans flight/booking/passenger/payment data, masks PII, computes KPIs.
Run: python pipeline.py
"""

import pandas as pd
import numpy as np
import hashlib
import logging
import sqlite3
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
RAW_FILE = BASE / "raw_data" / "UseCase_-_Airlines.xlsx"
OUT_DIR = BASE / "cleaned_data"
LOG_DIR = BASE / "logs"
DB_PATH = OUT_DIR / "asg_airlines.db"

logging.basicConfig(
    filename=LOG_DIR / f"pipeline_{datetime.now():%Y%m%d_%H%M%S}.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("asg_pipeline")


# ---------- 1. INGESTION ----------

def load_raw_tables(path: Path) -> dict:
    """Reads all four sheets from the source workbook into a dict of DataFrames."""
    log.info("Reading source file: %s", path)
    xl = pd.ExcelFile(path)
    tables = {name: xl.parse(name) for name in xl.sheet_names}
    for name, df in tables.items():
        log.info("Loaded '%s' -> %d rows, %d columns", name, len(df), df.shape[1])
    return tables


# ---------- 2. CLEANING ----------

def clean_flights(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    before = len(df)

    # UNKNOWN/blank airline = not recorded; flagged and kept so route/duration data isn't lost
    df["airline"] = df["airline"].replace("UNKNOWN", np.nan)
    df["airline_missing_flag"] = df["airline"].isna()
    df["airline"] = df["airline"].fillna("Not Recorded")

    # a reused flight_id is normal (same flight number flies daily); only exact duplicate rows are dropped
    exact_dupes = df.duplicated(subset=["flight_id", "departure_time", "arrival_time"]).sum()
    df = df.drop_duplicates(subset=["flight_id", "departure_time", "arrival_time"])
    log.info("flights: removed %d exact duplicate rows", exact_dupes)

    df["departure_time"] = pd.to_datetime(df["departure_time"], errors="coerce")
    df["arrival_time"] = pd.to_datetime(df["arrival_time"], errors="coerce")
    bad_dates = df["departure_time"].isna().sum() + df["arrival_time"].isna().sum()
    if bad_dates:
        log.warning("flights: %d unparseable timestamps found and dropped", bad_dates)
    df = df.dropna(subset=["departure_time", "arrival_time"])

    # arrival before departure just means it rolled past midnight; timestamps already carry the right date
    crosses_midnight = df["arrival_time"] < df["departure_time"]
    df.loc[crosses_midnight, "arrival_time"] += pd.Timedelta(days=1)

    df["duration_minutes"] = (df["arrival_time"] - df["departure_time"]).dt.total_seconds() / 60
    df["is_overnight"] = df["departure_time"].dt.normalize() != df["arrival_time"].dt.normalize()

    df["source"] = df["source"].str.strip().str.upper()
    df["destination"] = df["destination"].str.strip().str.upper()
    df["route"] = df["source"] + "-" + df["destination"]

    # flag negative/zero or >6hr durations as unrealistic for these domestic routes
    df["duration_anomaly"] = (df["duration_minutes"] <= 0) | (df["duration_minutes"] > 360)

    log.info("flights: %d -> %d rows after cleaning, %d flagged as duration anomalies",
              before, len(df), df["duration_anomaly"].sum())
    return df


def clean_bookings(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["status"] = df["status"].fillna("UNKNOWN")
    df["status"] = df["status"].str.strip().str.upper()
    # INVALID is a real but flagged status, not removed - still represents a seat/payment event
    df["status_is_invalid"] = df["status"] == "INVALID"
    dupes = df.duplicated(subset=["booking_id"]).sum()
    df = df.drop_duplicates(subset=["booking_id"])
    log.info("bookings: dropped %d duplicate booking_id rows", dupes)
    return df


def clean_passengers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    before = len(df)
    # duplicate passenger_id = re-ingestion artifact; keep first occurrence
    df = df.drop_duplicates(subset=["passenger_id"])
    df["last_name"] = df["last_name"].fillna("")
    log.info("passengers: %d -> %d rows after de-duplication", before, len(df))
    return df


def clean_payments(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    missing = df["amount"].isna().sum()
    # missing amount isn't guessed at; flagged and excluded from revenue sums instead
    df["amount_missing_flag"] = df["amount"].isna()
    log.info("payments: %d rows have missing amount, flagged rather than imputed", missing)
    return df


# ---------- 3. PII MASKING ----------

def mask_value(value: str, salt: str = "asg_airlines_2026") -> str:
    """One-way hash so masked values still work as join keys but can't be reversed."""
    if pd.isna(value):
        return value
    return hashlib.sha256(f"{salt}{value}".encode()).hexdigest()[:16]


def mask_email(email: str) -> str:
    if pd.isna(email) or "@" not in str(email):
        return email
    user, domain = email.split("@", 1)
    return f"{user[0]}***@{domain}"


def mask_phone(phone: str) -> str:
    if pd.isna(phone):
        return phone
    s = str(phone)
    return s[:-6] + "XXXX" + s[-2:] if len(s) > 6 else "XXXXXX"


def apply_pii_masking(passengers: pd.DataFrame, bookings: pd.DataFrame) -> tuple:
    passengers = passengers.copy()
    bookings = bookings.copy()

    passengers["aadhaar_id"] = passengers["aadhaar_id"].apply(mask_value)
    passengers["email"] = passengers["email"].apply(mask_email)
    passengers["phone"] = passengers["phone"].apply(mask_phone)

    bookings["passport_number"] = bookings["passport_number"].apply(mask_value)
    bookings["emergency_contact_phone"] = bookings["emergency_contact_phone"].apply(mask_phone)
    # not the passenger's own PII, but hashed anyway since there's no analytical need to expose it
    bookings["emergency_contact_name"] = bookings["emergency_contact_name"].apply(mask_value)

    log.info("PII masking applied: aadhaar_id (hashed), passport_number (hashed), "
              "email/phone (partially masked), emergency contact (hashed)")
    return passengers, bookings


# ---------- 4. KPI CALCULATIONS ----------

def build_kpis(flights: pd.DataFrame, bookings: pd.DataFrame, payments: pd.DataFrame) -> dict:
    kpis = {}

    kpis["avg_duration_by_route"] = (
        flights.groupby("route")["duration_minutes"].mean().round(1)
        .reset_index().sort_values("duration_minutes", ascending=False)
    )

    kpis["avg_duration_overall"] = flights["duration_minutes"].mean()
    kpis["avg_duration_overnight_vs_same_day"] = (
        flights.groupby("is_overnight")["duration_minutes"].mean().round(1)
    )

    kpis["route_traffic"] = (
        flights.groupby("route").size().reset_index(name="flight_count")
        .sort_values("flight_count", ascending=False)
    )

    kpis["airline_distribution"] = (
        flights.groupby("airline").size().reset_index(name="flight_count")
        .sort_values("flight_count", ascending=False)
    )

    kpis["duration_anomalies"] = flights[flights["duration_anomaly"]][
        ["flight_id", "airline", "route", "departure_time", "arrival_time", "duration_minutes"]
    ]

    # additional KPI the brief asks for - only confirmed bookings count as revenue
    confirmed = bookings[bookings["status"] == "CONFIRMED"]
    rev = confirmed.merge(payments, on="booking_id", how="left")
    rev = rev.merge(flights[["flight_id", "route"]], on="flight_id", how="left")
    kpis["revenue_by_route"] = (
        rev.groupby("route")["amount"].sum().round(2)
        .reset_index().sort_values("amount", ascending=False)
    )

    kpis["cancellation_rate"] = round(
        (bookings["status"] == "CANCELLED").mean() * 100, 2
    )

    kpis["booking_status_breakdown"] = (
        bookings["status"].value_counts().reset_index()
        .rename(columns={"index": "status", "status": "count"})
    )

    return kpis


# ---------- 5. LOAD ----------

def save_outputs(tables: dict, kpis: dict):
    OUT_DIR.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(DB_PATH)

    for name, df in tables.items():
        df.to_csv(OUT_DIR / f"{name}_clean.csv", index=False)
        df.to_sql(name, conn, if_exists="replace", index=False)
        log.info("Saved cleaned '%s' -> CSV + SQLite (%d rows)", name, len(df))

    for name, df in kpis.items():
        if isinstance(df, pd.DataFrame):
            df.to_csv(OUT_DIR / f"kpi_{name}.csv", index=False)

    conn.close()
    log.info("All outputs written to %s and %s", OUT_DIR, DB_PATH)


def run():
    log.info("=== Pipeline run started ===")
    raw = load_raw_tables(RAW_FILE)

    flights = clean_flights(raw["flights"])
    bookings = clean_bookings(raw["bookings"])
    passengers = clean_passengers(raw["passengers"])
    payments = clean_payments(raw["payments"])

    passengers, bookings = apply_pii_masking(passengers, bookings)

    kpis = build_kpis(flights, bookings, payments)

    tables = {
        "flights": flights,
        "bookings": bookings,
        "passengers": passengers,
        "payments": payments,
    }
    save_outputs(tables, kpis)

    print("Pipeline finished. Cleaned data in:", OUT_DIR)
    print(f"Rows -> flights: {len(flights)}, bookings: {len(bookings)}, "
          f"passengers: {len(passengers)}, payments: {len(payments)}")
    print(f"Cancellation rate: {kpis['cancellation_rate']}%")
    print(f"Duration anomalies flagged: {len(kpis['duration_anomalies'])}")
    log.info("=== Pipeline run finished ===")


if __name__ == "__main__":
    run()
