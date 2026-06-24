# A First Session

This walks through everything from a cold start to a running trial, assuming the hardware is already wired and the Pis are set up.

---

## Before you start — hardware checklist

- All cage Pis are powered on and the network cables are plugged in.
- The ItsyBitsy MCU is connected to the PCB and powered.
- Beam sensors, LEDs, valves, speakers, and the camera are connected to the PCB.
- The PC (sentinel) is on.

---

## Step 1 — Start the PC application

Double-click the terminal shortcut on the desktop. A terminal opens and starts the Flask application. It will print a startup message once the UDP receivers and cage connections are live.

Open **Google Chrome** and navigate to:

```
http://localhost:5000
```

or from another machine on the network:

```
http://<PC IP>:5000
```

You should see the dashboard with one cage card per cage.

---

## Step 2 — Add a training curriculum

Before you can run trials you need at least one training stage with a substage and a trial definition. Go to the **Curriculum** page (link in the top navigation bar).

**Left sidebar — stage tree**

The sidebar shows all training stages. Each stage can contain multiple substages. To create a stage, type a name in the input box at the top of the sidebar and click **+**.

Once a stage exists, hover over it and click **+ sub** to add a substage inside it. A new substage appears with a default number.

**Right panel — substage editor**

Click any substage in the tree to open its editor. The editor has three sections:

1. **Meta bar** — set the substage label, substage number, and base/fail ITI (inter-trial interval in seconds). Click **Save meta** to persist.

2. **Advancement criteria bar** — two rows, one for advancement (move to a higher substage) and one for fallback (drop to a lower substage). For each row, pick the criterion type (e.g. `pct_correct`), set the window and threshold, and choose the target substage to move to. Click **Save criteria** when done.

3. **Trial builder** — the main area. At the top toolbar, set the initial state and side mode (`random`, `fixed_left`, `fixed_right`). Click **+ State** to add a FSM state. Each state card has:
   - A **duration** field (how long the state lasts before timeout).
   - An **entry actions** section — click **+ action** and choose the type (`led_on`, `valve_open`, `play_clicks`, etc.) and fill in the parameters.
   - An **exit actions** section — same as entry.
   - A **transitions** section with the possible next states on beam break or timeout.
   
   A live FSM graph above the builder updates as you add states so you can verify the trial logic visually. Click **Save trial definition** when the trial is ready.

---

## Step 3 — Add a subject

Go to the **Subjects** page (link in the top navigation bar).

The top section has a create form with fields:

| Field | What to enter |
|---|---|
| Code | Short animal ID (e.g. `R001`) |
| Sex | M or F |
| DOB | Date of birth (DD/MM/YYYY) |
| Weight | Body weight in grams |
| Water restricted | Yes or No |
| Substage | Starting substage from the curriculum |
| Species | e.g. `Rattus norvegicus` |
| Strain | e.g. `Wistar` |
| Experiment Nr | Lab tracking number |
| Notes | Optional free text |

Click **+ Add Subject**. The subject appears in the table below. You can click **Edit** at any time to change fields, **Move substage** to manually reassign the animal to a different substage, or **✕** to delete.

Each row in the table also shows the current substage, whether the animal is water-restricted, and which bias algorithm is active (set via the Edit modal).

---

## Step 4 — Assign the curriculum to the subject

This is done at subject creation time via the **Substage** dropdown. If the subject already exists, use **Move substage** to assign the correct starting substage. The substage determines which trial definition runs and which advancement criteria apply.

---

## Step 5 — Return to the dashboard and open a session

Go back to the **Dashboard** (home icon or BMI Closed Loop in the header).

In the **researcher** field at the top of the page, type your name or initials. This is stored in the session record.

Each cage card has:
- A **subject dropdown** — select the animal assigned to this cage.
- An **Open** button — opens a session for this cage. Once a subject is selected, the button becomes active.
- After opening, the card gains **Stream ▶**, **Rec ▶**, and **Trial ▶** buttons.

Click **Open** for the relevant cage. The system:
1. Creates a session record in the database.
2. Creates a welfare scoresheet entry for today.
3. If this is the animal's first session ever, prompts you to enter a reference weight (used to track percentage weight change over the experiment).

---

## Step 6 — Start the stream and run trials

Click **Stream ▶** to start the camera. The cage card video feed becomes live.

Click **Rec ▶** to begin recording frames to the NAS (optional — trials run without recording).

Click **Trial ▶** to dispatch the first trial. The trial runs automatically, the FSM advances through states, and when it ends the system waits for the ITI and then starts the next trial automatically.

The cage card shows:
- Live fps and network drop counts in the header.
- Coloured status dots: the large dot (top right of the card) shows acquisition status (alive/stopped/dead); the fan and strip dots show peripheral state; the sync dot shows NTP sync status.
- A trial status dot below the session buttons (green = running, grey = idle).
- An advancement popup if the rat meets the criteria to advance or fall back.

Click **Trial ■** to stop trials. Click **Close** to close the session.

---

## Global controls

At the bottom of the dashboard, the **ALL CAGES** bar has bulk buttons — **Open All Sessions**, **Start All Trials**, etc. — that perform the same action on every cage simultaneously. These are useful when running a full rack session.
