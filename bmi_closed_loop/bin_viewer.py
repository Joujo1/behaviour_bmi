#!/usr/bin/env python3
"""
Standalone .bin file viewer for BMI closed-loop recordings.

Parses a cage_N.bin file produced by FrameWriter, indexes all frames into
memory (headers + events), and serves a local web viewer for post-hoc
inspection. JPEG bytes are read from disk on demand to keep memory usage low.

Usage:
    python bin_viewer.py <path/to/cage_1.bin> [--port 7000]

Then open http://localhost:7000 in a browser.
Navigate with ← → arrow keys, the slider, or clicking the buttons.
Jump between state changes with [ ] keys or the State ‹ › buttons.
"""

import argparse
import io
import json
import struct
import sys

from flask import Flask, jsonify, render_template_string, send_file

# ── Packet format (must match udp_sender_pi.py and packet_parser.py) ──────────

HEADER_FORMAT = "<IQIIBBBBBBBBB"
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)
HEADER_FIELDS = [
    "pi_seq", "timestamp", "jpeg_size", "events_size",
    "led_center", "led_left", "led_right",
    "valve_left", "valve_right",
    "beam_left", "beam_right", "beam_center",
    "trial_state",
]

# ── Bin file indexing ─────────────────────────────────────────────────────────

def index_bin(path: str) -> tuple:
    """
    Parse headers and events for every frame.
    Returns (frames, state_change_indices, timeline).

    - frames: list of dicts with header, events, jpeg_offset, jpeg_size, current_state
    - state_change_indices: sorted list of frame indices where a state transition occurred
    - timeline: list of {frame, state, t, from} for every state transition (including
                synthetic initial-state entries derived from each transition's 'from' field)
    """
    index         = []
    current_state = None
    state_changes = []
    raw_timeline  = []   # one entry per observed transition event

    with open(path, "rb") as f:
        while True:
            length_bytes = f.read(4)
            if len(length_bytes) < 4:
                break
            packet_len   = struct.unpack("<I", length_bytes)[0]
            packet_start = f.tell()
            packet       = f.read(packet_len)

            if len(packet) < packet_len:
                break  # truncated frame (e.g. recording interrupted)

            header_vals = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
            header      = dict(zip(HEADER_FIELDS, header_vals))
            events_size = header["events_size"]
            jpeg_size   = header["jpeg_size"]

            events = []
            if events_size > 0:
                try:
                    events = json.loads(
                        packet[HEADER_SIZE : HEADER_SIZE + events_size]
                    )
                except Exception:
                    pass

            frame_idx = len(index)
            for e in events:
                if "to" in e:
                    current_state = e["to"]
                    state_changes.append(frame_idx)
                    raw_timeline.append({
                        "frame": frame_idx,
                        "state": current_state,
                        "t":     round(e.get("t", 0), 3),
                        "from":  e.get("from", "—"),
                    })

            index.append({
                "header":        header,
                "events":        events,
                "jpeg_offset":   packet_start + HEADER_SIZE + events_size,
                "jpeg_size":     jpeg_size,
                "current_state": current_state,
            })

    TERMINALS = {"__correct__", "__wrong__", "aborted"}

    # ── Retroactive fill ───────────────────────────────────────────────────────
    for i, (change_frame, tl) in enumerate(zip(state_changes, raw_timeline)):
        from_state  = tl["from"]
        block_start = state_changes[i - 1] if i > 0 else 0
        for k in range(block_start, change_frame):
            if index[k]["current_state"] is None or \
               index[k]["current_state"] in TERMINALS:
                index[k]["current_state"] = from_state

    # ── Group raw transitions into per-trial lists ─────────────────────────────
    trials_raw = []
    current_trial = []
    for tl in raw_timeline:
        current_trial.append(tl)
        if tl["state"] in TERMINALS:
            trials_raw.append(current_trial)
            current_trial = []
    if current_trial:
        trials_raw.append(current_trial)

    # ── Build rich timeline ────────────────────────────────────────────────────
    timeline    = []   # list of dicts with type∈{trial_header,state,transition,iti}
    nav_frames  = []   # all interesting frame indices for [ ] navigation

    for trial_idx, transitions in enumerate(trials_raw):
        first_transition_frame = transitions[0]["frame"]
        initial_state = transitions[0]["from"]

        # Find first frame of this trial's initial state (retroactively filled)
        trial_start_frame = first_transition_frame
        for k in range(first_transition_frame - 1, -1, -1):
            if index[k]["current_state"] == initial_state:
                trial_start_frame = k
            else:
                break

        timeline.append({"type": "trial_header", "trial_num": trial_idx + 1,
                          "frame": trial_start_frame})
        nav_frames.append(trial_start_frame)

        prev_t     = 0.0
        prev_frame = trial_start_frame

        for tl in transitions:
            state_name = tl["from"]
            duration   = round(tl["t"] - prev_t, 3)

            # State block
            timeline.append({
                "type":     "state",
                "state":    state_name,
                "frame":    prev_frame,
                "start_t":  prev_t,
                "duration": duration,
            })
            nav_frames.append(prev_frame)

            # Transition arrow
            timeline.append({
                "type":       "transition",
                "from_state": tl["from"],
                "to_state":   tl["state"],
                "t":          tl["t"],
                "frame":      tl["frame"],
            })
            nav_frames.append(tl["frame"])

            prev_t     = tl["t"]
            prev_frame = tl["frame"]

        # Terminal state (duration unknown — trial ended here)
        last = transitions[-1]
        timeline.append({
            "type":     "state",
            "state":    last["state"],
            "frame":    last["frame"],
            "start_t":  last["t"],
            "duration": None,
        })
        nav_frames.append(last["frame"])

        # ITI gap between this trial and the next
        if trial_idx < len(trials_raw) - 1:
            next_first_frame = trials_raw[trial_idx + 1][0]["frame"]
            ts_end  = index[last["frame"]]["header"]["timestamp"]
            ts_next = index[next_first_frame]["header"]["timestamp"]
            gap_s   = round((ts_next - ts_end) / 1_000_000, 1)
            timeline.append({"type": "iti", "duration_s": gap_s,
                              "frame": last["frame"]})

    nav_frames = sorted(set(nav_frames))
    return index, nav_frames, timeline


# ── Flask viewer ──────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Bin Viewer</title>
  <style>
    :root {
      font-family: Futura, Inter, system-ui, Helvetica, Arial, sans-serif;
      --bg: #fff; --fg: #000; --faint: #888; --border: #e0e0e0;
      --alive: rgb(64,202,114); --dead: rgb(205,20,20); --accent: #ffd000;
      --correct: rgb(64,202,114); --wrong: rgb(205,20,20);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--fg); display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

    header {
      display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
      padding: 8px 16px; border-bottom: 2px solid var(--fg); flex-shrink: 0;
    }
    header h1 { font-size: 0.9rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; margin-right: 4px; }
    header span.file { font-size: 0.75rem; color: var(--faint); margin-right: 8px; }

    #nav { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    #slider { width: 200px; accent-color: var(--fg); }
    #frame-label { font-size: 0.78rem; font-variant-numeric: tabular-nums; min-width: 100px; }

    .btn {
      padding: 4px 10px; font-family: inherit; font-size: 0.72rem; font-weight: 600;
      letter-spacing: 0.05em; text-transform: uppercase; cursor: pointer;
      border: 1.5px solid var(--fg); background: var(--bg); color: var(--fg);
      white-space: nowrap;
    }
    .btn:hover { background: var(--fg); color: var(--bg); }
    .btn.accent { background: var(--accent); border-color: var(--accent); }
    .btn.accent:hover { background: var(--fg); border-color: var(--fg); color: var(--bg); }

    #main { display: flex; flex: 1; overflow: hidden; }

    #image-pane {
      flex: 1; display: flex; align-items: center; justify-content: center;
      background: #111; overflow: hidden; position: relative;
    }
    #image-pane img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; }

    /* State overlay on image */
    #state-overlay {
      position: absolute; top: 10px; left: 10px;
      background: rgba(0,0,0,0.55); color: #fff;
      padding: 4px 10px; font-size: 0.8rem; font-weight: 700;
      letter-spacing: 0.06em; text-transform: uppercase;
      border-radius: 2px; pointer-events: none;
    }
    #state-overlay.correct { background: rgba(64,202,114,0.8); color: #000; }
    #state-overlay.wrong   { background: rgba(205,20,20,0.8);  color: #fff; }

    #sidebar {
      width: 420px; flex-shrink: 0; border-left: 2px solid var(--fg);
      overflow-y: auto; display: flex; flex-direction: column;
    }

    .side-section { padding: 10px 14px; border-bottom: 1px solid var(--border); }
    .side-title {
      font-size: 0.62rem; font-weight: 700; letter-spacing: 0.12em;
      text-transform: uppercase; color: var(--faint); margin-bottom: 8px;
    }

    /* State display */
    #state-name {
      font-size: 1.3rem; font-weight: 700; letter-spacing: -0.01em;
      margin-bottom: 2px;
    }
    #state-name.correct { color: var(--correct); }
    #state-name.wrong   { color: var(--wrong); }
    #state-since { font-size: 0.72rem; color: var(--faint); }

    /* Timestamp */
    #ts-val { font-size: 0.82rem; font-variant-numeric: tabular-nums; }

    /* GPIO indicators */
    #gpio-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; }
    .gpio-item {
      display: flex; flex-direction: column; align-items: center; gap: 3px;
      font-size: 0.6rem; color: var(--faint); text-align: center;
      text-transform: uppercase; letter-spacing: 0.06em;
    }
    .gpio-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--border); }
    .gpio-dot.on      { background: var(--alive); }
    .gpio-dot.beam-on { background: var(--dead); }

    /* Events */
    #events-list { display: flex; flex-direction: column; gap: 3px; }
    .event-row {
      font-size: 0.7rem; padding: 4px 7px;
      border: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center; gap: 6px;
    }
    .event-row .et { font-variant-numeric: tabular-nums; color: var(--faint); flex-shrink: 0; }
    .event-badge {
      font-size: 0.58rem; font-weight: 700; padding: 1px 5px;
      letter-spacing: 0.06em; text-transform: uppercase; flex-shrink: 0;
    }
    .badge-beam-break { background: var(--dead);    color: #fff; }
    .badge-beam-clear { background: var(--border);  color: var(--faint); }
    .badge-transition { background: var(--accent);  color: var(--fg); }
    .badge-correct    { background: var(--correct); color: #000; }
    .badge-wrong      { background: var(--wrong);   color: #fff; }

    /* Timeline */
    #timeline-list { display: flex; flex-direction: column; gap: 0; }

    .tl-trial-header {
      font-size: 0.65rem; font-weight: 700; letter-spacing: 0.12em;
      text-transform: uppercase; color: var(--fg);
      padding: 10px 14px 4px; margin-top: 6px;
      border-top: 2px solid var(--fg);
    }
    .tl-trial-header:first-child { border-top: none; margin-top: 0; }

    .tl-state-row {
      padding: 6px 14px; cursor: pointer;
      display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
      border-left: 3px solid var(--border);
      margin-left: 14px;
    }
    .tl-state-row:hover { background: var(--border); }
    .tl-state-row.active { border-left-color: var(--fg); background: #f8f8f8; }
    .tl-state-row.correct { border-left-color: var(--correct); }
    .tl-state-row.wrong   { border-left-color: var(--wrong); }
    .tl-state-name { font-size: 0.8rem; font-weight: 700; }
    .tl-state-dur  { font-size: 0.7rem; color: var(--faint); font-variant-numeric: tabular-nums; flex-shrink: 0; }

    .tl-transition-row {
      padding: 3px 14px 3px 20px; cursor: pointer;
      display: flex; align-items: center; gap: 8px;
      font-size: 0.68rem; color: var(--faint);
    }
    .tl-transition-row:hover { background: var(--border); }
    .tl-transition-row.active { color: var(--fg); font-weight: 600; }
    .tl-arrow { font-size: 0.7rem; color: var(--border); flex-shrink: 0; }
    .tl-trans-label { flex: 1; }
    .tl-trans-t { font-variant-numeric: tabular-nums; flex-shrink: 0; }

    .tl-iti-row {
      padding: 4px 14px 4px 20px;
      font-size: 0.65rem; color: var(--faint);
      font-style: italic; letter-spacing: 0.03em;
      display: flex; align-items: center; gap: 6px;
    }
    .tl-iti-line { flex: 1; height: 1px; background: var(--border); }

    .tl-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); flex-shrink: 0; }
    .tl-dot.correct { background: var(--correct); }
    .tl-dot.wrong   { background: var(--wrong); }
  </style>
</head>
<body>

<header>
  <h1>Bin Viewer</h1>
  <span class="file">{{ filename }}</span>
  <div id="nav">
    <button class="btn" onclick="seekState(-1)" title="[ key">‹ State</button>
    <button class="btn" onclick="seek(-10)">«10</button>
    <button class="btn" onclick="seek(-1)">‹</button>
    <input id="slider" type="range" min="0" max="{{ max_frame }}" value="0"
           oninput="goTo(parseInt(this.value))" />
    <button class="btn" onclick="seek(1)">›</button>
    <button class="btn" onclick="seek(10)">10»</button>
    <button class="btn" onclick="seekState(1)" title="] key">State ›</button>
    <span id="frame-label">0 / {{ max_frame }}</span>
  </div>
</header>

<div id="main">
  <div id="image-pane">
    <img id="frame-img" src="/frame/0/image" alt="frame" />
    <div id="state-overlay">—</div>
  </div>

  <div id="sidebar">

    <div class="side-section">
      <div class="side-title">Current State</div>
      <div id="state-name">—</div>
      <div id="state-since"></div>
    </div>

    <div class="side-section">
      <div class="side-title">Timestamp</div>
      <div id="ts-val">—</div>
    </div>

    <div class="side-section">
      <div class="side-title">GPIO</div>
      <div id="gpio-grid">
        <div class="gpio-item"><div class="gpio-dot" id="g-led-center"></div>LED C</div>
        <div class="gpio-item"><div class="gpio-dot" id="g-led-left"></div>LED L</div>
        <div class="gpio-item"><div class="gpio-dot" id="g-led-right"></div>LED R</div>
        <div class="gpio-item"><div class="gpio-dot" id="g-valve-left"></div>Valve L</div>
        <div class="gpio-item"><div class="gpio-dot" id="g-valve-right"></div>Valve R</div>
        <div class="gpio-item"></div>
        <div class="gpio-item"><div class="gpio-dot" id="g-beam-left"></div>Beam L</div>
        <div class="gpio-item"><div class="gpio-dot" id="g-beam-right"></div>Beam R</div>
        <div class="gpio-item"><div class="gpio-dot" id="g-beam-center"></div>Beam C</div>
      </div>
    </div>

    <div class="side-section" style="flex:0 0 auto">
      <div class="side-title">Events This Frame</div>
      <div id="events-list"><span style="font-size:0.72rem;color:var(--faint)">none</span></div>
    </div>

    <div class="side-section" style="flex:1">
      <div class="side-title">Trial Timeline</div>
      <div id="timeline-list">{{ timeline_html | safe }}</div>
    </div>

  </div>
</div>

<script>
  const MAX_FRAME     = {{ max_frame }};
  const STATE_CHANGES = {{ state_changes }};  // sorted frame indices of transitions
  let current = 0;

  // ── State helpers ────────────────────────────────────────────────────────────
  function stateClass(s) {
    if (!s || s === 'null') return '';
    if (s === '__correct__') return 'correct';
    if (s === '__wrong__')   return 'wrong';
    return '';
  }

  // ── Navigation ───────────────────────────────────────────────────────────────
  async function goTo(n) {
    n = Math.max(0, Math.min(MAX_FRAME, n));
    current = n;
    document.getElementById('slider').value = n;
    document.getElementById('frame-label').textContent = `${n} / ${MAX_FRAME}`;
    document.getElementById('frame-img').src = `/frame/${n}/image?t=${Date.now()}`;

    const res  = await fetch(`/frame/${n}/data`);
    const data = await res.json();

    // ── State ──────────────────────────────────────────────────────────────────
    const state = data.current_state;
    const cls   = stateClass(state);
    const label = state || '—';

    const nameEl = document.getElementById('state-name');
    nameEl.textContent  = label;
    nameEl.className    = cls;

    const overlay = document.getElementById('state-overlay');
    overlay.textContent = label;
    overlay.className   = cls;

    document.getElementById('state-since').textContent =
      data.state_since_frame !== null
        ? `entered at frame ${data.state_since_frame}`
        : '';

    // ── Timestamp ──────────────────────────────────────────────────────────────
    const ts_us = data.header.timestamp;
    document.getElementById('ts-val').textContent =
      `${(ts_us / 1_000_000).toFixed(3)} s (Pi clock)  ·  frame seq ${data.header.pi_seq}`;

    // ── GPIO ───────────────────────────────────────────────────────────────────
    [
      ['led-center',  data.header.led_center,   false],
      ['led-left',    data.header.led_left,      false],
      ['led-right',   data.header.led_right,     false],
      ['valve-left',  data.header.valve_left,    false],
      ['valve-right', data.header.valve_right,   false],
      ['beam-left',   data.header.beam_left,     true],
      ['beam-right',  data.header.beam_right,    true],
      ['beam-center', data.header.beam_center,   true],
    ].forEach(([id, val, isBeam]) => {
      const dot = document.getElementById(`g-${id}`);
      dot.className = 'gpio-dot' + (val ? (isBeam ? ' beam-on' : ' on') : '');
    });

    // ── Events ─────────────────────────────────────────────────────────────────
    const list = document.getElementById('events-list');
    if (!data.events.length) {
      list.innerHTML = '<span style="font-size:0.72rem;color:var(--faint)">none</span>';
    } else {
      list.innerHTML = data.events.map(e => {
        const t = e.t !== undefined ? `${e.t.toFixed(3)}s` : '';
        let label, badge;
        if (e.sensor !== undefined) {
          label = `${e.sensor} ${e.active ? 'BREAK' : 'clear'}`;
          badge = e.active
            ? `<span class="event-badge badge-beam-break">break</span>`
            : `<span class="event-badge badge-beam-clear">clear</span>`;
        } else if (e.from !== undefined) {
          label = `${e.from} → ${e.to}`;
          const bc = e.to === '__correct__' ? 'badge-correct'
                   : e.to === '__wrong__'   ? 'badge-wrong'
                   : 'badge-transition';
          badge = `<span class="event-badge ${bc}">transition</span>`;
        } else {
          label = JSON.stringify(e);
          badge = '';
        }
        return `<div class="event-row">${badge}<span style="flex:1">${label}</span><span class="et">${t}</span></div>`;
      }).join('');
    }

    // ── Timeline highlight ─────────────────────────────────────────────────────
    document.querySelectorAll('.tl-state-row, .tl-transition-row').forEach(el => {
      el.classList.toggle('active', parseInt(el.dataset.frame) === n);
    });
  }

  function seek(delta) { goTo(current + delta); }

  function seekState(dir) {
    if (!STATE_CHANGES.length) return;
    if (dir > 0) {
      const next = STATE_CHANGES.find(f => f > current);
      if (next !== undefined) goTo(next);
    } else {
      const prev = [...STATE_CHANGES].reverse().find(f => f < current);
      if (prev !== undefined) goTo(prev);
    }
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight') seek(1);
    if (e.key === 'ArrowLeft')  seek(-1);
    if (e.key === 'ArrowUp')    seek(10);
    if (e.key === 'ArrowDown')  seek(-10);
    if (e.key === ']') seekState(1);
    if (e.key === '[') seekState(-1);
  });

  goTo(0);
</script>
</body>
</html>
"""


def _state_class(s):
    if s == "__correct__": return "correct"
    if s == "__wrong__":   return "wrong"
    return ""


def create_app(bin_path: str) -> Flask:
    print(f"Indexing {bin_path} …", end=" ", flush=True)
    frames, state_changes, timeline = index_bin(bin_path)
    print(f"{len(frames)} frames, {len(state_changes)} state transitions.")

    if not frames:
        print("No frames found — is this the right file?")
        sys.exit(1)

    # Build frame → state_since_frame lookup
    state_since = {}
    for sc_frame in state_changes:
        state_since[frames[sc_frame]["current_state"]] = sc_frame
    # Walk forward to assign state_since_frame per frame
    frame_state_since = []
    current_since = None
    for i, f in enumerate(frames):
        if i in set(state_changes):
            current_since = i
        frame_state_since.append(current_since)

    # Build timeline HTML (server-side for speed)
    tl_rows = []
    for entry in timeline:
        t = entry["type"]

        if t == "trial_header":
            tl_rows.append(
                f'<div class="tl-trial-header" data-frame="{entry["frame"]}" '
                f'onclick="goTo({entry["frame"]})" style="cursor:pointer">'
                f'Trial {entry["trial_num"]}'
                f'</div>'
            )

        elif t == "state":
            cls = _state_class(entry["state"])
            if entry["duration"] is not None:
                dur = f'{entry["duration"]} s'
            else:
                dur = "—"
            tl_rows.append(
                f'<div class="tl-state-row {cls}" data-frame="{entry["frame"]}" '
                f'onclick="goTo({entry["frame"]})">'
                f'<span class="tl-state-name">{entry["state"]}</span>'
                f'<span class="tl-state-dur">duration {dur}</span>'
                f'</div>'
            )

        elif t == "transition":
            cls = _state_class(entry["to_state"])
            dot_cls = cls
            tl_rows.append(
                f'<div class="tl-transition-row" data-frame="{entry["frame"]}" '
                f'onclick="goTo({entry["frame"]})">'
                f'<div class="tl-dot {dot_cls}"></div>'
                f'<span class="tl-arrow">↓</span>'
                f'<span class="tl-trans-label">→ {entry["to_state"]}</span>'
                f'<span class="tl-trans-t">at t = {entry["t"]} s  · frame {entry["frame"]}</span>'
                f'</div>'
            )

        elif t == "iti":
            tl_rows.append(
                f'<div class="tl-iti-row">'
                f'<div class="tl-iti-line"></div>'
                f'<span>inter-trial gap  {entry["duration_s"]} s</span>'
                f'<div class="tl-iti-line"></div>'
                f'</div>'
            )

    timeline_html = "\n".join(tl_rows) if tl_rows else \
        '<span style="font-size:0.72rem;color:var(--faint)">no transitions recorded</span>'

    import os
    filename = os.path.basename(bin_path)
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(
            HTML,
            filename=filename,
            max_frame=len(frames) - 1,
            state_changes=json.dumps(sorted({e["frame"] for e in timeline})),
            timeline_html=timeline_html,
        )

    @app.get("/frame/<int:n>/image")
    def frame_image(n: int):
        if not (0 <= n < len(frames)):
            return "out of range", 404
        f = frames[n]
        with open(bin_path, "rb") as fh:
            fh.seek(f["jpeg_offset"])
            jpeg_bytes = fh.read(f["jpeg_size"])
        return send_file(io.BytesIO(jpeg_bytes), mimetype="image/jpeg")

    @app.get("/frame/<int:n>/data")
    def frame_data(n: int):
        if not (0 <= n < len(frames)):
            return "out of range", 404
        f = frames[n]
        return jsonify({
            "header":            f["header"],
            "events":            f["events"],
            "current_state":     f["current_state"],
            "state_since_frame": frame_state_since[n],
        })

    return app


def main():
    parser = argparse.ArgumentParser(description="BMI bin file viewer")
    parser.add_argument("bin_file", help="Path to cage_N.bin recording file")
    parser.add_argument("--port", type=int, default=7000, help="Local port (default 7000)")
    args = parser.parse_args()

    app = create_app(args.bin_file)
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    print(f"Viewer running at http://localhost:{args.port}  —  press Ctrl+C to quit")
    app.run(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
