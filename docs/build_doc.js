const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, ImageRun, AlignmentType, PageBreak,
  LevelFormat, convertInchesToTwip
} = require("docx");

const heading = (text, level = HeadingLevel.HEADING_1) =>
  new Paragraph({ text, heading: level, spacing: { before: 280, after: 140 } });

const body = (text, opts = {}) =>
  new Paragraph({
    children: [new TextRun({ text, ...opts })],
    spacing: { after: 160 },
  });

const bullet = (text) =>
  new Paragraph({
    text,
    bullet: { level: 0 },
    spacing: { after: 80 },
  });

const cell = (text, { header = false, width } = {}) =>
  new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: header ? { type: ShadingType.CLEAR, fill: "2F3B4C" } : undefined,
    children: [new Paragraph({
      children: [new TextRun({ text, bold: header, color: header ? "FFFFFF" : "222222", size: 20 })],
    })],
  });

function table(headers, rows, widths) {
  return new Table({
    width: { size: 9600, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ children: headers.map((h, i) => cell(h, { header: true, width: widths[i] })) }),
      ...rows.map(r => new TableRow({ children: r.map((c, i) => cell(c, { width: widths[i] })) })),
    ],
  });
}

function image(path, width, height) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 200 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(path), transformation: { width, height } })],
  });
}

const doc = new Document({
  creator: "sovin",
  lastModifiedBy: "sovin",
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 } } },
    children: [
      new Paragraph({
        children: [new TextRun({ text: "ASG Airlines", bold: true, size: 44 })],
        spacing: { after: 40 },
      }),
      new Paragraph({
        children: [new TextRun({ text: "Data Engineering Pipeline — Documentation", size: 30, color: "555555" })],
        spacing: { after: 40 },
      }),
      new Paragraph({
        children: [new TextRun({ text: "Prepared for NeoStats internship assignment (Round 2)", italics: true, size: 22, color: "777777" })],
        spacing: { after: 400 },
      }),

      heading("1. Overview"),
      body("This document covers the data engineering pipeline built for the ASG Airlines flight-operations case study. The pipeline is implemented locally in Python (pandas + SQLite) rather than on Azure. The brief allows this as an alternative to the cloud path, and it made more sense given the timeline — I'd rather hand over something working end-to-end than a half-finished Azure setup."),
      body("The source workbook actually contains four related tables — flights, bookings, passengers, and payments — not just the six-column flight table described in the brief. I used all four, since the passenger and booking tables carry real PII, and the payments table is what makes a revenue KPI possible."),

      heading("2. Architecture"),
      body("The pipeline follows a straightforward ingest → clean → store → visualize flow. Everything runs as a single Python script for this assignment, but each stage is a separate function so it could be lifted into Azure Data Factory / Databricks activities later without restructuring the logic."),
      body("At this volume (~1,000 rows per table), pandas in memory is the right call — it's simple to read, debug, and rerun. It wouldn't scale past that as-is: the cleaning functions would need to move to PySpark or ADF mapping data flows to parallelize the groupby/join work, and the KPI aggregations would move from pandas into the warehouse layer (Synapse/Databricks SQL) instead of being computed in memory. Keeping each stage as its own function was a deliberate choice so that swap is a rewrite of individual pieces, not a redesign of the whole flow."),
      image("images/architecture_diagram.png", 580, 240),

      heading("3. Data Flow"),
      body("Each of the four source tables goes through its own cleaning logic before being joined for the KPI layer. Passenger and booking PII is masked at the cleaning stage — before the data ever reaches the joined analytical layer or the dashboard."),
      image("images/data_flow_diagram.png", 580, 290),

      heading("4. Data Model"),
      body("Bookings sits at the centre as the fact table, since it's the natural join point between flights, passengers, and payments (one booking = one passenger, one flight, one or more payments)."),
      image("images/data_model_diagram.png", 520, 315),

      heading("5. Dataset Structure"),
      body("Field-level structure of the four source tables:"),
      table(
        ["Table", "Key Fields", "Notes"],
        [
          ["flights", "flight_id, airline, source, destination, departure_time, arrival_time, duration", "1,020 rows. Timestamps are already full datetimes — duration formula was pre-computed in the source."],
          ["bookings", "booking_id, passenger_id, flight_id, status, passport_number, seat_number", "1,000 rows. Links passengers to flights; contains passport and emergency contact PII."],
          ["passengers", "passenger_id, first_name, last_name, age, gender, email, phone, aadhaar_id, date_of_birth", "1,039 rows before de-duplication. Aadhaar ID is the most sensitive field in the dataset."],
          ["payments", "payment_id, booking_id, amount, payment_method", "1,000 rows. One-to-many with bookings — 267 bookings have more than one payment row, mostly a failed/missing-amount attempt followed by a successful one."],
        ],
        [1600, 4800, 3200]
      ),

      heading("6. Data Quality Findings & Assumptions"),
      body("I checked the actual data rather than assuming what was broken. Here's what I found, and the assumption I made to handle each:"),
      table(
        ["Issue", "Found", "Assumption / Handling"],
        [
          ["Missing / 'UNKNOWN' airline", "69 rows", "Kept the row (route and duration data is still valid), relabeled to 'Not Recorded', flagged separately so KPIs can include/exclude on demand."],
          ["Duplicate flight rows", "15 rows shared a flight_id, but only exact duplicates (same id + departure + arrival) were dropped", "A flight number reused across different days is normal airline scheduling, not a data error — only removed true row-level duplicates."],
          ["Overnight (cross-midnight) flights", "125 flights", "Source timestamps already carry the correct next-day date. Added an explicit midnight-rollover check so duration stays correct even if a future feed only sends time-of-day."],
          ["Missing booking status", "45 rows", "Filled as 'UNKNOWN' rather than dropped, since the booking and its passenger/payment links are still valid."],
          ["'INVALID' booking status", "present in data", "Treated as a real but flagged status (data-entry error), not removed — it still represents a seat/payment event."],
          ["Duplicate passenger_id", "39 rows", "Kept first occurrence only, assumed later duplicates are re-ingestion artifacts."],
          ["Missing payment amount", "78 rows", "Not imputed — money shouldn't be guessed at. Flagged and excluded from revenue sums, kept for join integrity."],
        ],
        [2400, 2400, 4800]
      ),

      heading("7. Cleaning & Transformation Logic"),
      body("Flights: ", { bold: true }),
      bullet("Standardized source/destination to uppercase IATA-style codes and built a route field (e.g. BOM-CCU)."),
      bullet("Recomputed duration in minutes from departure/arrival timestamps rather than trusting the pre-built duration column, so overnight flights are guaranteed correct."),
      bullet("Flagged anomalies as duration ≤ 0 minutes or > 360 minutes (6 hours) — unrealistic for these domestic sectors."),
      body("Bookings & Payments: ", { bold: true }),
      bullet("Normalized status text (trim + uppercase) and filled missing status as UNKNOWN rather than dropping rows."),
      bullet("Coerced payment amount to numeric, flagging non-numeric/missing values instead of imputing a guessed figure."),
      body("Passengers: ", { bold: true }),
      bullet("De-duplicated on passenger_id, keeping the first record."),
      bullet("PII fields masked before export — details in the next section."),

      heading("8. PII Masking & Access Control"),
      body("The dataset contains genuine PII: Aadhaar ID, passport number, phone, and email. These are masked before the data reaches the analytics layer or the dashboard:"),
      table(
        ["Field", "Method", "Reason"],
        [
          ["aadhaar_id", "SHA-256 hash (salted, truncated to 16 chars)", "Never needs to be human-readable; hash still works as a stable join/dedupe key."],
          ["passport_number", "SHA-256 hash (salted)", "Same as above — a legal identifier with no analytical need to be reversible."],
          ["emergency_contact_name", "SHA-256 hash (salted)", "Third-party PII (not even the passenger's own), masked by default."],
          ["email", "Partial mask (first letter + domain, e.g. v***@gmail.com)", "Keeps enough context for support use without exposing the full address."],
          ["phone / emergency_contact_phone", "Partial mask (country code + last 2 digits visible)", "Same rationale as email."],
        ],
        [2400, 3600, 3600]
      ),
      body("Access control: in a production setup, the masked fields shown above would sit in the general-access analytics schema, while a separate restricted schema (or Azure SQL row-level security / Synapse column-level security policy) would hold the unmasked originals, accessible only to a named data-protection role. Power BI itself would enforce this with row-level security tied to Azure AD groups, so only authorized users could ever query the unmasked layer — analysts building dashboards only ever see the masked version."),

      heading("9. KPIs"),
      body("Required KPIs — average flight duration, route-wise traffic, delay/anomaly detection, and airline distribution — are all computed from the cleaned flights table. I added two more:"),
      bullet("Revenue by route — joins confirmed bookings to payments to flights, since a flight-ops dashboard without a revenue view felt incomplete."),
      bullet("Cancellation rate — roughly 31% of all bookings are cancelled, which is high enough to warrant its own dashboard callout."),

      heading("10. Tools Used"),
      body("Python (pandas, hashlib, sqlite3, logging) for the pipeline; Jupyter notebook for the walkthrough; Power BI Desktop for the dashboard; matplotlib for the architecture diagrams in this document."),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("ASG_Airlines_Documentation.docx", buf);
  console.log("done");
});
