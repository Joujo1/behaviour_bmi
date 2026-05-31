"""
Camera capture and H264 encoding pipeline for the Pi-side video stream.

UDPFrameOutput   — picamera2 Output subclass; bundles each encoded frame with
                   the current GPIO state and FSM events, then posts to a queue.
CameraStreamer   — owns the Picamera2 instance, configures it, and wires the
                   encoder output to UDPFrameOutput.
"""

import logging
import queue
import time

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import Output

from config import (
    CAMERA_FPS, CAMERA_WIDTH, CAMERA_HEIGHT,
    CAMERA_BITRATE, CAMERA_H264_IPERIOD, CAMERA_EXPOSURE_US, CAMERA_GAIN,
)

logger = logging.getLogger(__name__)


class UDPFrameOutput(Output):
    """picamera2 Output that bundles encoded frames with GPIO state and FSM events."""

    def __init__(self, data_queue: queue.Queue, gpio_controller, fsm_data_cb=None):
        super().__init__()
        self._data_queue    = data_queue
        self._gpio_controller = gpio_controller
        self._fsm_data_cb   = fsm_data_cb

        self._frame_count      = 0
        self._stats_start_time = time.time()
        self._fps              = 0
        self._iframe_sizes     = []
        self._pframe_sizes     = []
        # Set on first frame: CLOCK_MONOTONIC − cam_pts anchors camera-relative
        # PTS to absolute CLOCK_MONOTONIC, matching engine.py event timestamps.
        self._mono_at_start_us = None

    def outputframe(self, frame_bytes: bytes, keyframe: bool = True, timestamp: int | None = None, packet=None, *args, **kwargs) -> None:
        self._frame_count += 1
        elapsed = time.time() - self._stats_start_time

        if keyframe:
            self._iframe_sizes.append(len(frame_bytes))
        else:
            self._pframe_sizes.append(len(frame_bytes))

        if elapsed >= 60.0:
            self._fps = self._frame_count / elapsed
            avg_i = sum(self._iframe_sizes) / len(self._iframe_sizes) / 1024 if self._iframe_sizes else 0
            avg_p = sum(self._pframe_sizes) / len(self._pframe_sizes) / 1024 if self._pframe_sizes else 0
            max_i = max(self._iframe_sizes) / 1024 if self._iframe_sizes else 0
            logger.info("%.2f fps | I-frame: avg=%.1fKB max=%.1fKB | P-frame: avg=%.1fKB", self._fps, avg_i, max_i, avg_p)
            self._frame_count      = 0
            self._stats_start_time = time.time()
            self._iframe_sizes     = []
            self._pframe_sizes     = []

        current_gpio = self._gpio_controller.get_current_state()
        mono_now_us  = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1e6)

        if self._mono_at_start_us is None:
            self._mono_at_start_us = mono_now_us - (timestamp if timestamp is not None else 0)

        abs_ts = (self._mono_at_start_us + timestamp) if timestamp is not None else mono_now_us
        current_timestamp = abs_ts

        recent_events = []
        if self._fsm_data_cb is not None:
            _, recent_events = self._fsm_data_cb(current_timestamp)

        bundle = {
            'frame':     frame_bytes,
            'gpio':      current_gpio,
            'timestamp': current_timestamp,
            'state':     0,
            'events':    recent_events,
        }

        try:
            self._data_queue.put(bundle, block=False)
        except queue.Full:
            logger.warning("Frame queue full — dropping frame")


class CameraStreamer:
    """Owns the Picamera2 instance and wires it to a UDPFrameOutput for streaming."""

    def __init__(self, data_queue: queue.Queue, gpio_controller, fsm_data_cb=None):
        self._camera       = Picamera2()
        self._frame_output = UDPFrameOutput(data_queue, gpio_controller, fsm_data_cb)
        self._encoder      = H264Encoder(bitrate=CAMERA_BITRATE, iperiod=CAMERA_H264_IPERIOD)

        cam_config = self._camera.create_video_configuration(
            main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT), "format": "YUV420"},
            controls={
                "FrameDurationLimits": (1_000_000 // CAMERA_FPS, 1_000_000 // CAMERA_FPS),
                "ExposureTime":        CAMERA_EXPOSURE_US,
                "AeEnable":            False,
                "AwbEnable":           False,
                "NoiseReductionMode":  0,
                "AnalogueGain":        CAMERA_GAIN,
            },
        )

        if "sensor" not in cam_config:
            cam_config["sensor"] = {}
        cam_config["sensor"]["bit_depth"]   = 10
        cam_config["sensor"]["output_size"] = (CAMERA_WIDTH, CAMERA_HEIGHT)

        self._camera.configure(cam_config)

    def start(self) -> None:
        self._camera.start()
        self._camera.start_recording(self._encoder, self._frame_output, name="main")
        actual_size = self._camera.camera_configuration()['main']['size']
        logger.info("Camera streaming started — size: %s", actual_size)

    def stop(self) -> None:
        self._camera.stop_recording()
        self._camera.stop()
        self._camera.close()
        logger.info("Camera stopped")
