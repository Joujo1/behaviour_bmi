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

def index_bin(path: str) -> list:
    """
    Parse headers and events for every frame; store JPEG byte offsets so
    the JPEG is only read from disk when a frame is requested.
    """
    index = []
    with open(path, "rb") as f:
        while True:
            length_bytes = f.read(4)
            if len(length_bytes) < 4:
                break
            packet_len   = struct.unpack("<I", length_bytes)[0]
            packet_start = f.tell()
            packet       = f.read(packet_len)

            if len(packet) < HEADER_SIZE:
                break

            header_vals  = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
            header       = dict(zip(HEADER_FIELDS, header_vals))
            events_size  = header["events_size"]
            jpeg_size    = header["jpeg_size"]

            events = []
            if events_size > 0:
                try:
                    events = json.loads(
                        packet[HEADER_SIZE : HEADER_SIZE + events_size]
                    )
                except Exception:
                    pass

            index.append({
                "header":      header,
                "events":      events,
                "jpeg_offset": packet_start + HEADER_SIZE + events_size,
                "jpeg_size":   jpeg_size,
            })

    return index


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
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--fg); display: flex; flex-direction: column; height: 100vh; }

    header {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 20px; border-bottom: 2px solid var(--fg); flex-shrink: 0;
    }
    header h1 { font-size: 0.95rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
    header span { font-size: 0.8rem; color: var(--faint); }

    #nav { display: flex; align-items: center; gap: 8px; margin-left: auto; }
    #slider { width: 260px; accent-color: var(--fg); }
    #frame-label { font-size: 0.8rem; font-variant-numeric: tabular-nums; width: 90px; text-align: right; }

    .btn {
      padding: 5px 12px; font-family: inherit; font-size: 0.75rem; font-weight: 600;
      letter-spacing: 0.05em; text-transform: uppercase; cursor: pointer;
      border: 1.5px solid var(--fg); background: var(--bg); color: var(--fg);
    }
    .btn:hover { background: var(--fg); color: var(--bg); }

    #main { display: flex; flex: 1; overflow: hidden; }

    #image-pane {
      flex: 1; display: flex; align-items: center; justify-content: center;
      background: #111; overflow: hidden;
    }
    #image-pane img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; }

    #sidebar {
      width: 320px; flex-shrink: 0; border-left: 2px solid var(--fg);
      overflow-y: auto; display: flex; flex-direction: column;
    }

    .side-section { padding: 14px 16px; border-bottom: 1px solid var(--border); }
    .side-title {
      font-size: 0.65rem; font-weight: 700; letter-spacing: 0.12em;
      text-transform: uppercase; color: var(--faint); margin-bottom: 10px;
    }

    /* GPIO indicators */
    #gpio-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
    .gpio-item {
      display: flex; flex-direction: column; align-items: center; gap: 3px;
      font-size: 0.62rem; color: var(--faint); text-align: center; text-transform: uppercase; letter-spacing: 0.06em;
    }
    .gpio-dot { width: 14px; height: 14px; border-radius: 50%; background: var(--border); }
    .gpio-dot.on { background: var(--alive); }
    .gpio-dot.beam-on { background: var(--dead); }

    /* Trial state */
    #state-val { font-size: 1.4rem; font-weight: 700; }

    /* Timestamp */
    #ts-val { font-size: 0.82rem; font-variant-numeric: tabular-nums; }

    /* Events */
    #events-list { display: flex; flex-direction: column; gap: 4px; }
    .event-row {
      font-size: 0.72rem; padding: 5px 8px;
      background: var(--bg); border: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center;
    }
    .event-row .et { font-variant-numeric: tabular-nums; color: var(--faint); }
    .event-badge {
      font-size: 0.6rem; font-weight: 700; padding: 1px 5px;
      letter-spacing: 0.06em; text-transform: uppercase;
    }
    .badge-beam-break { background: var(--dead);   color: #fff; }
    .badge-beam-clear { background: var(--border); color: var(--faint); }
    .badge-transition { background: var(--accent); color: var(--fg); }

    #no-events { font-size: 0.75rem; color: var(--faint); }
  </style>
</head>
<body>

<header>
  <h1>Bin Viewer</h1>
  <span id="file-label">{{ filename }}</span>
  <div id="nav">
    <button class="btn" onclick="seek(-10)">«10</button>
    <button class="btn" onclick="seek(-1)">‹</button>
    <input id="slider" type="range" min="0" max="{{ max_frame }}" value="0"
           oninput="goTo(parseInt(this.value))" />
    <button class="btn" onclick="seek(1)">›</button>
    <button class="btn" onclick="seek(10)">10»</button>
    <span id="frame-label">0 / {{ max_frame }}</span>
  </div>
</header>

<div id="main">
  <div id="image-pane">
    <img id="frame-img" src="/frame/0/image" alt="frame" />
  </div>

  <div id="sidebar">
    <div class="side-section">
      <div class="side-title">Timestamp</div>
      <div id="ts-val">—</div>
    </div>

    <div class="side-section">
      <div class="side-title">Trial State</div>
      <div id="state-val">—</div>
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

    <div class="side-section" style="flex:1">
      <div class="side-title">Events this frame</div>
      <div id="events-list"><span id="no-events" style="font-size:0.75rem;color:var(--faint)">none</span></div>
    </div>
  </div>
</div>

<script>
  const MAX_FRAME = {{ max_frame }};
  let current = 0;

  async function goTo(n) {
    n = Math.max(0, Math.min(MAX_FRAME, n));
    current = n;
    document.getElementById('slider').value = n;
    document.getElementById('frame-label').textContent = `${n} / ${MAX_FRAME}`;
    document.getElementById('frame-img').src = `/frame/${n}/image?t=${Date.now()}`;

    const res  = await fetch(`/frame/${n}/data`);
    const data = await res.json();

    // Timestamp
    const ts_us = data.header.timestamp;
    document.getElementById('ts-val').textContent =
      `${(ts_us / 1_000_000).toFixed(3)}s  (seq ${data.header.pi_seq})`;

    // Trial state
    document.getElementById('state-val').textContent = data.header.trial_state;

    // GPIO
    const gpio = [
      ['led-center',  data.header.led_center,   false],
      ['led-left',    data.header.led_left,      false],
      ['led-right',   data.header.led_right,     false],
      ['valve-left',  data.header.valve_left,    false],
      ['valve-right', data.header.valve_right,   false],
      ['beam-left',   data.header.beam_left,     true],
      ['beam-right',  data.header.beam_right,    true],
      ['beam-center', data.header.beam_center,   true],
    ];
    gpio.forEach(([id, val, isBeam]) => {
      const dot = document.getElementById(`g-${id}`);
      dot.className = 'gpio-dot' + (val ? (isBeam ? ' beam-on' : ' on') : '');
    });

    // Events
    const list = document.getElementById('events-list');
    const noEv = document.getElementById('no-events');
    if (!data.events.length) {
      list.innerHTML = '<span id="no-events" style="font-size:0.75rem;color:var(--faint)">none</span>';
      return;
    }
    list.innerHTML = data.events.map(e => {
      const t = e.t !== undefined ? `t=${e.t.toFixed(3)}s` : '';
      let label, badge;
      if (e.sensor !== undefined) {
        label = `${e.sensor} ${e.active ? 'BREAK' : 'clear'}`;
        badge = e.active
          ? `<span class="event-badge badge-beam-break">break</span>`
          : `<span class="event-badge badge-beam-clear">clear</span>`;
      } else if (e.from !== undefined) {
        label = `${e.from} → ${e.to}`;
        badge = `<span class="event-badge badge-transition">transition</span>`;
      } else {
        label = JSON.stringify(e);
        badge = '';
      }
      return `<div class="event-row">${badge}<span>${label}</span><span class="et">${t}</span></div>`;
    }).join('');
  }

  function seek(delta) { goTo(current + delta); }

  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight') seek(1);
    if (e.key === 'ArrowLeft')  seek(-1);
    if (e.key === 'ArrowUp')    seek(10);
    if (e.key === 'ArrowDown')  seek(-10);
  });

  goTo(0);
</script>
</body>
</html>
"""


def create_app(bin_path: str) -> Flask:
    print(f"Indexing {bin_path} …", end=" ", flush=True)
    frames = index_bin(bin_path)
    print(f"{len(frames)} frames found.")

    if not frames:
        print("No frames found — is this the right file?")
        sys.exit(1)

    import os
    filename = os.path.basename(bin_path)
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(HTML, filename=filename, max_frame=len(frames) - 1)

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
        return jsonify({"header": f["header"], "events": f["events"]})

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
