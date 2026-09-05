# Power BI Dashboard — Build Guide

You have Power BI Desktop, so this should take about 20-25 minutes. The data is already clean — you're just importing and wiring up relationships/measures, not fixing anything.

## 1. Import data

`Get Data → Text/CSV` and import these four files from `cleaned_data/`:
- `flights_clean.csv`
- `bookings_clean.csv`
- `passengers_clean.csv`
- `payments_clean.csv`

## 2. Set relationships (Model view)

- `flights[flight_id]` → `bookings[flight_id]` (one-to-many)
- `passengers[passenger_id]` → `bookings[passenger_id]` (one-to-many)
- `bookings[booking_id]` → `payments[booking_id]` (one-to-one)

## 3. Fix data types

- `flights[departure_time]`, `flights[arrival_time]` → Date/Time
- `flights[duration_minutes]` → Decimal Number
- `payments[amount]` → Decimal Number
- `bookings[booking_date]` → Date/Time

## 4. Paste these DAX measures (New Measure, on the `flights` or `bookings` table as noted)

```dax
Avg Flight Duration (min) = AVERAGE(flights[duration_minutes])

Total Flights = COUNTROWS(flights)

Overnight Flights = CALCULATE(COUNTROWS(flights), flights[is_overnight] = TRUE)

Duration Anomalies = CALCULATE(COUNTROWS(flights), flights[duration_anomaly] = TRUE)

Total Bookings = COUNTROWS(bookings)

Cancellation Rate % =
DIVIDE(
    CALCULATE(COUNTROWS(bookings), bookings[status] = "CANCELLED"),
    COUNTROWS(bookings)
) * 100

Confirmed Revenue =
CALCULATE(
    SUM(payments[amount]),
    bookings[status] = "CONFIRMED"
)

Missing Payment Count = CALCULATE(COUNTROWS(payments), payments[amount_missing_flag] = TRUE)
```

## 5. Suggested pages (matches the brief's requested structure)

**Page 1 — Duration Analysis**
- KPI cards: `Avg Flight Duration (min)`, `Overnight Flights`, `Duration Anomalies`
- Bar chart: average duration by `route`
- Column chart: same-day vs overnight avg duration (`is_overnight` on axis)

**Page 2 — Route Performance**
- Map or bar chart: flight count by `route`
- Table: top 10 busiest routes
- Bar chart: `Confirmed Revenue` by `route`

**Page 3 — Airline Trends**
- Donut/pie: flight count by `airline`
- Card: count of `airline_missing_flag` = TRUE (data quality callout)

**Page 4 — Delay / Anomaly & Booking Health**
- Table: flights where `duration_anomaly` = TRUE
- KPI card: `Cancellation Rate %`
- Column chart: booking count by `status`
- Card: `Missing Payment Count`

## 6. Filters/slicers to add on every page

`source`, `destination`, `airline`, and a date slicer on `departure_time`.

## 7. A note on PII

`passengers` and `bookings` in the CSVs are already masked (hashed Aadhaar/passport, partially masked email/phone) — don't pull in the original workbook by mistake for the dashboard, only the `cleaned_data/` files.
