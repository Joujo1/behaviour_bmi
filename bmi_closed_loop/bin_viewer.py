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

from flask import Flask, abort, jsonify, render_template, request, send_file

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
    ("led_left",    "LED L",   False),
    ("led_center",  "LED C",   False),
    ("led_right",   "LED R",   False),
    ("beam_left",   "Beam L",  True),
    ("beam_center", "Beam C",  True),
    ("beam_right",  "Beam R",  True),
    ("valve_left",  "Valve L", False),
    ("valve_right", "Valve R", False),
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

    TERMINALS = {"__correct__", "__wrong__", "__end__", "aborted"}

    for i, (change_frame, tl) in enumerate(zip(state_changes, raw_timeline)):
        from_state  = tl["from"]
        block_start = state_changes[i - 1] if i > 0 else 0
        for k in range(block_start, change_frame):
            if index[k]["current_state"] is None or \
               index[k]["current_state"] in TERMINALS:
                index[k]["current_state"] = from_state

    # Group transitions into trials.
    # Two split conditions:
    #   1. Terminal state reached (__correct__, __wrong__, __end__, aborted).
    #   2. t decreases — the engine restarted (new trial_start), so the terminal
    #      event was never flushed into the stream before fsm_data_cb changed.
    trials_raw    = []
    current_trial = []
    prev_t        = None
    for tl in raw_timeline:
        if current_trial and prev_t is not None and tl["t"] < prev_t:
            trials_raw.append(current_trial)
            current_trial = []
        current_trial.append(tl)
        prev_t = tl["t"]
        if tl["state"] in TERMINALS:
            trials_raw.append(current_trial)
            current_trial = []
            prev_t = None
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
            iti_outcome = ("correct" if last["state"] in ("__correct__", "__end__")
                           else "wrong" if last["state"] == "__wrong__"
                           else "unknown")
            timeline.append({"type": "iti", "duration_s": gap_s,
                              "frame": last["frame"], "next_frame": next_first_frame,
                              "outcome": iti_outcome})

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
    t0   = frames[0]["header"]["timestamp"] if frames else 0
    t_us = [f["header"]["timestamp"] - t0 for f in frames]

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


# ── Stats ─────────────────────────────────────────────────────────────────────

def compute_stats(wf: dict) -> dict:
    """Count trial outcomes from state transition labels."""
    correct = sum(1 for sl in wf["state_labels"] if sl["state"] == "__correct__")
    wrong   = sum(1 for sl in wf["state_labels"] if sl["state"] == "__wrong__")
    decided = correct + wrong
    return {
        "n_trials":    decided,
        "correct":     correct,
        "wrong":       wrong,
        "success_pct": round(100 * correct / decided, 1) if decided else None,
    }


# ── Plotly figure builder ─────────────────────────────────────────────────────

def build_figure(frames: list, wf: dict) -> dict:
    """
    Build a Plotly-compatible figure dict for the waveform.
    shapes[0] is reserved as the cursor line (initially hidden).
    State background blocks start at shapes[1].
    """
    t_s = [t / 1_000_000 for t in wf["t_us"]]
    N   = len(GPIO_SIGNALS)

    COLORS = {"led": "#3b82f6", "valve": "#f59e0b", "beam": "#ef4444"}

    traces    = []
    tick_vals = []
    tick_text = []

    for idx, (key, label, is_beam) in enumerate(GPIO_SIGNALS):
        offset = (N - 1 - idx) * 1.8
        tick_vals.append(offset + 0.5)
        tick_text.append(label)
        color = COLORS["beam"] if is_beam else (COLORS["valve"] if "valve" in key else COLORS["led"])

        # Build explicit transition points so edges are truly vertical.
        # At each 0→1 or 1→0 transition, insert the old value at the new
        # sample's time before the new value — creates a vertical step.
        vals = wf["signals"][key]
        xs, ys = [], []
        for i, v in enumerate(vals):
            if i > 0 and v != vals[i - 1]:
                xs.append(t_s[i])
                ys.append(vals[i - 1] + offset)
            xs.append(t_s[i])
            ys.append(v + offset)

        traces.append({
            "type":       "scatter",
            "x":          xs,
            "y":          ys,
            "name":       label,
            "mode":       "lines",
            "line":       {"color": color, "width": 1.5},
            "hoverinfo":  "skip",
            "showlegend": False,
        })

    # shapes[0]: cursor line — initially hidden, updated by JS on click/nav
    shapes = [{
        "type": "line", "xref": "x", "yref": "paper",
        "x0": t_s[0], "x1": t_s[0], "y0": 0, "y1": 1,
        "line": {"color": "rgba(255,100,0,0.85)", "width": 2, "dash": "solid"},
        "visible": False,
    }]

    # State background blocks
    labels = wf["state_labels"]
    for i, sl in enumerate(labels):
        t0    = sl["t_us"] / 1_000_000
        t1    = labels[i + 1]["t_us"] / 1_000_000 if i + 1 < len(labels) else t_s[-1]
        state = sl["state"] or "—"
        color = ("rgba(64,202,114,0.18)"  if state == "__correct__" else
                 "rgba(205,20,20,0.14)"   if state == "__wrong__"   else
                 "rgba(240,240,240,0.55)")
        shapes.append({
            "type": "rect", "xref": "x", "yref": "paper",
            "x0": t0, "x1": t1, "y0": 0, "y1": 1,
            "fillcolor": color, "line": {"width": 0}, "layer": "below",
        })


    layout = {
        "shapes": shapes,
        "xaxis": {
            "title":     "Time from recording start (s)",
            "zeroline":  False,
            "showgrid":  True,
            "gridcolor": "#e8e8e8",
        },
        "yaxis": {
            "tickvals":   tick_vals,
            "ticktext":   tick_text,
            "zeroline":   False,
            "showgrid":   False,
            "range":      [-0.3, N * 1.8 - 0.2],
            "fixedrange": True,
        },
        "margin":        {"l": 80, "r": 10, "t": 10, "b": 60},
        "showlegend":    False,
        "hovermode":     "x",
        "plot_bgcolor":  "#fff",
        "paper_bgcolor": "#fff",
        "autosize":      True,
        "dragmode":      "pan",
    }

    return {"data": traces, "layout": layout}


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
    root     = os.path.realpath(root)
    tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    app      = Flask(__name__, template_folder=tmpl_dir)

    @app.get("/")
    def index():
        return render_template("bin_viewer.html")

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

    @app.get("/api/figure")
    def api_figure():
        rel = request.args.get("path", "")
        try:
            abs_path, frames, _, wf = _load(rel, root)
        except Exception as e:
            return str(e), 400
        return jsonify(build_figure(frames, wf))

    @app.get("/api/stats")
    def api_stats():
        rel = request.args.get("path", "")
        try:
            _, _, _, wf = _load(rel, root)
        except Exception as e:
            return str(e), 400
        return jsonify(compute_stats(wf))

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
