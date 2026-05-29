"""
Hardware pin assignments and tunable constants for the Pi-side trial controller.

All values use BCM (Broadcom) GPIO numbering.
"""

LED_PINS = {
    "left":   13,   # physical 33
    "center": 19,   # physical 35
    "right":  26,   # physical 37
}

VALVE_PINS = {
    "left":  0,     # physical 27
    "right": 5,     # physical 29
}

BEAM_PINS = {
    "left":   2,    # physical 3
    "center": 3,    # physical 5
    "right":  4,    # physical 7
}

AUDIO_PINS = {
    "left":  9,     # physical 26  (TTL trigger → ItsyBitsy D9)
    "right": 10,     # physical 28  (TTL trigger → ItsyBitsy D10)
}

BEAM_ACTIVE_LOW = {
    "left":   True,
    "center": True,
    "right":  True,
}

FAN_PIN      = 8
STRIP_PIN    = 25
FAN_PWM_FREQ = 200.0
FAN_MIN_DUTY = 30

CLICK_PULSE_US = 50

VALVE_OPEN_DEFAULT_MS = 150

TRIAL_WATCHDOG_S = 1200

# ── Emulator ──────────────────────────────────────────────────────────────────
# Set EMULATE = True to skip real GPIO beam monitoring and inject synthetic
# beam events instead.  No hardware wiring required.
# EMULATE_OUTCOMES is cycled in order; repeat the list as needed.
EMULATE = False
def _looping_outcomes(n_cycles: int = 100) -> list:
    """
    One cycle = 30 decided trials, always ending back in S3.
    Advancement events per cycle (decided-trial offsets are relative to
    the start of each substage entry):

      S1  trials 1-10:  10/10 correct  → ADVANCE S1→S2  (at decided 10)
      S2  trials 1-10:  9/10  correct  → ADVANCE S2→S3  (at decided 10)
      S3  trials 1-10:  4/10  correct  → FALLBACK S3→S2 (at decided 10)
      S2  trials 1-10:  10/10 correct  → ADVANCE S2→S3  (at decided 10)
      … then S3 fails again, restarting the loop from S2

    Each cycle after the first starts from S2 (already advanced past S1 once).
    First cycle includes S1→S2 bootstrap.
    """
    # Bootstrap: S1→S2 (10 correct)
    bootstrap = [
        "correct","correct","correct","correct","correct",
        "correct","correct","correct","correct","correct",
    ]
    # One repeating unit: S2→S3→S2→S3 (30 decided trials per iteration)
    # S2 advance (9/10):
    s2_advance = [
        "correct","correct","correct","correct","wrong",
        "correct","correct","correct","correct","correct",
    ]
    # S3 fallback (4/10):
    s3_fallback = [
        "correct","correct","correct","correct",
        "wrong","wrong","wrong","wrong","wrong","wrong",
    ]
    # S2 advance again (10/10):
    s2_advance2 = [
        "correct","correct","correct","correct","correct",
        "correct","correct","correct","correct","correct",
    ]
    # S3 fallback again (4/10) — ends cycle, returns to S2:
    s3_fallback2 = [
        "correct","correct","correct","correct",
        "wrong","wrong","wrong","wrong","wrong","wrong",
    ]
    cycle = s2_advance + s3_fallback + s2_advance2 + s3_fallback2
    return bootstrap + cycle * n_cycles


EMULATE_OUTCOMES = _looping_outcomes(n_cycles=100)

# Fixed delay before each beam break (seconds).  Keep these constant so every
# trial takes a predictable, known duration — required for validating that
# curriculum advancement triggers at exactly the expected trial boundaries.
EMULATE_PRE_BEAM_DELAY_S  = 0.3    # wait before breaking each beam
EMULATE_BEAM_HOLD_S       = 0.15   # must exceed any hold_ms in trial transitions (easy substage uses 5ms)

TCP_PORT        = 6000
UDP_STREAM_PORT = 5002

CAMERA_FPS          = 60
CAMERA_WIDTH        = 480
CAMERA_HEIGHT       = 320
CAMERA_BITRATE      = 2_000_000
CAMERA_H264_IPERIOD = 60
CAMERA_EXPOSURE_US  = 6000
CAMERA_GAIN         = 4.0

FRAME_QUEUE_MAXSIZE = 30

#AUDIO_DEVICE  = 1
AUDIO_SRATE   = 48_000
CLICK_WIDTH_S = 0.003
