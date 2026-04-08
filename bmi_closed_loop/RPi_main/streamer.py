import time
import queue
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import Output

class UDPFrameOutput(Output):
    def __init__(self, data_queue, gpio_controller, fsm_data_cb=None):
        super().__init__()
        self.data_queue = data_queue
        self.gpio = gpio_controller
        self.fsm_data_cb = fsm_data_cb

        self.frame_count = 0
        self.start_time = time.time()
        self.fps = 0

    def outputframe(self, frame_bytes, keyframe=True, timestamp=None, packet=None, *args, **kwargs):
        self.frame_count += 1
        elapsed_time = time.time() - self.start_time
        
        # print(f"frame size: {len(frame_bytes)} bytes ({len(frame_bytes)/1024:.1f} KB)")

        if elapsed_time >= 1.0:
            self.fps = self.frame_count / elapsed_time
            print(f"{self.fps:.2f} fps | {len(frame_bytes)/1024:.1f} KB")

            self.frame_count = 0
            self.start_time = time.time()

        current_gpio = self.gpio.get_current_state()
        current_timestamp = timestamp if timestamp is not None else int(time.time() * 1_000_000)

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
        self.encoder = MJPEGEncoder(bitrate=12_000_000)
        
        fps = 60
        width = 1280
        height = 720

        config = self.picam2.create_video_configuration(
            main={
                "size": (width, height), 
                "format": "YUV420"
            },
            controls={
                "FrameDurationLimits": (1000000//fps, 1000000//fps),
                "ExposureTime": 6000,                 
                "AeEnable": False,                    
                "AwbEnable": False,                   
                "NoiseReductionMode": 0, 
                "AnalogueGain": 4.0
            }
        )
        
        if "sensor" not in config:
            config["sensor"] = {}
        config["sensor"]["bit_depth"] = 10
        config["sensor"]["output_size"] = (width, height)
        
        self.picam2.configure(config)

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