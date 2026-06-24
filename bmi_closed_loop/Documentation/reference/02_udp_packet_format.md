# UDP Packet Format

Each camera frame is transmitted from the Pi to the PC as a single UDP datagram. The packet has three sections: a fixed-size binary header, a variable-length JSON events blob, and the raw H264 frame bytes.

Source: [RPi_main/udp_sender_pi.py](../../RPi_main/udp_sender_pi.py) (packing) and [acquisition/packet_parser.py](../../acquisition/packet_parser.py) (parsing).

---

## Wire layout

```
Offset   Size   Type     Field
------   ----   ----     -----
0        4      uint32   frame_counter      — Pi's per-stream sequence number
4        8      uint64   timestamp_us       — CLOCK_MONOTONIC microseconds (Pi clock)
12       4      uint32   jpeg_size          — byte count of the H264 frame section
16       4      uint32   events_size        — byte count of the events JSON section
20       1      uint8    led_center         — 0 or 1
21       1      uint8    led_left           — 0 or 1
22       1      uint8    led_right          — 0 or 1
23       1      uint8    valve_left         — 0 or 1
24       1      uint8    valve_right        — 0 or 1
25       1      uint8    beam_left          — 0 or 1 (1 = beam broken)
26       1      uint8    beam_right         — 0 or 1
27       1      uint8    beam_center        — 0 or 1
28       1      uint8    trial_state        — reserved, always 0
29       N      bytes    events JSON        — UTF-8 encoded JSON array (N = events_size)
29+N     M      bytes    H264 frame         — Annex-B H264 bytes (M = jpeg_size)
```

Total header size: **29 bytes** (`struct` format `<IQIIBBBBBBBBB`).

All multi-byte integers are **little-endian**.

---

## Field notes

**`frame_counter`** — increments by 1 for every packet sent. Gaps in this sequence on the PC side indicate dropped packets (network loss or oversized frame silently discarded by the sender).

**`timestamp_us`** — `CLOCK_MONOTONIC` microseconds captured by the Pi's camera thread at frame capture time. This clock is disciplined by chrony (see [architecture/07_clocks_and_timestamping.md](../architecture/07_clocks_and_timestamping.md)) but is not wall-clock time.

**`jpeg_size`** / **`events_size`** — used by the parser to slice the payload. A packet is considered malformed and dropped if `jpeg_size` is 0 or exceeds 10 MB, or if the total byte count is less than `29 + events_size + jpeg_size`.

**GPIO state fields** (offsets 20–28) — snapshot of hardware output/input state at the moment the frame was captured. `1` = active. These are convenience fields; the same information is also available event-by-event in the events JSON for inputs and via `_log_output_event` for outputs.

**`trial_state`** — reserved for future use. Always 0 in current firmware.

**`events JSON`** — a JSON array of event dicts that occurred during this frame's capture window. May be an empty array `[]`. See [reference/03_tcp_commands.md](03_tcp_commands.md) for the three event shapes.

**`H264 frame`** — Annex-B encoded H264. Keyframes begin with SPS NAL (NAL type 7, detectable as `img_bytes[4] & 0x1F == 7`). The Pi sends a keyframe every `CAMERA_H264_IPERIOD` frames (default: 60, one per second at 60 fps).

---

## Size limit

The maximum UDP payload is **65,507 bytes**. Packets exceeding this are silently dropped in `UDPSender._pack_and_send()`. At the default bitrate of 2 Mbps and 60 fps, average frame size is ~4 kB, well within the limit.

---

## Parsing on the PC

`parse_packet(raw_data, sender_ip, network_arrival_time)` in [acquisition/packet_parser.py](../../acquisition/packet_parser.py) returns a `ParsedFrame` dataclass with all header fields unpacked plus:

- `events` — decoded Python list of event dicts
- `raw_packet` — the full raw bytes; JPEG/H264 starts at `raw_packet[29 + events_size:]`
- `network_arrival_time` — `time.time()` on the PC when the datagram was received
- `sender_ip` — IP address of the Pi that sent this packet

Returns `None` on any malformed input.
