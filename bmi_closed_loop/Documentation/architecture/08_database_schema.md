# Database Schema

The PostgreSQL database is the central store for all persistent experiment state — curricula, subjects, sessions, trial results, welfare records, and video chunk metadata.

![Database schema diagram](<img/SQL db.svg>)

---

## How to read the diagram

Each box is a table. Columns are listed with their type and constraint tags (`pk` = primary key, `not null`, `unique`, `default`, etc.).

Lines between tables are **foreign-key relationships**. The endpoints use crow's foot notation:

| Endpoint symbol | Meaning |
|---|---|
| Single vertical bar `\|` | "One" side — the referenced primary key |
| Crow's foot `<` | "Many" side — the foreign key column |

Delete behaviour is shown inline on the arrow:

| Tag | Behaviour when the parent row is deleted |
|---|---|
| `[delete: restrict]` | Deletion is blocked while child rows exist |
| `[delete: set null]` | The foreign key column in child rows is set to NULL |
| `[delete: cascade]` | All child rows are deleted alongside the parent |

All relationships in this schema are **one-to-many**: one parent row may be referenced by many child rows.

---

## Table overview

| Table | Role |
|---|---|
| `training_stages` | Top-level curriculum groupings (e.g. "Habituation", "Task A") |
| `training_substages` | One row per stage step; holds the full `task_config` JSON sent to the Pi plus advancement and fallback rules. Self-references on `advance_to_substage_id` and `fallback_to_substage_id` link steps together. |
| `subjects` | One row per animal; `current_substage_id` and `substage_entered_at` track live training progress |
| `sessions` | One row per sitting; links subject ↔ cage ↔ substage snapshot; also captures body weight and water volume |
| `trial_results` | One row per trial; stores outcome, the full FSM event list (JSONB), timing fields, and correct side |
| `scoresheet_entries` | Daily welfare checks (scores A–D); auto-created when a session opens |
| `recordings` | Chunk index for `.bin` binary video files written by `frame_writer.py` |

For how a completed trial travels from the Pi into these tables see [Trial Events & Database Flow](03_trial_events_database_flow.md).  
For how to modify or extend the schema see [Adding and Changing the Database Schema](../extending/02_database_schema.md).
