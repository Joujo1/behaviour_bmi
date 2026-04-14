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


FAN_PIN       = 8
STRIP_PIN     = 25
FAN_PWM_FREQ  = 25.0   # Hz — PWM frequency for the fan SSR gate signal.
                        #
                        # BEFORE CHANGING: look up the SSR part number on the PCB and check
                        # the datasheet for "maximum switching frequency" or "maximum control
                        # input frequency". Never exceed that value — the SSR output will
                        # fail to follow the input and the duty cycle becomes undefined.
                        #
                        # WHAT TO CONSIDER:
                        #   - DC SSRs (transistor output): typically handle 1 kHz – 100 kHz.
                        #     Safe to raise to 200–500 Hz for smooth fan control.
                        #   - AC zero-crossing SSRs: switching is locked to mains zero
                        #     crossings (100 Hz at 50 Hz mains). Raising above ~100 Hz has
                        #     no effect and may cause unpredictable behaviour.
                        #   - RPi.GPIO software PWM (what we use) is implemented in a Python
                        #     thread and has jitter of ~0.1–1 ms. This is acceptable for fan
                        #     control but means frequencies above ~500 Hz become unreliable
                        #     regardless of SSR capability. Use hardware PWM pins (GPIO 12,
                        #     13, 18, 19) and pigpio if you need clean high-frequency PWM.
                        #
                        # WHAT CAN BREAK:
                        #   - Too high for a mechanical relay: contacts weld or burn out
                        #     within minutes. Do NOT use PWM with a mechanical relay at all.
                        #   - Too high for an AC SSR: output no longer tracks input cleanly;
                        #     fan may run at wrong speed or not respond to duty changes.
                        #   - Too low (< 5 Hz): fan motor current has time to fully collapse
                        #     each cycle — fan visibly pulses and bearing life is reduced.
                        #
                        # RECOMMENDED STARTING POINT: confirm SSR type, then:
                        #   DC SSR  → try 200 Hz; increase if fan still audibly pulses.
                        #   AC SSR  → keep at 25–50 Hz; do not exceed 100 Hz.

CLICK_PULSE_US = 100

VALVE_OPEN_DEFAULT_MS = 150
BEAM_DEBOUNCE_MS      = 50

TRIAL_WATCHDOG_S = 300

TCP_PORT        = 6000
UDP_STREAM_PORT = 5002
