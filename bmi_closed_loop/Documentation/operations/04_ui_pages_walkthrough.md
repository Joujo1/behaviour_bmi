# UI Pages Walkthrough

The web UI has five pages, all accessible from the navigation bar at the top of every page.

---

## Dashboard (`/`)

The main operational view. One card per cage, laid out in a grid.

**Header bar**
- **Researcher** text field — enter your name before opening sessions. Stored in the session record.
- **↻ Subjects** button — reloads the subject list in all cage dropdowns (auto-refreshes every 10 s but useful after adding a new subject).

**Cage card — top row**
- Cage number and title.
- Live **fps** counter, **q** (internal queue depth), and **net** drop count (UDP packets lost on the network, shown in red).
- Fan controls: **−** and **🌀** buttons step the fan PWM duty cycle up and down. The current duty is shown between them. A small dot to the right turns green when the fan is running.
- **💡** strip light toggle with a dot showing state.

**Cage card — camera area**
- Live video feed (MJPEG or H264 WebSocket stream).
- "No feed" label when no stream is active.
- "Camera Lost" overlay with elapsed time when frames stop arriving.
- Advancement popup when the rat meets criteria to advance or fall back — shows the target substage and a Dismiss button.

**Cage card — session controls**
- Subject dropdown — select which animal is in this cage.
- **Open** / **Close** session buttons. Open becomes active once a subject is selected.
- **Stream ▶/■** — start/stop the camera and UDP stream.
- **Rec ▶/■** — start/stop recording frames to the NAS.
- **Trial ▶** / **Trial ■** — start or stop the trial runner.
- Status dots: large dot (acquisition alive/stopped/dead), recording dot, trial dot.
- NTP sync dot (updates every 5 s).

**Global bar (bottom)**
Bulk controls that apply the same action to all cages simultaneously: Open All Sessions, Close All Sessions, Start/Stop All Trials, Streams, Fans, LEDs.

**DEV strip (top)**
Buttons to truncate individual database tables. Only use in development.

---

## Curriculum (`/curriculum-page`)

The trial definition and training progression editor.

**Left sidebar**
- Input box at top to create a new **training stage** (a named group of substages, e.g. "Habituation", "Click Task").
- Below that, the **stage tree** lists all stages with their substages numbered. Click a substage to open it in the editor. Hover a substage to reveal the delete button.
- The sidebar also shows a small **curriculum graph** — a Graphviz-rendered directed graph of all substages and their advancement/fallback connections.

**Right panel — substage editor**
Opens when you click a substage.

*Meta bar* — substage label, substage number, and the ITI settings (base ITI for correct outcomes, fail ITI for wrong/abort). Click **Save meta**.

*Advancement criteria bar* — two rows: advance (move forward) and fallback (drop back). Each row has a criterion type selector (populated from registered `CRITERIA_HANDLERS`), window and threshold inputs, and a target substage selector. Click **Save criteria**.

*FSM graph* — live Graphviz render of the trial state machine as you build it. Updates on every change.

*Builder toolbar* — set the initial state and side mode. **+ State** adds a new state card. **Save trial definition** persists the whole trial JSON.

*State cards* — one card per FSM state with:
- State name and duration.
- Entry and exit action lists (type selector + parameters per action).
- Transition list (trigger, optional target sensor, hold time, next state).

Terminal state cards (**\_\_correct\_\_** and **\_\_wrong\_\_**) are shown separately at the bottom and cannot be deleted.

---

## Subjects (`/subjects-page`)

Animal registry and management.

**Create form (top)**
Fields: code, sex, date of birth, weight, water restriction status, starting substage, species, strain, experiment number, notes. Click **+ Add Subject**.

**Subjects table**
One row per animal. Each row shows the current substage, days enrolled, bias algorithm, water restriction badge, and three action buttons:
- **Move substage** — opens a modal to manually reassign the animal to any substage. If a session is currently open for this animal, the change takes effect immediately without interrupting the running trial.
- **Edit** — opens a modal to change any field, including the active bias algorithm and the reference weight (under the Advanced section).
- **✕** — deletes the subject. Blocked if any sessions reference the animal.

---

## Metrics (`/metrics-page`)

Data visualisation and session log.

**Animal summary table** — one row per subject: total trials, last-N percent correct (window configurable with the n= input), current substage, sessions count, last session date.

**Learning curve** — Plotly line chart of percent correct per session number. Filter by subject or show all on the same plot. Click **↻ Refresh** to reload.

**Side bias** — bar chart showing left/right trial count and correct/wrong breakdown for a selected subject.

**Session log** — filterable table of sessions: cage, subject, date, duration, weight, water, trial counts, percent correct. Click any row to expand a per-trial detail table for that session.

**Substage dwell** — table showing how many sessions and trials a subject spent at each substage, with percent correct per substage.

---

## Scoresheet (`/scoresheet-page`)

See [03_welfare_scoresheet.md](03_welfare_scoresheet.md) for a full description.

---

## Export (`/export-page`)

Download filtered datasets as CSV. Select an export type from the dropdown (trials, events, click timing, sessions, performance, etc.), apply filters (subject, date range, substage), and click **Download**. Files stream directly to the browser without loading into server memory. See [extending/03_export_options.md](../extending/03_export_options.md) for how to add new export types.
