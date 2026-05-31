# Database Schema

All persistent data lives in a PostgreSQL database. The full schema is defined in `bmi_closed_loop/db/schema.sql`.

The diagram below shows every table, their columns, and how they relate to each other.

![Database schema diagram](<img/SQL db.svg>)

---

## How to read the diagram

Each box is a table. Columns are listed with their type and tags (`pk` = primary key, `not null`, `unique`, `default`, etc.).

Lines between tables are foreign-key relationships — one table's column points to a row in another table. The endpoints use crow's foot notation:

| Symbol | Meaning |
|---|---|
| Single bar `\|` | "One" side — the primary key being referenced |
| Crow's foot `<` | "Many" side — the foreign key column |

Delete behaviour is labelled on the line:

| Label | What happens when the parent row is deleted |
|---|---|
| `[delete: restrict]` | The deletion is blocked — you must remove child rows first |
| `[delete: set null]` | The child row's foreign key column is set to NULL |
| `[delete: cascade]` | All child rows are deleted along with the parent |

---

## What each table stores

**`training_stages`** — the top-level groups of your curriculum, like "Habituation" or "Task A". Mostly just a name and a sort order.

**`training_substages`** — one row per step within a stage. This is the most important table for the trial logic: the `task_config` column holds the full JSON trial definition that gets sent to the Pi. It also holds the advancement criteria (how well the animal needs to do to move on) and fallback criteria (how poorly it needs to do to go back). The `advance_to_substage_id` and `fallback_to_substage_id` columns point to other rows in the same table, creating the curriculum graph.

**`subjects`** — one row per animal. `current_substage_id` and `substage_entered_at` track where the animal currently is in the curriculum.

**`sessions`** — one row per sitting at the rig. Links an animal to a cage and records body weight, water volume, and timestamps.

**`trial_results`** — one row per trial. Stores the outcome, the full event list as JSON (`events`), timing fields, and which side was correct. This is the main table for analysis.

**`scoresheet_entries`** — daily welfare checks with scores A through D. One is created automatically when a session opens.

**`recordings`** — a chunk index for the `.bin` binary video files saved on the NAS. Every 1000 frames, one row is added with the frame range, timestamps, and byte offset. This lets you seek to any point in the video without reading the whole file.

---

## Where each table is written and read

| Table | Written by | Read by |
|---|---|---|
| `training_stages` / `training_substages` | `ui/endpoints/curriculum.py` | `cage_runner.py`, `advancement.py`, export queries |
| `subjects` | `ui/endpoints/subjects.py`, `advancement.py` | `cage_runner.py`, export queries, dashboard |
| `sessions` | `ui/endpoints/session.py` | Export queries, dashboard |
| `trial_results` | `ui/event_handler.py` | `advancement.py`, export queries, bias algorithms, metrics |
| `scoresheet_entries` | `ui/endpoints/scoresheet.py` | Scoresheet page, export |
| `recordings` | `acquisition/frame_writer.py` | `bin_viewer.py`, video seek tools |

---

For how to add columns or new tables, see [Adding and Changing the Database Schema](../extending/02_database_schema.md).  
For how trial results get written here, see [Trial Events & Database Flow](03_trial_events_database_flow.md).
