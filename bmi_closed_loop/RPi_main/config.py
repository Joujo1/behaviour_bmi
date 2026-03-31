LED_PINS = {
    "center": 33,
    "left":   35,
    "right":  37,
}

VALVE_PINS = {
    "left":  27,
    "right": 29,
}

IR_PINS = {
    "left":   3,
    "right":  5,
    "center": 7,
}

AUDIO_PINS = {
    "left":  19,
    "right": 21,
}

# All values are physical header pin numbers (gpio_handler uses GPIO.BOARD mode).

# Each IR sensor's active logic and the GPIO edge that signals beam break
# (animal entering the port).
#   All ports wired with pull-down, active HIGH — beam break = RISING edge.
#   Override to True for any port wired active-LOW (pull-up).
IR_ACTIVE_LOW = {
    "left":   False,   # PUD_DOWN, active HIGH
    "right":  False,   # PUD_DOWN, active HIGH
    "center": True,    # PUD_UP,   active LOW  (center poke wired inverted)
}

# Click pulse width in microseconds — how long the GPIO pin stays HIGH.
CLICK_PULSE_US = 100

# Hardware timing
VALVE_OPEN_DEFAULT_MS = 150   # default reward pulse if no duration given
IR_DEBOUNCE_MS        = 50    # bouncetime passed to GPIO.add_event_detect

# Trial safety
TRIAL_WATCHDOG_S = 300        # abort trial after 5 minutes regardless

TCP_PORT        = 6000
UDP_STREAM_PORT = 5005