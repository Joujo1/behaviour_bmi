# Daily Welfare Scoresheet

The welfare scoresheet tracks daily animal health observations required by the animal ethics protocol. Access it via the **Scoresheet** link in the navigation bar.

---

## How it works

At the top of the page is a subject selector. Choose an animal from the dropdown to load its scoresheet.

A summary strip below the selector shows:
- **Reference weight** — the animal's baseline body weight, set at first session. Used to calculate percentage weight change.

The main table has one row per day a session was opened. Rows are created **automatically** when a session is opened for that subject — you do not need to add them manually.

### Columns

| Column | Description |
|---|---|
| Date | Date of the session |
| Time | Time the session was opened |
| Day | Days since the experiment started |
| Proc Nr | Procedure number (editable) |
| Procedure | Procedure details (editable) |
| Weight (g) | Body weight measured that day (editable) |
| Δ Weight | Percentage change from reference weight — calculated automatically when you enter the weight |
| A, B, C, D | Welfare score fields (0–3 each) — click the cell to change the value |
| Total | Sum of A+B+C+D — colour-coded: green (0–2), yellow (3–5), red (6+) |
| Medication | Free text (editable) |
| Remarks | Free text (editable) |

All editable cells save automatically when you click away (no save button needed).

---

## Water intake

Water intake (ml) is **not automatically calculated** at this time. The session record has a `water_ml` field that can be filled in when closing a session, but the scoresheet does not currently pull this value through to the table. It must be tracked separately until this is implemented.

---

## Exporting

Click **Export .xlsx** to download the scoresheet for the selected subject as an Excel file, formatted from the scoresheet template at the path defined by `SCORESHEET_TEMPLATE_PATH` in `config.py`.

---

## Adding entries manually

If a session was not opened for a given day but you still need a scoresheet entry (e.g. cage cleaning, health check), click **+ Add Entry**. This creates a new row for today without an associated session.
