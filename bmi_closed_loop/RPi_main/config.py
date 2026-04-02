# All values are BCM numbers (gpio_handler uses GPIO.BCM mode).
# Physical header pin numbers from the PCB schematic shown in comments.

LED_PINS = {
    "center": 13,   # physical 33
    "left":   19,   # physical 35
    "right":  26,   # physical 37
}

VALVE_PINS = {
    "left":  0,     # physical 27  (VALVE1 on schematic, BCM 0)
    "right": 5,     # physical 29  (VALVE2 on schematic, BCM 5)
}


BEAM_PINS = {
    "left":   2,    # physical 3  (DIST1)
    "right":  3,    # physical 5  (DIST2)
    "center": 4,    # physical 7  (DIST3)
}

# GPIO pins connected directly to the PAM8302 amplifier audio inputs.
# A brief HIGH pulse (CLICK_PULSE_US microseconds) produces an audible click.
AUDIO_PINS = {
    "left":  10,    # physical 19 (AUD1)
    "right": 9,     # physical 21 (AUD2)
}

# Each beam sensor's active logic level.
# True  = active LOW:  beam break pulls pin LOW  → PUD_UP holds pin HIGH at idle
# False = active HIGH: beam break pulls pin HIGH → PUD_DOWN holds pin LOW at idle
BEAM_ACTIVE_LOW = {
    "left":   True,
    "right":  True,
    "center": True,
}

# Click pulse width in microseconds — how long the GPIO pin stays HIGH.
CLICK_PULSE_US = 100

# Hardware timing
VALVE_OPEN_DEFAULT_MS = 150   # default reward pulse if no duration given
BEAM_DEBOUNCE_MS      = 50    # bouncetime passed to GPIO.add_event_detect

# Trial safety
TRIAL_WATCHDOG_S = 300        # abort trial after 5 minutes regardless

TCP_PORT        = 6000
UDP_STREAM_PORT = 5005
