import json
import struct
from dataclasses import dataclass, field
from typing import Optional

HEADER_FORMAT = "<IQIIBBBBBBB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


@dataclass
class ParsedFrame:
    # used by the Postgres write (frame metadata + GPIO state per chunk)
    frame_num: int
    timestamp: int          # microseconds, from Pi
    jpeg_size: int
    events_size: int        # bytes of JSON events between header and jpeg
    led_center: int
    valve_left: int
    valve_right: int
    sensor_left: int
    sensor_right: int
    sensor_center: int
    trial_state: int
    events: list

    # jpeg is sliced from here for Valkey: raw_packet[HEADER_SIZE + events_size:]
    raw_packet: bytes

    network_arrival_time: float
    sender_ip: str


def parse_packet(raw_data: bytes, sender_ip: str, network_arrival_time: float):
    if len(raw_data) < HEADER_SIZE:
        return None

    (
        frame_num, timestamp, jpeg_size, events_size,
        led_center, valve_left, valve_right,
        sensor_left, sensor_right, sensor_center,
        trial_state,
    ) = struct.unpack(HEADER_FORMAT, raw_data[:HEADER_SIZE])

    if not jpeg_size or jpeg_size <= 0 or jpeg_size > 10_000_000:
        return None

    expected_size = HEADER_SIZE + events_size + jpeg_size
    if len(raw_data) < expected_size:
        return None

    events = []
    if events_size > 0:
        try:
            events = json.loads(
                raw_data[HEADER_SIZE : HEADER_SIZE + events_size].decode("utf-8")
            )
        except Exception:
            pass

    return ParsedFrame(
        frame_num=frame_num,
        timestamp=timestamp,
        jpeg_size=jpeg_size,
        events_size=events_size,
        led_center=led_center,
        valve_left=valve_left,
        valve_right=valve_right,
        sensor_left=sensor_left,
        sensor_right=sensor_right,
        sensor_center=sensor_center,
        trial_state=trial_state,
        events=events,
        raw_packet=raw_data[:expected_size],
        network_arrival_time=network_arrival_time,
        sender_ip=sender_ip,
    )
