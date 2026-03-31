# All values are BCM numbers (gpio_handler uses GPIO.BCM mode).
# Physical header pin numbers from the PCB schematic shown in comments.

LED_PINS = {
    "center": 13,   # physical 33
    "left":   19,   # physical 35
    "right":  26,   # physical 37
}

VALVE_PINS = {
    "left":  5,     # physical 29  (VALVE2 on schematic — see note below)
    "right": 6,     # physical 31  (VALVE3 on schematic)
}
# NOTE: schematic VALVE1 is on physical 27 → BCM 0 (HAT EEPROM SDA pin).


IR_PINS = {
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

# Each IR sensor's active logic level.
# False = PUD_DOWN, active HIGH (beam break = RISING edge)
# True  = PUD_UP,   active LOW  (beam break = FALLING edge)
IR_ACTIVE_LOW = {
    "left":   False,
    "right":  False,
    "center": True,    # center poke wired with pull-up, active LOW
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
