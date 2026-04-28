import time
import queue
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import Output

from config import (
    CAMERA_FPS, CAMERA_WIDTH, CAMERA_HEIGHT,
    CAMERA_BITRATE, CAMERA_H264_IPERIOD, CAMERA_EXPOSURE_US, CAMERA_GAIN,
)

class UDPFrameOutput(Output):
    def __init__(self, data_queue, gpio_controller, fsm_data_cb=None):
        super().__init__()
        self.data_queue = data_queue
        self.gpio = gpio_controller
        self.fsm_data_cb = fsm_data_cb

        self.frame_count = 0
        self.start_time = time.time()
        self.fps = 0
        self._iframe_sizes = []
        self._pframe_sizes = []
        # K (set on first frame): CLOCK_MONOTONIC − cam_ts, converts camera-relative
        # timestamps to absolute CLOCK_MONOTONIC, matching engine.py event timestamps.
        self._mono_at_start_us = None

    def outputframe(self, frame_bytes, keyframe=True, timestamp=None, packet=None, *args, **kwargs):
        self.frame_count += 1
        elapsed_time = time.time() - self.start_time

        if keyframe:
            self._iframe_sizes.append(len(frame_bytes))
        else:
            self._pframe_sizes.append(len(frame_bytes))

        if elapsed_time >= 60.0:
            self.fps = self.frame_count / elapsed_time
            avg_i = sum(self._iframe_sizes) / len(self._iframe_sizes) / 1024 if self._iframe_sizes else 0
            avg_p = sum(self._pframe_sizes) / len(self._pframe_sizes) / 1024 if self._pframe_sizes else 0
            max_i = max(self._iframe_sizes) / 1024 if self._iframe_sizes else 0
            print(f"{self.fps:.2f} fps | I-frame: avg={avg_i:.1f}KB max={max_i:.1f}KB | P-frame: avg={avg_p:.1f}KB")
            self.frame_count = 0
            self.start_time = time.time()
            self._iframe_sizes = []
            self._pframe_sizes = []

        current_gpio = self.gpio.get_current_state()
        mono_now_us = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1e6)

        if self._mono_at_start_us is None:
            self._mono_at_start_us = mono_now_us - (timestamp if timestamp is not None else 0)

        abs_ts = (self._mono_at_start_us + timestamp) if timestamp is not None else mono_now_us
        current_timestamp = abs_ts

        recent_events = []

        if self.fsm_data_cb is not None:
            _, recent_events = self.fsm_data_cb()

        trial_state = 0

        bundle = {
            'frame': frame_bytes,
            'gpio': current_gpio,
            'timestamp': current_timestamp,
            'state': trial_state,
            'events': recent_events
        }

        try:
            self.data_queue.put(bundle, block=False)
        except queue.Full:
            print("Warning: Network Queue Full")


class CameraStreamer:
    def __init__(self, data_queue, gpio_controller, fsm_data_cb=None):
        self.picam2 = Picamera2()
        
        self.stream_output = UDPFrameOutput(data_queue, gpio_controller, fsm_data_cb)
        self.encoder = H264Encoder(bitrate=CAMERA_BITRATE, iperiod=CAMERA_H264_IPERIOD)

        cam_config = self.picam2.create_video_configuration(
            main={
                "size": (CAMERA_WIDTH, CAMERA_HEIGHT),
                "format": "YUV420"
            },
            controls={
                "FrameDurationLimits": (1000000 // CAMERA_FPS, 1000000 // CAMERA_FPS),
                "ExposureTime": CAMERA_EXPOSURE_US,
                "AeEnable": False,
                "AwbEnable": False,
                "NoiseReductionMode": 0,
                "AnalogueGain": CAMERA_GAIN,
            }
        )

        if "sensor" not in cam_config:
            cam_config["sensor"] = {}
        cam_config["sensor"]["bit_depth"] = 10
        cam_config["sensor"]["output_size"] = (CAMERA_WIDTH, CAMERA_HEIGHT)
        
        self.picam2.configure(cam_config)

    def start(self):
        self.picam2.start()
        self.picam2.start_recording(self.encoder, self.stream_output, name="main")
        
        actual_size = self.picam2.camera_configuration()['main']['size']
        print(f"Global Shutter Camera streaming started at {actual_size}")

    def stop(self):
        self.picam2.stop_recording()
        self.picam2.stop()
        self.picam2.close()
        print("Camera stopped")