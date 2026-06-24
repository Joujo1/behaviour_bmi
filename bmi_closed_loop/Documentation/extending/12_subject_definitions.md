# Adding and Changing Subject Definitions

A subject is a database row in the `subjects` table. Its fields define the animal's identity, welfare tracking, and training assignment. The API and UI for managing subjects live in [ui/endpoints/subjects.py](../../ui/endpoints/subjects.py) and [ui/templates/subjects.html](../../ui/templates/subjects.html).

---

## Current subject fields

| Column | Type | Description |
|---|---|---|
| `id` | serial | Auto-assigned primary key |
| `code` | text (unique) | Short identifier used everywhere (e.g. `"R001"`) |
| `sex` | CHAR(1) | `"M"` or `"F"` |
| `dob` | date | Date of birth |
| `weight_g` | NUMERIC(6,1) | Body weight in grams |
| `reference_weight_g` | NUMERIC | Baseline weight for water restriction calculations |
| `water_restricted` | bool | Whether the animal is on water restriction |
| `species` | text | e.g. `"rat"` |
| `strain` | text | e.g. `"Wistar"` |
| `experiment_nr` | text | Lab experiment tracking number |
| `notes` | text | Free-text notes |
| `enrolled_at` | TIMESTAMPTZ | When the subject was created |
| `current_substage_id` | int (FK) | Which training substage the animal is on |
| `substage_entered_at` | timestamp | When the current substage was assigned |
| `side_bias_alg` | text | Active bias algorithm key (see [04_bias_algorithms.md](04_bias_algorithms.md)) |

---

## The API endpoints

| Method | Path | What it does |
|---|---|---|
| `GET` | `/subjects` | List all subjects with substage info |
| `POST` | `/subjects` | Create a new subject |
| `GET` | `/subjects/<id>` | Get one subject plus recent trial stats |
| `PATCH` | `/subjects/<id>` | Update any writable field |
| `PATCH` | `/subjects/<id>/substage` | Move the subject to a different substage (live-switches if a session is open) |
| `DELETE` | `/subjects/<id>` | Delete a subject (guarded — fails if sessions reference it) |

---

## How to add a new subject field

### Step 1 — Add the column to the database

Create a migration that adds the column to `subjects`. See [02_database_schema.md](02_database_schema.md) for how to write and run migrations.

```sql
ALTER TABLE subjects ADD COLUMN my_field text;
```

### Step 2 — Expose the field in `subjects.py`

**In `list_subjects()`**: add the column to the `SELECT` query so it appears in the list response.

**In `create_subject()`**: add the field to the `INSERT` columns list and to the values tuple:

```python
cur.execute("""
    INSERT INTO subjects (code, ..., my_field)
    VALUES (%s, ..., %s)
    RETURNING id
""", (code, ..., body.get("my_field")))
```

**In `update_subject()`**: add the field name to the `allowed` set so clients can patch it:

```python
allowed = {
    "code", "sex", "dob", ..., "my_field",
}
```

### Step 3 — Add the field to the UI

Open [ui/templates/subjects.html](../../ui/templates/subjects.html) and add an input field for creating and editing subjects. The subjects page fetches `GET /subjects` to render the table and uses `PATCH /subjects/<id>` for inline edits — match the field name to the column name you used in step 2.

---

## Substage live-switching

When `PATCH /subjects/<id>/substage` is called while an active session is open, it calls `runner.switch_substage()` on the relevant `CageRunner`. This updates the substage in the database and changes the task config used for the next trial without interrupting the current one.
