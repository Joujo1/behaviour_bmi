# Reading Per-Frame Packages from NAS

When recording is active, every received UDP packet is written to a binary `.bin` file on the NAS. Each file corresponds to one cage and one session. The format is a simple length-prefixed sequence of raw packets.

---

## File location

Files are written to:

```
<NAS_BASE_PATH>/session_<session_id>/cage_<cage_id>.bin
```

`NAS_BASE_PATH` is defined in [bmi_closed_loop/config.py](../../config.py).

---

## File format

The file is a flat sequence of frames, each stored as:

```
[4 bytes: uint32 little-endian packet length][N bytes: raw UDP packet]
```

The raw UDP packet is the complete datagram exactly as received from the Pi — header + events JSON + H264 frame. See [reference/02_udp_packet_format.md](../reference/02_udp_packet_format.md) for the packet layout.

---

## Reading the file in Python

```python
import struct
from bmi_closed_loop.acquisition.packet_parser import parse_packet, HEADER_SIZE

with open("cage_1.bin", "rb") as f:
    while True:
        length_bytes = f.read(4)
        if len(length_bytes) < 4:
            break
        (packet_length,) = struct.unpack("<I", length_bytes)
        raw_packet = f.read(packet_length)
        if len(raw_packet) < packet_length:
            break

        frame = parse_packet(raw_packet, sender_ip="192.168.1.101", network_arrival_time=0.0)
        if frame is None:
            continue

        print(f"seq={frame.pi_seq}  ts={frame.timestamp}µs  events={frame.events}")

        # Extract the H264 frame bytes:
        h264 = raw_packet[HEADER_SIZE + frame.events_size:]
```

`parse_packet` returns a `ParsedFrame` with all header fields, the decoded events list, and the raw bytes. The H264 data starts at offset `HEADER_SIZE + events_size` within the raw packet.

---

## Postgres chunk index

The database table `recordings` stores a chunk index that maps byte offsets into the `.bin` file to frame ranges. Each row covers `DB_CHUNK_SIZE` frames (default 1000) and records:

| Column | Description |
|---|---|
| `chunk_start_frame` | Pi sequence number of first frame in chunk |
| `chunk_end_frame` | Pi sequence number of last frame in chunk |
| `chunk_start_ts` | CLOCK_MONOTONIC timestamp of first frame (µs) |
| `chunk_end_ts` | CLOCK_MONOTONIC timestamp of last frame (µs) |
| `chunk_byte_offset` | Byte position in the `.bin` file where this chunk starts |
| `chunk_frame_count` | Number of frames in this chunk |

You can use this index to seek directly to a time range without scanning the whole file:

```python
# Example: find the byte offset for frames near a given CLOCK_MONOTONIC timestamp
cur.execute("""
    SELECT chunk_byte_offset
    FROM recordings
    WHERE cage_id = %s AND chunk_start_ts <= %s
    ORDER BY chunk_start_ts DESC LIMIT 1
""", (cage_id, target_ts_us))
```
