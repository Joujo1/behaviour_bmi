#!/usr/bin/env python3
"""
Standalone .bin file viewer for BMI closed-loop recordings.

Opens a browser-based file browser rooted at NAS_BASE_PATH.
Select any .bin file to view a Verilog-style waveform of all GPIO signals,
with state/substage annotations and a small JPEG preview.

Usage:
    python bin_viewer.py [--port 7000] [--root /path/to/NAS]

Then open http://localhost:7000 in a browser.
"""

import argparse
import io
import json
import os
import struct
import sys

from flask import Flask, abort, jsonify, render_template_string, request, send_file

# ── Packet format (must match udp_sender_pi.py and packet_parser.py) ─────────

HEADER_FORMAT = "<IQIIBBBBBBBBB"
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)
HEADER_FIELDS = [
    "pi_seq", "timestamp", "jpeg_size", "events_size",
    "led_center", "led_left", "led_right",
    "valve_left", "valve_right",
    "beam_left", "beam_right", "beam_center",
    "trial_state",
]

GPIO_SIGNALS = [
    ("led_center",  "LED C",    False),
    ("led_left",    "LED L",    False),
    ("led_right",   "LED R",    False),
    ("valve_left",  "Valve L",  False),
    ("valve_right", "Valve R",  False),
    ("beam_left",   "Beam L",   True),
    ("beam_right",  "Beam R",   True),
    ("beam_center", "Beam C",   True),
]

# ── Bin file indexing ─────────────────────────────────────────────────────────

def index_bin(path: str) -> tuple:
    """
    Parse headers and events for every frame.
    Returns (frames, state_changes, timeline).
    """
    index         = []
    current_state = None
    state_changes = []
    raw_timeline  = []

    with open(path, "rb") as f:
        while True:
            length_bytes = f.read(4)
            if len(length_bytes) < 4:
                break
            packet_len   = struct.unpack("<I", length_bytes)[0]
            packet_start = f.tell()
            packet       = f.read(packet_len)

            if len(packet) < packet_len:
                break

            header_vals = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
            header      = dict(zip(HEADER_FIELDS, header_vals))
            events_size = header["events_size"]
            jpeg_size   = header["jpeg_size"]

            events = []
            if events_size > 0:
                try:
                    events = json.loads(packet[HEADER_SIZE : HEADER_SIZE + events_size])
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

    for i, (change_frame, tl) in enumerate(zip(state_changes, raw_timeline)):
        from_state  = tl["from"]
        block_start = state_changes[i - 1] if i > 0 else 0
        for k in range(block_start, change_frame):
            if index[k]["current_state"] is None or \
               index[k]["current_state"] in TERMINALS:
                index[k]["current_state"] = from_state

    # Group transitions into trials
    trials_raw    = []
    current_trial = []
    for tl in raw_timeline:
        current_trial.append(tl)
        if tl["state"] in TERMINALS:
            trials_raw.append(current_trial)
            current_trial = []
    if current_trial:
        trials_raw.append(current_trial)

    # Build rich timeline
    timeline   = []
    nav_frames = []

    for trial_idx, transitions in enumerate(trials_raw):
        first_transition_frame = transitions[0]["frame"]
        initial_state = transitions[0]["from"]

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
            timeline.append({
                "type":     "state",
                "state":    tl["from"],
                "frame":    prev_frame,
                "start_t":  prev_t,
                "duration": round(tl["t"] - prev_t, 3),
            })
            nav_frames.append(prev_frame)
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

        last = transitions[-1]
        timeline.append({
            "type":     "state",
            "state":    last["state"],
            "frame":    last["frame"],
            "start_t":  last["t"],
            "duration": None,
        })
        nav_frames.append(last["frame"])

        if trial_idx < len(trials_raw) - 1:
            next_first_frame = trials_raw[trial_idx + 1][0]["frame"]
            ts_end  = index[last["frame"]]["header"]["timestamp"]
            ts_next = index[next_first_frame]["header"]["timestamp"]
            gap_s   = round((ts_next - ts_end) / 1_000_000, 1)
            timeline.append({"type": "iti", "duration_s": gap_s, "frame": last["frame"]})

    nav_frames = sorted(set(nav_frames))
    return index, nav_frames, timeline


# ── Waveform data builder ─────────────────────────────────────────────────────

def build_waveform(frames: list) -> dict:
    """
    Build compact waveform data for client-side Canvas rendering.
    Returns dict with:
      - t_us: list of timestamps (µs)
      - signals: {signal_name: [0/1 per frame]}
      - state_labels: [{t_us, state, frame}]
      - trial_markers: [{t_us, trial_num, frame}]
    """
    t_us = [f["header"]["timestamp"] for f in frames]

    signals = {}
    for key, _label, _is_beam in GPIO_SIGNALS:
        signals[key] = [f["header"][key] for f in frames]

    state_labels  = []
    trial_markers = []
    prev_state = None
    prev_trial = None

    for i, f in enumerate(frames):
        cs = f["current_state"]
        if cs != prev_state:
            state_labels.append({"t_us": t_us[i], "state": cs or "—", "frame": i})
            prev_state = cs

    return {
        "t_us":          t_us,
        "signals":       signals,
        "state_labels":  state_labels,
    }


# ── HTML template ─────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Bin Viewer</title>
  <style>
    :root {
      font-family: Futura, Inter, system-ui, Helvetica, Arial, sans-serif;
      --bg: #fff; --fg: #000; --faint: #aaa; --border: #e0e0e0;
      --accent: #ffd000;
      --correct: #40ca72; --wrong: #cd1414;
      --signal-led: #3b82f6;
      --signal-valve: #f59e0b;
      --signal-beam: #ef4444;
      --row-h: 32px;
      --label-w: 80px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--fg); display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

    /* ── Top bar ── */
    header {
      display: flex; align-items: center; gap: 10px; padding: 8px 14px;
      border-bottom: 2px solid var(--fg); flex-shrink: 0; flex-wrap: wrap;
    }
    header h1 { font-size: 0.85rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
    .file-path { font-size: 0.72rem; color: var(--faint); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .btn {
      padding: 4px 10px; font-family: inherit; font-size: 0.68rem; font-weight: 700;
      letter-spacing: 0.06em; text-transform: uppercase; cursor: pointer;
      border: 1.5px solid var(--fg); background: var(--bg); color: var(--fg); white-space: nowrap;
    }
    .btn:hover { background: var(--fg); color: var(--bg); }
    .btn.open { background: var(--accent); border-color: var(--accent); color: #000; }
    .btn.open:hover { background: var(--fg); border-color: var(--fg); color: var(--bg); }

    /* ── Layout ── */
    #app { display: flex; flex: 1; overflow: hidden; }

    /* ── File browser overlay ── */
    #browser-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,0.55);
      display: flex; align-items: center; justify-content: center;
      z-index: 100;
    }
    #browser-overlay.hidden { display: none; }
    #browser-panel {
      background: var(--bg); border: 2px solid var(--fg);
      width: 560px; max-height: 70vh; display: flex; flex-direction: column;
    }
    #browser-header {
      padding: 10px 14px; border-bottom: 1.5px solid var(--fg);
      display: flex; align-items: center; gap: 8px;
    }
    #browser-header h2 { font-size: 0.82rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; flex: 1; }
    #browser-path { font-size: 0.68rem; color: var(--faint); padding: 6px 14px; border-bottom: 1px solid var(--border); }
    #browser-list { flex: 1; overflow-y: auto; }
    .browser-item {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 14px; border-bottom: 1px solid var(--border);
      cursor: pointer; font-size: 0.78rem;
    }
    .browser-item:hover { background: #f5f5f5; }
    .browser-item .icon { font-size: 1rem; flex-shrink: 0; }
    .browser-item .name { flex: 1; }
    .browser-item .meta { font-size: 0.65rem; color: var(--faint); }
    .browser-item.up { color: var(--faint); font-style: italic; }
    .browser-item.bin-file .name { font-weight: 600; }

    /* ── Main waveform area ── */
    #waveform-wrap {
      flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative;
    }
    #waveform-empty {
      flex: 1; display: flex; align-items: center; justify-content: center;
      flex-direction: column; gap: 12px; color: var(--faint);
    }
    #waveform-empty h2 { font-size: 1.1rem; font-weight: 700; letter-spacing: 0.04em; }
    #waveform-empty p  { font-size: 0.8rem; }

    /* Signal rows */
    #signal-container {
      flex: 1; display: flex; flex-direction: column; overflow: hidden;
    }
    #state-lane {
      height: 28px; flex-shrink: 0; display: flex; overflow: hidden;
      border-bottom: 1px solid var(--border); position: relative;
    }
    #state-lane-label {
      width: var(--label-w); flex-shrink: 0; font-size: 0.58rem; font-weight: 700;
      letter-spacing: 0.08em; text-transform: uppercase; color: var(--faint);
      display: flex; align-items: center; padding-left: 6px;
      border-right: 1px solid var(--border);
    }
    #state-canvas-wrap { flex: 1; overflow: hidden; position: relative; }
    #state-canvas { display: block; height: 28px; }

    #signal-rows { flex: 1; overflow: hidden; position: relative; }
    .signal-row {
      height: var(--row-h); display: flex; border-bottom: 1px solid var(--border);
    }
    .signal-label {
      width: var(--label-w); flex-shrink: 0;
      font-size: 0.6rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
      color: var(--faint); display: flex; align-items: center; padding-left: 6px;
      border-right: 1px solid var(--border);
    }
    .signal-canvas-wrap { flex: 1; overflow: hidden; position: relative; }
    canvas.signal-canvas { display: block; }

    /* Timescale ruler */
    #timescale-wrap {
      height: 24px; flex-shrink: 0; display: flex; border-top: 1.5px solid var(--fg);
    }
    #timescale-spacer { width: var(--label-w); flex-shrink: 0; border-right: 1px solid var(--border); }
    #timescale-canvas { flex: 1; display: block; height: 24px; }

    /* Scrollbar / zoom controls */
    #scroll-controls {
      height: 30px; flex-shrink: 0; display: flex; align-items: center; gap: 8px;
      padding: 0 8px; border-top: 1px solid var(--border);
    }
    #scroll-controls label { font-size: 0.62rem; color: var(--faint); letter-spacing: 0.06em; text-transform: uppercase; }
    #hscroll { flex: 1; accent-color: var(--fg); }
    #zoom-in, #zoom-out { font-size: 0.9rem; cursor: pointer; padding: 0 4px; background: none; border: none; }

    /* Cursor line */
    #cursor-line {
      position: absolute; top: 0; bottom: 0; width: 1px;
      background: rgba(0,0,0,0.35); pointer-events: none; display: none;
    }

    /* ── Right sidebar: JPEG + info ── */
    #sidebar {
      width: 260px; flex-shrink: 0; border-left: 2px solid var(--fg);
      display: flex; flex-direction: column; overflow: hidden;
    }
    #frame-preview {
      flex-shrink: 0; background: #111; aspect-ratio: 4/3; overflow: hidden;
      display: flex; align-items: center; justify-content: center;
    }
    #frame-preview img { width: 100%; height: 100%; object-fit: contain; display: block; }
    #frame-info { flex: 1; overflow-y: auto; padding: 8px 10px; display: flex; flex-direction: column; gap: 8px; }
    .info-section { display: flex; flex-direction: column; gap: 3px; }
    .info-title {
      font-size: 0.57rem; font-weight: 700; letter-spacing: 0.12em;
      text-transform: uppercase; color: var(--faint);
    }
    .info-val { font-size: 0.78rem; font-weight: 600; }
    .info-val.correct { color: var(--correct); }
    .info-val.wrong   { color: var(--wrong); }
    .info-sub { font-size: 0.65rem; color: var(--faint); }

    #gpio-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 4px; margin-top: 2px; }
    .gpio-item { display: flex; flex-direction: column; align-items: center; gap: 2px;
                 font-size: 0.55rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); }
    .gpio-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--border); }
    .gpio-dot.on      { background: var(--signal-led); }
    .gpio-dot.valve   { background: var(--signal-valve); }
    .gpio-dot.beam-on { background: var(--signal-beam); }

    /* Trial timeline in sidebar */
    #tl-list { display: flex; flex-direction: column; }
    .tl-trial { font-size: 0.6rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
                padding: 6px 4px 2px; border-top: 1.5px solid var(--fg); margin-top: 4px; cursor: pointer; }
    .tl-trial:first-child { border-top: none; margin-top: 0; }
    .tl-state { font-size: 0.72rem; padding: 3px 4px 3px 10px; cursor: pointer;
                border-left: 2.5px solid var(--border); margin-left: 6px;
                display: flex; justify-content: space-between; }
    .tl-state:hover { background: #f5f5f5; }
    .tl-state.active { border-left-color: var(--fg); font-weight: 700; }
    .tl-state.correct { border-left-color: var(--correct); }
    .tl-state.wrong   { border-left-color: var(--wrong); }
    .tl-dur { font-size: 0.62rem; color: var(--faint); flex-shrink: 0; }
    .tl-iti { font-size: 0.62rem; color: var(--faint); padding: 2px 4px 2px 10px; font-style: italic; }
  </style>
</head>
<body>

<header>
  <h1>Bin Viewer</h1>
  <span class="file-path" id="hdr-path">No file loaded</span>
  <button class="btn open" onclick="openBrowser()">Open File</button>
</header>

<div id="app">

  <!-- File browser overlay -->
  <div id="browser-overlay">
    <div id="browser-panel">
      <div id="browser-header">
        <h2>Select Recording</h2>
        <button class="btn" onclick="closeBrowser()" id="browser-close-btn" style="display:none">Close</button>
      </div>
      <div id="browser-path">/</div>
      <div id="browser-list">Loading…</div>
    </div>
  </div>

  <!-- Waveform area -->
  <div id="waveform-wrap">
    <div id="waveform-empty">
      <h2>No file loaded</h2>
      <p>Click <strong>Open File</strong> to browse recordings.</p>
    </div>
    <div id="signal-container" style="display:none">
      <!-- State annotation lane -->
      <div id="state-lane">
        <div id="state-lane-label">State</div>
        <div id="state-canvas-wrap">
          <canvas id="state-canvas"></canvas>
        </div>
      </div>
      <!-- GPIO signal rows (injected by JS) -->
      <div id="signal-rows"></div>
      <!-- Timescale ruler -->
      <div id="timescale-wrap">
        <div id="timescale-spacer"></div>
        <canvas id="timescale-canvas"></canvas>
      </div>
      <!-- Zoom/scroll controls -->
      <div id="scroll-controls">
        <label>Scroll</label>
        <input type="range" id="hscroll" min="0" max="1000" value="0" oninput="onScroll()"/>
        <button id="zoom-out" onclick="zoom(0.5)" title="Zoom out">−</button>
        <label id="zoom-label">1×</label>
        <button id="zoom-in"  onclick="zoom(2)"   title="Zoom in">+</button>
      </div>
    </div>
  </div>

  <!-- Sidebar -->
  <div id="sidebar">
    <div id="frame-preview">
      <img id="prev-img" src="" alt="" style="display:none"/>
    </div>
    <div id="frame-info">
      <div class="info-section">
        <div class="info-title">State</div>
        <div class="info-val" id="si-state">—</div>
        <div class="info-sub" id="si-ts">—</div>
      </div>
      <div class="info-section">
        <div class="info-title">GPIO</div>
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
      <div class="info-section" style="flex:1;overflow:hidden;display:flex;flex-direction:column">
        <div class="info-title">Trial Timeline</div>
        <div id="tl-list" style="overflow-y:auto;flex:1"></div>
      </div>
    </div>
  </div>

</div>

<script>
// ── Constants injected server-side ───────────────────────────────────────────
const SIGNAL_DEFS = [
  {key:"led_center",  label:"LED C",   beam:false},
  {key:"led_left",    label:"LED L",   beam:false},
  {key:"led_right",   label:"LED R",   beam:false},
  {key:"valve_left",  label:"Valve L", beam:false},
  {key:"valve_right", label:"Valve R", beam:false},
  {key:"beam_left",   label:"Beam L",  beam:true},
  {key:"beam_right",  label:"Beam R",  beam:true},
  {key:"beam_center", label:"Beam C",  beam:true},
];
const COLOR_LED   = "#3b82f6";
const COLOR_VALVE = "#f59e0b";
const COLOR_BEAM  = "#ef4444";
const COLOR_STATE_BG  = "#fffbea";
const COLOR_STATE_TXT = "#000";

// ── State ────────────────────────────────────────────────────────────────────
let waveform   = null;   // {t_us, signals, state_labels}
let timeline   = [];     // rich timeline array from /api/timeline
let frameCount = 0;
let currentBin = null;

// View: we display frames [viewStart, viewStart+viewLen)
let viewStart = 0;
let viewLen   = 0;       // in frames; 0 = not loaded
let zoomLevel = 1;       // multiplier relative to "fit all"
let baseLen   = 0;       // frames that fit at zoom=1 (= frameCount)

let canvases  = {};      // key -> canvas element
let cursorFrame = 0;

// ── File browser ─────────────────────────────────────────────────────────────
function openBrowser() {
  document.getElementById('browser-overlay').classList.remove('hidden');
  browseTo('');
}
function closeBrowser() {
  document.getElementById('browser-overlay').classList.add('hidden');
}

async function browseTo(rel) {
  const res  = await fetch('/api/browse?path=' + encodeURIComponent(rel));
  const data = await res.json();
  document.getElementById('browser-path').textContent = data.abs_path || '/';

  const list = document.getElementById('browser-list');
  let html = '';

  if (data.parent !== null) {
    html += `<div class="browser-item up" onclick="browseTo(${JSON.stringify(data.parent)})">
               <span class="icon">↩</span><span class="name">.. (up)</span>
             </div>`;
  }

  for (const item of data.items) {
    if (item.type === 'dir') {
      html += `<div class="browser-item" onclick="browseTo(${JSON.stringify(item.rel)})">
                 <span class="icon">📁</span>
                 <span class="name">${item.name}</span>
               </div>`;
    } else {
      const mb = (item.size / 1048576).toFixed(1);
      html += `<div class="browser-item bin-file" onclick="loadBin(${JSON.stringify(item.rel)})">
                 <span class="icon">📄</span>
                 <span class="name">${item.name}</span>
                 <span class="meta">${mb} MB</span>
               </div>`;
    }
  }

  if (!html) html = '<div style="padding:14px;font-size:0.78rem;color:#aaa">No recordings found here.</div>';
  list.innerHTML = html;
}

// ── Load bin file ─────────────────────────────────────────────────────────────
async function loadBin(rel) {
  closeBrowser();
  document.getElementById('hdr-path').textContent = 'Loading…';
  document.getElementById('waveform-empty').style.display = 'flex';
  document.getElementById('signal-container').style.display = 'none';

  try {
    const [wfRes, tlRes] = await Promise.all([
      fetch('/api/waveform?path=' + encodeURIComponent(rel)),
      fetch('/api/timeline?path='  + encodeURIComponent(rel)),
    ]);

    if (!wfRes.ok) { alert('Failed to load: ' + await wfRes.text()); return; }

    waveform   = await wfRes.json();
    timeline   = await tlRes.json();
    currentBin = rel;
    frameCount = waveform.t_us.length;

    document.getElementById('hdr-path').textContent = rel;
    document.getElementById('browser-close-btn').style.display = '';
    document.getElementById('waveform-empty').style.display = 'none';
    document.getElementById('signal-container').style.display = 'flex';
    document.getElementById('signal-container').style.flexDirection = 'column';

    initCanvases();
    buildTimelineHtml();

    baseLen   = frameCount;
    zoomLevel = 1;
    viewStart = 0;
    viewLen   = baseLen;
    updateZoomLabel();
    updateScroll();
    renderAll();
    goToFrame(0);

  } catch(e) {
    alert('Error: ' + e);
  }
}

// ── Canvas setup ──────────────────────────────────────────────────────────────
function initCanvases() {
  const rows = document.getElementById('signal-rows');
  rows.innerHTML = '';
  canvases = {};

  for (const sig of SIGNAL_DEFS) {
    const row = document.createElement('div');
    row.className = 'signal-row';
    const lbl = document.createElement('div');
    lbl.className = 'signal-label';
    lbl.textContent = sig.label;
    const wrap = document.createElement('div');
    wrap.className = 'signal-canvas-wrap';
    wrap.id = 'wrap-' + sig.key;
    const cv = document.createElement('canvas');
    cv.className = 'signal-canvas';
    cv.id = 'cv-' + sig.key;
    wrap.appendChild(cv);
    row.appendChild(lbl);
    row.appendChild(wrap);
    rows.appendChild(row);
    canvases[sig.key] = cv;
  }
}

function getCanvasWidth(key) {
  const wrap = document.getElementById('wrap-' + key);
  return wrap ? wrap.clientWidth : 0;
}

function getStateCanvasWidth() {
  return document.getElementById('state-canvas-wrap').clientWidth;
}

// ── Rendering ─────────────────────────────────────────────────────────────────
function renderAll() {
  if (!waveform) return;
  for (const sig of SIGNAL_DEFS) renderSignal(sig);
  renderStateLane();
  renderTimescale();
}

function renderSignal(sig) {
  const cv = canvases[sig.key];
  if (!cv) return;
  const wrap = document.getElementById('wrap-' + sig.key);
  const W = wrap.clientWidth;
  const H = wrap.clientHeight || 32;
  cv.width  = W;
  cv.height = H;
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  const data = waveform.signals[sig.key];
  const color = sig.beam ? COLOR_BEAM : (sig.key.startsWith('valve') ? COLOR_VALVE : COLOR_LED);

  const end = Math.min(viewStart + viewLen, frameCount);
  const n   = end - viewStart;
  if (n <= 0) return;

  const yHi = H * 0.15;
  const yLo = H * 0.85;

  ctx.strokeStyle = color;
  ctx.lineWidth   = 1.5;
  ctx.beginPath();

  let firstMove = true;
  for (let i = 0; i < n; i++) {
    const fi  = viewStart + i;
    const val = data[fi];
    const x   = (i / n) * W;
    const y   = val ? yHi : yLo;

    if (firstMove) { ctx.moveTo(x, y); firstMove = false; }
    else {
      const prevVal = data[fi - 1];
      if (val !== prevVal) {
        const prevX = ((i-1) / n) * W;
        const prevY = prevVal ? yHi : yLo;
        ctx.lineTo(prevX, prevY);
        ctx.lineTo(x,     prevY);
        ctx.lineTo(x,     y);
      } else {
        ctx.lineTo(x, y);
      }
    }
  }
  ctx.stroke();
}

function renderStateLane() {
  const wrap = document.getElementById('state-canvas-wrap');
  const W = wrap.clientWidth;
  const H = 28;
  const cv = document.getElementById('state-canvas');
  cv.width  = W;
  cv.height = H;
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  const end = Math.min(viewStart + viewLen, frameCount);
  const n   = end - viewStart;
  if (n <= 0) return;

  // State blocks
  const labels = waveform.state_labels;

  for (let li = 0; li < labels.length; li++) {
    const startF = labels[li].frame;
    const endF   = li + 1 < labels.length ? labels[li+1].frame : frameCount;
    const state  = labels[li].state;

    // Clip to view
    const csF = Math.max(startF, viewStart);
    const ceF = Math.min(endF, end);
    if (csF >= ceF) continue;

    const x1 = ((csF - viewStart) / n) * W;
    const x2 = ((ceF - viewStart) / n) * W;

    let bg = '#f0f0f0';
    if (state === '__correct__') bg = 'rgba(64,202,114,0.25)';
    else if (state === '__wrong__') bg = 'rgba(205,20,20,0.2)';

    ctx.fillStyle = bg;
    ctx.fillRect(x1, 0, x2 - x1, H - 1);

    // Separator line
    ctx.strokeStyle = '#ccc';
    ctx.lineWidth   = 1;
    ctx.beginPath();
    ctx.moveTo(x1, 0); ctx.lineTo(x1, H);
    ctx.stroke();

    // Label if wide enough
    const bw = x2 - x1;
    if (bw > 20) {
      ctx.fillStyle = state === '__wrong__' ? '#c00' : state === '__correct__' ? '#1a7' : '#555';
      ctx.font      = 'bold 9px system-ui';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      const txt = state || '—';
      ctx.fillText(txt, x1 + 3, H / 2);
    }
  }

  // Trial markers
  for (const entry of timeline) {
    if (entry.type !== 'trial_header') continue;
    const fi = entry.frame;
    if (fi < viewStart || fi >= end) continue;
    const x = ((fi - viewStart) / n) * W;
    ctx.strokeStyle = '#000';
    ctx.lineWidth   = 1.5;
    ctx.beginPath();
    ctx.moveTo(x, 0); ctx.lineTo(x, H);
    ctx.stroke();
    ctx.fillStyle = '#000';
    ctx.font = 'bold 8px system-ui';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('T' + entry.trial_num, x + 2, 2);
  }

  // Cursor
  drawCursor(ctx, W, H);
}

function renderTimescale() {
  const W = document.getElementById('timescale-canvas').clientWidth;
  const H = 24;
  const cv = document.getElementById('timescale-canvas');
  cv.width  = W; cv.height = H;
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  if (!waveform || viewLen <= 0) return;
  const end   = Math.min(viewStart + viewLen, frameCount);
  const n     = end - viewStart;
  const t0_us = waveform.t_us[viewStart];
  const t1_us = waveform.t_us[end - 1];
  const dur_s = (t1_us - t0_us) / 1e6;

  // Pick a nice tick interval
  const targetTicks = Math.max(4, Math.floor(W / 80));
  let tickInterval  = niceTick(dur_s / targetTicks);

  ctx.fillStyle   = '#888';
  ctx.font        = '9px system-ui';
  ctx.textBaseline = 'top';

  const t0_s = t0_us / 1e6;
  let t = Math.ceil(t0_s / tickInterval) * tickInterval;
  while (t <= t0_s + dur_s + tickInterval) {
    const frac = (t - t0_s) / dur_s;
    const x    = frac * W;
    ctx.strokeStyle = '#ccc';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, 0); ctx.lineTo(x, 6);
    ctx.stroke();
    ctx.textAlign = 'center';
    ctx.fillText(t.toFixed(2) + 's', x, 8);
    t = Math.round((t + tickInterval) * 1e6) / 1e6;
  }
}

function niceTick(approx) {
  const e = Math.pow(10, Math.floor(Math.log10(approx)));
  const f = approx / e;
  if (f < 2) return e;
  if (f < 5) return 2 * e;
  return 5 * e;
}

function drawCursor(ctx, W, H) {
  if (cursorFrame < viewStart || cursorFrame >= viewStart + viewLen) return;
  const n = Math.min(viewStart + viewLen, frameCount) - viewStart;
  const x = ((cursorFrame - viewStart) / n) * W;
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth   = 1;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(x, 0); ctx.lineTo(x, H);
  ctx.stroke();
  ctx.setLineDash([]);
}

// ── Frame navigation ──────────────────────────────────────────────────────────
async function goToFrame(n) {
  n = Math.max(0, Math.min(frameCount - 1, n));
  cursorFrame = n;

  // Scroll view to keep cursor visible
  if (n < viewStart) {
    viewStart = Math.max(0, n - Math.floor(viewLen * 0.1));
  } else if (n >= viewStart + viewLen) {
    viewStart = Math.min(frameCount - viewLen, n - Math.floor(viewLen * 0.9));
  }
  updateScroll();
  renderAll();

  // Sidebar update
  const h = waveform.signals;
  const t_us = waveform.t_us[n];

  const state = waveform.state_labels.reduce((acc, sl) => sl.frame <= n ? sl.state : acc, '—');
  const si = document.getElementById('si-state');
  si.textContent = state;
  si.className = 'info-val' + (state === '__correct__' ? ' correct' : state === '__wrong__' ? ' wrong' : '');
  document.getElementById('si-ts').textContent =
    `t = ${(t_us/1e6).toFixed(3)} s  ·  frame ${n}`;

  // GPIO dots
  const gpioMap = [
    ['led-center',  'led_center',  false],
    ['led-left',    'led_left',    false],
    ['led-right',   'led_right',   false],
    ['valve-left',  'valve_left',  false],
    ['valve-right', 'valve_right', false],
    ['beam-left',   'beam_left',   true],
    ['beam-right',  'beam_right',  true],
    ['beam-center', 'beam_center', true],
  ];
  for (const [id, key, isBeam] of gpioMap) {
    const dot = document.getElementById('g-' + id);
    const val = h[key][n];
    if (isBeam)                dot.className = 'gpio-dot' + (val ? ' beam-on' : '');
    else if (key.startsWith('valve')) dot.className = 'gpio-dot' + (val ? ' valve' : '');
    else                       dot.className = 'gpio-dot' + (val ? ' on' : '');
  }

  // JPEG preview
  if (currentBin) {
    document.getElementById('prev-img').src =
      `/api/frame/image?path=${encodeURIComponent(currentBin)}&frame=${n}&t=${Date.now()}`;
    document.getElementById('prev-img').style.display = '';
  }

  // Timeline highlight
  highlightTimeline(n);
}

// ── Timeline HTML ─────────────────────────────────────────────────────────────
function buildTimelineHtml() {
  const tl = document.getElementById('tl-list');
  let html = '';
  for (const e of timeline) {
    if (e.type === 'trial_header') {
      html += `<div class="tl-trial" onclick="goToFrame(${e.frame})">Trial ${e.trial_num}</div>`;
    } else if (e.type === 'state') {
      const cls = e.state === '__correct__' ? ' correct' : e.state === '__wrong__' ? ' wrong' : '';
      const dur = e.duration !== null ? `${e.duration}s` : '—';
      html += `<div class="tl-state${cls}" data-frame="${e.frame}" onclick="goToFrame(${e.frame})">
        <span>${e.state}</span><span class="tl-dur">${dur}</span></div>`;
    } else if (e.type === 'iti') {
      html += `<div class="tl-iti">— ITI ${e.duration_s}s —</div>`;
    }
  }
  tl.innerHTML = html || '<span style="font-size:0.72rem;color:#aaa">No transitions</span>';
}

function highlightTimeline(frame) {
  // Find the most recent state entry at or before this frame
  let best = null;
  for (const el of document.querySelectorAll('.tl-state')) {
    const f = parseInt(el.dataset.frame);
    if (f <= frame) best = el;
  }
  document.querySelectorAll('.tl-state').forEach(el => el.classList.remove('active'));
  if (best) {
    best.classList.add('active');
    best.scrollIntoView({block: 'nearest'});
  }
}

// ── Zoom / scroll ─────────────────────────────────────────────────────────────
function zoom(factor) {
  if (!waveform) return;
  const center = viewStart + viewLen / 2;
  zoomLevel = Math.max(1, Math.min(frameCount / 4, zoomLevel * factor));
  viewLen   = Math.max(4, Math.round(baseLen / zoomLevel));
  viewStart = Math.max(0, Math.min(frameCount - viewLen, Math.round(center - viewLen / 2)));
  updateZoomLabel();
  updateScroll();
  renderAll();
}

function onScroll() {
  if (!waveform) return;
  const v = parseInt(document.getElementById('hscroll').value);
  viewStart = Math.round((v / 1000) * Math.max(0, frameCount - viewLen));
  renderAll();
}

function updateScroll() {
  const el = document.getElementById('hscroll');
  const maxStart = Math.max(1, frameCount - viewLen);
  el.value = Math.round((viewStart / maxStart) * 1000);
}

function updateZoomLabel() {
  document.getElementById('zoom-label').textContent = zoomLevel.toFixed(1) + '×';
}

// ── Canvas click → frame ──────────────────────────────────────────────────────
function canvasClickToFrame(e, wrapId) {
  const wrap = document.getElementById(wrapId);
  const rect = wrap.getBoundingClientRect();
  const frac = (e.clientX - rect.left) / rect.width;
  const end  = Math.min(viewStart + viewLen, frameCount);
  return Math.round(viewStart + frac * (end - viewStart));
}

document.addEventListener('DOMContentLoaded', () => {
  // Wire up canvas clicks for all signal wrappers
  for (const sig of SIGNAL_DEFS) {
    const wrap = document.getElementById('wrap-' + sig.key);
    if (wrap) wrap.addEventListener('click', e => goToFrame(canvasClickToFrame(e, 'wrap-' + sig.key)));
  }
  const stateWrap = document.getElementById('state-canvas-wrap');
  if (stateWrap) stateWrap.addEventListener('click', e => goToFrame(canvasClickToFrame(e, 'state-canvas-wrap')));
});

// ── Keyboard ──────────────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (!waveform) return;
  if (e.key === 'ArrowRight') goToFrame(cursorFrame + 1);
  if (e.key === 'ArrowLeft')  goToFrame(cursorFrame - 1);
  if (e.key === 'ArrowUp')    goToFrame(cursorFrame + 10);
  if (e.key === 'ArrowDown')  goToFrame(cursorFrame - 10);
  if (e.key === ']') {
    // Jump to next state transition
    const next = waveform.state_labels.find(sl => sl.frame > cursorFrame);
    if (next) goToFrame(next.frame);
  }
  if (e.key === '[') {
    const prev = [...waveform.state_labels].reverse().find(sl => sl.frame < cursorFrame);
    if (prev) goToFrame(prev.frame);
  }
  if (e.key === '+' || e.key === '=') zoom(2);
  if (e.key === '-')                   zoom(0.5);
});

// ── Resize handler ────────────────────────────────────────────────────────────
window.addEventListener('resize', () => { if (waveform) renderAll(); });

// ── Mouse wheel zoom ──────────────────────────────────────────────────────────
document.getElementById('app').addEventListener('wheel', e => {
  if (!waveform) return;
  e.preventDefault();
  zoom(e.deltaY < 0 ? 1.5 : 1/1.5);
}, {passive: false});
</script>
</body>
</html>
"""

# ── Flask app ─────────────────────────────────────────────────────────────────

_cache = {}   # rel_path -> (frames, timeline, waveform)

def _load(rel: str, root: str):
    if rel in _cache:
        return _cache[rel]
    abs_path = os.path.realpath(os.path.join(root, rel))
    if not abs_path.startswith(os.path.realpath(root)):
        raise ValueError("path outside root")
    frames, nav_frames, tl = index_bin(abs_path)
    wf = build_waveform(frames)
    _cache[rel] = (abs_path, frames, tl, wf)
    return _cache[rel]


def create_app(root: str) -> Flask:
    root = os.path.realpath(root)
    app  = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(HTML)

    @app.get("/api/browse")
    def api_browse():
        rel     = request.args.get("path", "")
        abs_dir = os.path.realpath(os.path.join(root, rel))
        if not abs_dir.startswith(root):
            abort(403)
        if not os.path.isdir(abs_dir):
            abort(404)

        items = []
        try:
            for name in sorted(os.listdir(abs_dir)):
                full = os.path.join(abs_dir, name)
                rel2 = os.path.relpath(full, root)
                if os.path.isdir(full):
                    items.append({"type": "dir", "name": name, "rel": rel2})
                elif name.endswith(".bin"):
                    items.append({"type": "file", "name": name,
                                   "rel": rel2, "size": os.path.getsize(full)})
        except PermissionError:
            pass

        parent = None
        if abs_dir != root:
            p = os.path.relpath(os.path.dirname(abs_dir), root)
            parent = "" if p == "." else p

        return jsonify({"abs_path": abs_dir, "items": items, "parent": parent})

    @app.get("/api/waveform")
    def api_waveform():
        rel = request.args.get("path", "")
        try:
            _, _, _, wf = _load(rel, root)
        except Exception as e:
            return str(e), 400
        return jsonify(wf)

    @app.get("/api/timeline")
    def api_timeline():
        rel = request.args.get("path", "")
        try:
            _, _, tl, _ = _load(rel, root)
        except Exception as e:
            return str(e), 400
        return jsonify(tl)

    @app.get("/api/frame/image")
    def api_frame_image():
        rel   = request.args.get("path", "")
        frame = request.args.get("frame", 0, type=int)
        try:
            abs_path, frames, _, _ = _load(rel, root)
        except Exception as e:
            return str(e), 400
        if not (0 <= frame < len(frames)):
            abort(404)
        f = frames[frame]
        with open(abs_path, "rb") as fh:
            fh.seek(f["jpeg_offset"])
            jpeg_bytes = fh.read(f["jpeg_size"])
        return send_file(io.BytesIO(jpeg_bytes), mimetype="image/jpeg")

    return app


def main():
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    try:
        from config import NAS_BASE_PATH
        default_root = NAS_BASE_PATH
    except ImportError:
        default_root = os.path.expanduser("~")

    parser = argparse.ArgumentParser(description="BMI bin file viewer")
    parser.add_argument("--port", type=int, default=7000, help="Local port (default 7000)")
    parser.add_argument("--root", default=default_root,
                        help=f"Root directory to browse (default: {default_root})")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        print(f"Root directory does not exist: {args.root}", file=sys.stderr)
        sys.exit(1)

    app = create_app(args.root)
    print(f"Bin Viewer  →  http://localhost:{args.port}")
    print(f"Browsing    →  {args.root}")
    app.run(host="127.0.0.1", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
