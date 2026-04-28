# BCM numbering

LED_PINS = {
    "left": 13,   # physical 33
    "center":   19,   # physical 35
    "right":  26,   # physical 37
}

VALVE_PINS = {
    "left":  0,     # physical 27
    "right": 5,     # physical 29
}


BEAM_PINS = {
    "left":   2,    # physical 3
    "center":  3,    # physical 5
    "right": 4,    # physical 7
}

# CLICK_PULSE_US microseconds produces an audible click
AUDIO_PINS = {
    "left":  10,    # physical 19
    "right": 9,     # physical 21
}

BEAM_ACTIVE_LOW = {
    "left":   True,
    "center":  True,
    "right": True,
}


FAN_PIN       = 8
STRIP_PIN     = 25
FAN_PWM_FREQ  = 200.0
FAN_MIN_DUTY  = 30    # % — below this the fan turns off instead of running at low speed

CLICK_PULSE_US = 100

VALVE_OPEN_DEFAULT_MS = 150
BEAM_DEBOUNCE_MS      = 1    # IR sensors have no mechanical bounce; 1ms filters electrical glitches only

TRIAL_WATCHDOG_S = 1200

TCP_PORT        = 6000
UDP_STREAM_PORT = 5002

# Camera
CAMERA_FPS          = 60
CAMERA_WIDTH        = 1080
CAMERA_HEIGHT       = 720
CAMERA_BITRATE      = 2_000_000   # H264 — keeps I-frames well under UDP 65507 limit
CAMERA_H264_IPERIOD = 60          # I-frame every 1 s at 60 fps
CAMERA_EXPOSURE_US  = 6000
CAMERA_GAIN         = 4.0

FRAME_QUEUE_MAXSIZE = 30

# Audio (sounddevice)
AUDIO_DEVICE = 1        # Pi 4 audio jack (run `python -m sounddevice` to list)
AUDIO_SRATE  = 48_000

# GPS / PPS
# Wiring: GPS TX → GPIO15 (Pi UART RX), GPS PPS → GPIO18, VIN → 3.3 V
# Pi one-time setup:
#   raspi-config → Interface Options → Serial Port → login shell: No, hardware: Yes
#   Add to /boot/config.txt: dtoverlay=pps-gpio,gpiopin=18
#   Disable Bluetooth for full UART: dtoverlay=disable-bt in /boot/config.txt → use /dev/ttyAMA0
GPS_PPS_PIN   = 18             # wiring reference — owned by pps-gpio kernel driver at runtime
GPS_PPS_DEV   = '/dev/pps0'   # kernel PPS device created by dtoverlay=pps-gpio
GPS_UART_PORT = '/dev/ttyAMA0'  # full UART (BT disabled via dtoverlay=disable-bt)
GPS_UART_BAUD = 9600
GPS_LOG_DIR   = '/home/pi/gps_logs'
