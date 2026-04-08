# All values are BCM numbers (gpio_handler uses GPIO.BCM mode).

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

# A brief HIGH pulse (CLICK_PULSE_US microseconds) produces an audible click.
AUDIO_PINS = {
    "left":  10,    # physical 19
    "right": 9,     # physical 21
}

BEAM_ACTIVE_LOW = {
    "left":   True,
    "center":  True,
    "right": True,
}

CLICK_PULSE_US = 100

VALVE_OPEN_DEFAULT_MS = 150
BEAM_DEBOUNCE_MS      = 50

TRIAL_WATCHDOG_S = 300

TCP_PORT        = 6000
UDP_STREAM_PORT = 5002
