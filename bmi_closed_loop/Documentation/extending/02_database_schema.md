# Adding and Changing the Database Schema

The database schema lives in one file: [bmi_closed_loop/db/schema.sql](../../db/schema.sql).

Everything is plain SQL. The schema file is written so that you can safely re-run it against an existing database — it will add any missing pieces without destroying data.

---

## How to apply the schema

**First time (empty database):**

```bash
psql postgresql://bmi:yaniklab@localhost/bmi_closed_loop -f db/schema.sql
```
The PW is the same as the PC's.

**After adding something to the schema file (existing database, keep data):**

Run the exact same command again. All `CREATE TABLE` and `CREATE INDEX` statements use `IF NOT EXISTS`, and new columns are added with `ADD COLUMN IF NOT EXISTS`, so nothing breaks if the table already exists.

```bash
psql postgresql://bmi:yaniklab@localhost/bmi_closed_loop -f db/schema.sql
```

**Full reset (wipe everything and start fresh):**

```bash
psql <your-connection-string> -v RESET=1 -f db/schema.sql
```

The `-v RESET=1` flag triggers a block at the top of `schema.sql` (lines 12–19) that drops all tables before recreating them. **This deletes all data.**

---

## How to add a new column to an existing table

Say you want to add a column `notes` (plain text) to `trial_results`.

**1. Open `db/schema.sql` and find the `ALTER TABLE` section for that table.**

For `trial_results` this is around lines 160–163. You'll see lines like:

```sql
ALTER TABLE trial_results ADD COLUMN IF NOT EXISTS correct_side TEXT ...;
ALTER TABLE trial_results ADD COLUMN IF NOT EXISTS trial_start_us BIGINT;
```

**2. Add your new line in the same style:**

```sql
ALTER TABLE trial_results ADD COLUMN IF NOT EXISTS notes TEXT;
```

The `IF NOT EXISTS` part means if the column is already there (because you ran the schema before), PostgreSQL will skip it silently instead of throwing an error.

**3. Re-run the schema file against your database:**

```bash
psql postgresql://bmi:yaniklab@localhost/bmi_closed_loop -f db/schema.sql
```

The new column now exists. Any old rows will have `NULL` in that column unless you set a default.

---

## How to add a new table

Add a `CREATE TABLE IF NOT EXISTS` block anywhere after the existing tables in `schema.sql`. Follow the same style as the other tables:

```sql
CREATE TABLE IF NOT EXISTS my_new_table (
    id      SERIAL PRIMARY KEY,
    cage_id INT    NOT NULL,
    value   NUMERIC,
    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Then add an index if you'll be filtering on a column often:

```sql
CREATE INDEX IF NOT EXISTS idx_my_new_table_cage ON my_new_table (cage_id);
```

Re-run the schema file and you're done.

---

## Where each table is used in the code

| Table | Written by | Read by |
|---|---|---|
| `training_stages` / `training_substages` | UI curriculum editor | `cage_runner.py`, `advancement.py`, export queries |
| `subjects` | UI subjects page | `cage_runner.py`, `advancement.py`, export queries |
| `sessions` | `ui/endpoints/session.py` | Export queries, dashboard |
| `trial_results` | `event_handler.py` | `advancement.py`, export queries, bias algorithms |
| `scoresheet_entries` | `ui/endpoints/scoresheet.py` | Scoresheet page, export |
| `recordings` | `acquisition/frame_writer.py` | Bin-file seeking tools |

---

## Adding a CHECK constraint

If you add a column that should only accept certain values (like `outcome` only allowing `'correct'`, `'wrong'`, `'aborted'`), you can add a check constraint:

```sql
ALTER TABLE my_table ADD COLUMN IF NOT EXISTS status TEXT
    CHECK (status IN ('active', 'inactive'));
```

If you later need to allow a new value, you have to drop the old constraint and add a new one. Look at how it's done for `subjects.side_bias_alg` near line 77 of `schema.sql` — it drops the old constraint with a `DO $$ ... END$$` block and the column just becomes a free-text field instead.

---

## A note on the JSONB columns

Several columns store JSON (`task_config`, `events`, `advance_criteria`, etc.). These hold structured data directly in the database without needing extra tables. You can query inside them in PostgreSQL using `->` and `->>` operators, or `jsonb_array_elements()` to expand an array into rows. The export queries in `ui/endpoints/export.py` have several working examples of this (lines 190–263).
