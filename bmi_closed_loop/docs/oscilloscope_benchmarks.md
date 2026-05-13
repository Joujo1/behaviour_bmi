# Oscilloscope Benchmark Guide
# Automated Behavioural Training Rig — Real-Time Performance Characterisation
#
# All GPIO pin numbers are BCM unless stated otherwise.
# Physical (board) pin numbers are listed next to each probe point.
# Connect oscilloscope GND probe to any Pi GND pin (e.g. physical pin 6 or 9).
#
# GPIO reference (from RPi_main/config.py):
#   Beam left:    BCM 2  (physical 3)
#   Beam center:  BCM 3  (physical 5)
#   Beam right:   BCM 4  (physical 7)
#   LED left:     BCM 13 (physical 33)
#   LED center:   BCM 19 (physical 35)
#   LED right:    BCM 26 (physical 37)
#   Valve left:   BCM 0  (physical 27)
#   Valve right:  BCM 5  (physical 29)
#   Audio L/R:    3.5 mm jack (or BCM 10/9 for GPIO fallback)
#
# Voltage levels: 3.3 V logic on all GPIO.
# Beams are ACTIVE LOW (beam broken = pin goes LOW).
# LEDs and valves are ACTIVE HIGH (on = pin goes HIGH).
# =============================================================================


================================================================================
MEASUREMENT 1: FSM Transition Latency (Headline Number)
================================================================================

WHAT IT MEASURES
  The end-to-end time from a hardware beam break (rising/falling edge on a
  sensor GPIO) to the Pi asserting a GPIO output in response. This captures
  the full software chain:
    kernel IRQ → Python interrupt callback → event queue push
    → FSM thread wakeup → state transition logic → GPIO write

  This is the number most directly comparable to pyControl (556 ± 17 µs) and
  LabNet (0.26 ms median). It is the headline latency claim for the thesis.

HARDWARE SETUP
  - Scope channel 1 (CH1): probe Beam center pin (BCM 3, physical 5)
  - Scope channel 2 (CH2): probe LED center pin  (BCM 19, physical 35)
  - Scope GND: Pi GND (physical 6)
  - To simulate a beam break without a physical beam: connect a 1 kΩ resistor
    from the beam pin to GND and manually short it with a wire, OR use a
    signal generator outputting a 3.3 V logic signal.
  - Alternatively: block/unblock the actual IR beam with your finger.

TRIAL DEFINITION (create in the curriculum builder)
  Paste this JSON as the task config for a new substage called "bench_fsm":

  {
    "trial_id": "bench_fsm_latency",
    "side_mode": "fixed_left",
    "base_iti_s": 1.0,
    "fail_iti_s": 1.0,
    "initial_state": "wait_for_beam",
    "states": [
      {
        "id": "wait_for_beam",
        "duration": 30.0,
        "entry_actions": [],
        "exit_actions": [],
        "transitions": [
          { "trigger": "beam_break", "target": "center", "next_state": "respond" },
          { "trigger": "timeout", "next_state": "__wrong__" }
        ]
      },
      {
        "id": "respond",
        "duration": 2.0,
        "entry_actions": [
          { "type": "led_on", "target": "center" }
        ],
        "exit_actions": [
          { "type": "led_off", "target": "center" }
        ],
        "transitions": [
          { "trigger": "timeout", "next_state": "__correct__" }
        ]
      }
    ]
  }

OSCILLOSCOPE SETTINGS
  - Timebase: 1 ms/div (gives 10 ms total window, enough to see the edge)
  - Voltage scale CH1: 2 V/div (beam signal, active low — falls from 3.3 V to 0 V)
  - Voltage scale CH2: 2 V/div (LED signal, active high — rises from 0 V to 3.3 V)
  - Trigger: CH1, falling edge, ~1.5 V threshold (beam breaks → goes low)
  - Trigger mode: Normal (single-shot per break event)
  - Use cursor measurement or "Δt" function to read time between CH1 falling
    edge and CH2 rising edge

PROCEDURE
  1. Start a session on the master PC, assign the rat to substage "bench_fsm".
  2. Start continuous trials on the target cage via the UI.
  3. Arm the scope in Normal trigger mode.
  4. Break the beam (finger, card, or signal generator).
  5. Scope captures: read Δt from CH1 falling edge → CH2 rising edge.
  6. Record the value. Reset scope, repeat.
  7. Collect N ≥ 500 samples. Log each reading to a CSV manually or use
     the scope's statistics mode if available (mean/std/min/max built in
     on most Rigol/Siglent/Keysight scopes).

WHAT TO REPORT
  - Mean latency ± std
  - Minimum and maximum observed
  - 99th percentile (worst-case)
  - Histogram of distribution (bins of 100 µs)
  - Repeat under 12-cage load (see Measurement 9) and compare


================================================================================
MEASUREMENT 2: Threading.Timer Accuracy (State Timeout Jitter)
================================================================================

WHAT IT MEASURES
  FSM state timeouts are implemented via Python's threading.Timer. On a
  non-RTOS Linux system, timer callbacks are subject to OS scheduler jitter.
  This measures: how accurately does a 1000 ms timeout fire at exactly 1000 ms?

  This matters for trial timing — if timeout jitter is ±50 ms, your stimulus
  durations are imprecise by ±50 ms, which affects spike-event alignment.

HARDWARE SETUP
  - Scope CH1: probe LED center pin (BCM 19, physical 35)
    LED turns ON at state entry, turns OFF when timeout fires → next state
  - Scope GND: Pi GND
  - No beam break needed — the state just times out.

TRIAL DEFINITION
  {
    "trial_id": "bench_timeout",
    "side_mode": "fixed_left",
    "base_iti_s": 0.5,
    "fail_iti_s": 0.5,
    "initial_state": "timed_state",
    "states": [
      {
        "id": "timed_state",
        "duration": 1.0,
        "entry_actions": [{ "type": "led_on",  "target": "center" }],
        "exit_actions":  [{ "type": "led_off", "target": "center" }],
        "transitions": [
          { "trigger": "timeout", "next_state": "__correct__" }
        ]
      }
    ]
  }

  Variants to test: duration = 0.1 s, 0.5 s, 1.0 s, 2.0 s
  Shorter timeouts will show more relative jitter.

OSCILLOSCOPE SETTINGS
  - Timebase: set to show the full expected pulse width + 50 ms on each side
    e.g. for 1000 ms: 200 ms/div (gives 2 s window)
  - Trigger: CH1, rising edge (LED comes on at state entry = start of timer)
  - Measure: pulse width of the HIGH period on CH1
    (rising edge to falling edge = actual timer duration)
  - Most scopes have a "pulse width" or "period" automatic measurement — use it.

PROCEDURE
  1. Run continuous trials with the bench_timeout substage.
  2. Set scope to measure pulse width automatically.
  3. Let the scope accumulate statistics over 500+ cycles (it does this
     automatically in "statistics" mode — enable Mean, StdDev, Min, Max).
  4. Repeat for each duration variant.

WHAT TO REPORT
  - Mean measured duration vs. programmed duration (systematic offset)
  - Standard deviation (jitter)
  - Min / Max observed
  - Table across durations (0.1 s, 0.5 s, 1.0 s, 2.0 s)
  - Repeat under load (Measurement 9)


================================================================================
MEASUREMENT 3: Hold Timer Accuracy
================================================================================

WHAT IT MEASURES
  The hold_ms feature requires the animal to hold a beam break for a specified
  duration before the FSM advances. This is implemented as a threading.Timer
  started at beam-break time. This measures: how accurately does hold_ms fire?

  This directly affects task validity — if hold_ms=100 fires at 85 ms, the
  animal is rewarded for shorter holds than intended.

HARDWARE SETUP
  - Scope CH1: probe Beam center (BCM 3, physical 5) — active low
  - Scope CH2: probe LED center  (BCM 19, physical 35) — LED turns on in
    the state AFTER the hold completes
  - Scope GND: Pi GND

TRIAL DEFINITION
  {
    "trial_id": "bench_hold",
    "side_mode": "fixed_left",
    "base_iti_s": 0.5,
    "fail_iti_s": 0.5,
    "initial_state": "wait",
    "states": [
      {
        "id": "wait",
        "duration": 30.0,
        "entry_actions": [],
        "exit_actions": [],
        "transitions": [
          {
            "trigger": "beam_break",
            "target": "center",
            "hold_ms": 100,
            "next_state": "held"
          },
          { "trigger": "timeout", "next_state": "__wrong__" }
        ]
      },
      {
        "id": "held",
        "duration": 1.0,
        "entry_actions": [{ "type": "led_on",  "target": "center" }],
        "exit_actions":  [{ "type": "led_off", "target": "center" }],
        "transitions": [
          { "trigger": "timeout", "next_state": "__correct__" }
        ]
      }
    ]
  }

  Test with hold_ms: 50, 100, 200, 500

OSCILLOSCOPE SETTINGS
  - Timebase: 10 ms/div (for 100 ms hold — gives 100 ms window)
  - Trigger: CH1 falling edge (beam breaks)
  - Measure Δt: CH1 falling edge → CH2 rising edge = actual hold duration

  Important: keep the beam blocked continuously during the hold. Use a card
  or a wire connecting the beam pin to GND (simulate a held break) rather
  than relying on a human finger, which may wobble and cause debounce events.

PROCEDURE
  Same as Measurement 1 but measure the time from CH1 falling edge to CH2
  rising edge. N ≥ 300 samples per hold_ms value.

WHAT TO REPORT
  - Mean hold duration vs. programmed hold_ms (systematic bias)
  - Std deviation (jitter)
  - Table across hold_ms values


================================================================================
MEASUREMENT 4: Audio Onset Latency
================================================================================

WHAT IT MEASURES
  Time from the FSM dispatching a play_clicks action (LED GPIO used as
  proxy timestamp) to the first audio sample actually appearing at the DAC
  output (3.5 mm jack). This is the sounddevice buffer latency.

  This is the most experiment-critical latency: the rat hears the first
  click some time after the state is entered. All trial timestamps are
  aligned to state entry, so audio onset latency is a systematic offset
  in your behavioural data. You need to report it so others can correct for it.

HARDWARE SETUP
  - Scope CH1: probe LED left pin (BCM 13, physical 33)
    Use left LED as a "state entry" marker — turn it on simultaneously with
    play_clicks in the entry_actions list.
  - Scope CH2: connect to 3.5 mm audio jack tip (left channel)
    Use a 3.5 mm to BNC adapter, or strip a 3.5 mm cable and probe the tip
    wire. The audio signal is a ±1 V AC waveform.
    Set CH2 to AC coupling, 200 mV/div.
  - Scope GND: Pi GND

TRIAL DEFINITION
  {
    "trial_id": "bench_audio_latency",
    "side_mode": "fixed_left",
    "base_iti_s": 1.0,
    "fail_iti_s": 1.0,
    "initial_state": "play",
    "states": [
      {
        "id": "play",
        "duration": 3.0,
        "entry_actions": [
          { "type": "led_on",      "target": "left" },
          { "type": "play_clicks", "left_rate": 100, "right_rate": 0, "click_duration": 2.5 }
        ],
        "exit_actions": [
          { "type": "led_off", "target": "left" }
        ],
        "transitions": [
          { "trigger": "timeout", "next_state": "__correct__" }
        ]
      }
    ]
  }

  Note: left_rate=100 Hz gives dense clicks, easy to see on scope.
  Using right_rate=0 isolates left channel for clean probing.

OSCILLOSCOPE SETTINGS
  - Timebase: 5 ms/div (50 ms window — audio latency is typically 10–30 ms)
  - CH1: DC coupling, 2 V/div (GPIO logic signal)
  - CH2: AC coupling, 500 mV/div (audio)
  - Trigger: CH1 rising edge (LED turns on = state entry)
  - Measure Δt: CH1 rising edge → first audio peak on CH2

PROCEDURE
  1. Run continuous trials.
  2. Arm scope, wait for LED rising edge trigger.
  3. Measure Δt to first visible click waveform on CH2.
  4. N ≥ 200 samples (audio latency is fairly stable, less variable than GPIO).

WHAT TO REPORT
  - Mean audio onset latency ± std
  - This is the systematic offset to report in Methods for all behavioural analyses


================================================================================
MEASUREMENT 5: Click Inter-Arrival Interval Distribution
================================================================================

WHAT IT MEASURES
  Whether the intended Poisson-distributed inter-click intervals (ICI) are
  preserved through the audio pipeline. If sounddevice introduces timing
  distortion, your click trains are not truly Poisson, which invalidates the
  psychophysics task.

HARDWARE SETUP
  - Scope CH1: 3.5 mm audio jack (same setup as Measurement 4)
  - No GPIO probe needed

OSCILLOSCOPE SETTINGS
  - Timebase: 20 ms/div (to see multiple clicks)
  - CH1: AC coupling, 500 mV/div
  - Trigger: CH1, rising edge on a click peak

  Better approach: capture a long waveform (use scope "record" or screenshot
  mode) for a single 2.5 s click train, then export the data and compute
  ICI statistics in Python/MATLAB offline.
  Many Rigol/Siglent scopes can export CSV waveform data via USB.

PROCEDURE
  1. Capture a full 2.5 s click train at maximum sample rate.
  2. Export waveform as CSV from scope USB port.
  3. In Python: threshold the waveform, find click peak times, compute ICIs.
  4. Plot ICI histogram and overlay the expected exponential distribution
     (rate λ = left_rate, mean ICI = 1/λ).
  5. Repeat for several rate pairs: (80, 20), (60, 40), (50, 50), (100, 0).

WHAT TO REPORT
  - ICI histogram vs. theoretical exponential for each rate
  - Kolmogorov-Smirnov test p-value (confirms or rejects Poisson hypothesis)
  - Any systematic deviation (e.g. minimum ICI floor from CLICK_WIDTH_S = 3 ms)


================================================================================
MEASUREMENT 6: Valve Open Duration Precision
================================================================================

WHAT IT MEASURES
  Reward valves are opened for a fixed duration to deliver a precise water
  volume. Valve duration jitter directly translates to water volume variance,
  which matters for welfare records and experiment reproducibility.

HARDWARE SETUP
  - Scope CH1: probe Valve left pin (BCM 0, physical 27)
  - Scope GND: Pi GND

TRIAL DEFINITION
  {
    "trial_id": "bench_valve",
    "side_mode": "fixed_left",
    "base_iti_s": 2.0,
    "fail_iti_s": 2.0,
    "initial_state": "reward",
    "states": [
      {
        "id": "reward",
        "duration": 1.0,
        "entry_actions": [
          { "type": "valve_open",  "target": "left" }
        ],
        "exit_actions": [
          { "type": "valve_close", "target": "left" }
        ],
        "transitions": [
          { "trigger": "timeout", "next_state": "__correct__" }
        ]
      }
    ]
  }

  The valve is open for the full state duration (1.0 s here). To test shorter
  pulses, reduce duration to 0.15 s (= VALVE_OPEN_DEFAULT_MS = 150 ms).

OSCILLOSCOPE SETTINGS
  - Timebase: 50 ms/div for 150 ms pulse
  - CH1: DC coupling, 2 V/div
  - Trigger: CH1 rising edge
  - Use automatic pulse-width measurement and statistics mode

PROCEDURE
  N ≥ 300 trials. Use scope statistics mode to accumulate automatically.

WHAT TO REPORT
  - Mean valve open duration vs. programmed duration
  - Std deviation
  - Convert to volume: typical solenoid valve delivers ~3–8 µL/ms, so
    1 ms jitter ≈ 3–8 µL variance per reward


================================================================================
MEASUREMENT 7: Audio-to-LED Synchronisation (Multi-modal Stimulus Onset)
================================================================================

WHAT IT MEASURES
  In the actual task, LED and click train are presented simultaneously as the
  stimulus. This measures how well-synchronised they actually are at the
  hardware output level.

HARDWARE SETUP
  - Scope CH1: probe LED left pin (BCM 13, physical 33)
  - Scope CH2: 3.5 mm audio jack tip (left channel)
  - Scope GND: Pi GND

TRIAL DEFINITION
  Use the same definition as Measurement 4 (bench_audio_latency).
  The LED rising edge is the GPIO event; the first audio click is the
  first sensory event the animal perceives. The delta is the
  audio-visual asynchrony for this multi-modal stimulus.

OSCILLOSCOPE SETTINGS
  - Same as Measurement 4

WHAT TO REPORT
  - Mean audio-LED delta (this IS the audio onset latency from Measurement 4,
    confirming consistency)
  - Frame it as: "visual and auditory stimuli are offset by X ms, with the
    LED preceding the first click"


================================================================================
MEASUREMENT 8: Camera–GPIO Timestamp Synchronisation
================================================================================

WHAT IT MEASURES
  The Pi embeds a GPIO state snapshot in every UDP frame header, timestamped
  via CLOCK_MONOTONIC. This measurement validates whether the camera frame
  timestamps correctly correspond to when the GPIO state was actually captured.

  Specifically: when an LED turns on (GPIO event at time T_gpio), what is the
  timestamp of the first camera frame in which the LED appears lit?
  The difference (T_frame - T_gpio) should equal 0 ± one frame period (16.7 ms
  at 60 fps). Larger errors indicate a bug in the timestamp anchoring code
  (streamer.py).

HARDWARE SETUP
  - Scope CH1: probe LED center pin (BCM 19, physical 35)
  - Point the cage camera directly at the LED so it is visible in-frame.
  - No second scope probe needed — the camera is your second "channel".

PROCEDURE
  1. Run the bench_fsm_latency trial definition (Measurement 1).
  2. Record a session with camera recording enabled (NAS write on).
  3. Scope: arm on CH1 rising edge, record the absolute timestamp
     of the LED rising edge (scope time display or external time reference).
     Alternatively: log the CLOCK_MONOTONIC time in the FSM when the LED fires
     (add a single print/log statement to engine.py action dispatch).
  4. After the session, open the .bin recording in bin_viewer.py.
  5. Find the frame where the LED state bit first changes to 1 in the header.
     Read the frame's embedded timestamp.
  6. Delta = frame_timestamp - gpio_action_timestamp
     Expected: between 0 and 16.7 ms (one frame period).

WHAT TO REPORT
  - Mean synchronisation error ± std over N ≥ 100 events
  - Histogram of errors
  - Confirm: are errors always positive (frame timestamp always after GPIO)?
    If some are negative, there is a timestamp anchoring bug.


================================================================================
MEASUREMENT 9: Latency Under Load (Scaling Validation)
================================================================================

WHAT IT MEASURES
  All measurements above should be repeated under full 12-cage load to verify
  that the system scales without performance degradation. This is the key
  scalability claim for the thesis.

SETUP
  - Run Measurements 1, 2, and 4 with only 1 cage active (baseline).
  - Then repeat with 12 cages running simultaneous trials.
  - The cage under measurement runs the benchmark trial definition;
    the other 11 cages run the normal task (or any continuous trial loop).

WHAT TO COMPARE
  - FSM latency: mean and 99th percentile, 1 cage vs. 12 cages
  - Timeout jitter: std deviation, 1 cage vs. 12 cages
  - Audio onset latency: mean, 1 cage vs. 12 cages
  - Frame drop rate: check acquisition logs for UDP sequence number gaps
    (watchdog.py logs these)

WHAT TO REPORT
  - Table: all metrics at N=1 vs N=12 cages
  - If latency is stable: "the system scales to 12 parallel cages without
    measurable degradation in real-time performance"
  - If latency increases: quantify by how much and identify the bottleneck
    (CPU, network, Python GIL contention)


================================================================================
MEASUREMENT 10: TCP Command Latency (PC → Pi Round-Trip)
================================================================================

WHAT IT MEASURES
  The time from the PC sending a trial start command over TCP to the Pi's
  first GPIO output (LED turning on in the initial state's entry_actions).
  This includes: network RTT + TCP stack + Python recv + FSM state init.

HARDWARE SETUP
  - Scope CH1: probe LED center pin (BCM 19, physical 35)
  - On the PC side: add a timestamp log in tcp_command_sender.py at the
    moment the command bytes are written to the socket.
  - Compare: PC-side send timestamp vs. scope CH1 rising edge timestamp
    (read from scope display relative to a time reference).

  Easier alternative: wire a second GPIO output on the Pi to trigger
  immediately on TCP message receipt (before any FSM logic), probe it as
  CH2. Then Δt(CH1 - CH2) = FSM init overhead alone, and the total latency
  from the PC log is the network + processing total.

TRIAL DEFINITION
  Any trial definition where initial_state has an immediate LED entry action
  (e.g., bench_fsm_latency).

WHAT TO REPORT
  - Mean PC→Pi GPIO latency ± std
  - Breakdown: network RTT (measure separately with ping -c 1000 192.168.1.101)
    vs. Python processing overhead


================================================================================
MEASUREMENT 11: SCHED_FIFO Effect on Jitter
================================================================================

WHAT IT MEASURES
  Whether enabling real-time POSIX scheduling (SCHED_FIFO) in engine.py
  meaningfully reduces latency or jitter. This is activated by running the
  Pi code as root with the SCHED_FIFO flag set.

PROCEDURE
  1. Run Measurement 1 (FSM transition latency) in NORMAL mode.
     Record full distribution (N ≥ 500).
  2. In RPi_main/engine.py, enable SCHED_FIFO for the FSM thread (requires
     running main.py as root on the Pi: sudo python main.py).
  3. Run Measurement 1 again under identical conditions.
  4. Compare distributions, especially the tail (99th percentile and max).

WHAT TO REPORT
  - Side-by-side comparison: normal vs. SCHED_FIFO
  - Does the mean change? (probably not)
  - Does the 99th percentile or maximum change? (likely yes — SCHED_FIFO
    primarily reduces outliers, not the mean)
  - Practical recommendation: is SCHED_FIFO necessary for this application?


================================================================================
MEASUREMENT 12: Inter-Trial Interval (ITI) Precision
================================================================================

WHAT IT MEASURES
  The ITI is implemented as a time.sleep() call in cage_runner.py on the PC,
  followed by a new TCP command to the Pi. This measures: how accurately does
  the ITI execute, including network overhead?

HARDWARE SETUP
  - Scope CH1: probe LED center (BCM 19, physical 35)
  - The LED turns on at the start of each new trial's initial state.
  - Measure: time from LED falling edge (end of trial) to next LED rising
    edge (start of next trial) = actual ITI.

TRIAL DEFINITION
  Use bench_fsm_latency with base_iti_s = 1.0 and a very short trial
  (the beam break immediately ends the trial). This gives clean ITI pulses.

OSCILLOSCOPE SETTINGS
  - Timebase: 500 ms/div (for 1 s ITI — gives ~5 s window to see 2 ITIs)
  - Measure period or time between pulses

WHAT TO REPORT
  - Mean ITI vs. programmed ITI
  - Std deviation (dominated by network round-trip, not Pi-side timing)
  - This sets the floor on how precisely you can control session pacing


================================================================================
SUMMARY TABLE: All Measurements at a Glance
================================================================================

  #   | Measurement                        | Probe CH1          | Probe CH2         | N samples
  ----|------------------------------------|--------------------|-------------------|----------
  1   | FSM transition latency             | Beam center (BCM3) | LED center (BCM19)| 500+
  2   | Timeout jitter                     | LED center (BCM19) | —                 | 500+
  3   | Hold timer accuracy                | Beam center (BCM3) | LED center (BCM19)| 300+
  4   | Audio onset latency                | LED left   (BCM13) | Audio jack        | 200+
  5   | Click ICI distribution             | Audio jack         | —                 | 1 recording
  6   | Valve duration precision           | Valve left (BCM0)  | —                 | 300+
  7   | Audio-LED synchronisation          | LED left   (BCM13) | Audio jack        | 200+
  8   | Camera-GPIO timestamp sync         | LED center (BCM19) | (camera + software)| 100+
  9   | Latency under load (repeat 1,2,4)  | same as above      | same as above     | 500+ each
  10  | TCP command latency                | LED center (BCM19) | (PC log timestamp)| 200+
  11  | SCHED_FIFO effect (repeat 1)       | Beam center (BCM3) | LED center (BCM19)| 500+ x2
  12  | ITI precision                      | LED center (BCM19) | —                 | 200+


================================================================================
PRACTICAL TIPS
================================================================================

PROBE CONNECTIONS
  - The Pi GPIO header has 3.3 V logic. Use 10x probe attenuation.
  - Add a short (10 cm) ground lead from scope GND clip to Pi physical pin 6
    or any GND pin. Long ground leads introduce noise at this voltage level.
  - If you see noisy signals: the beam sensor is active-low with a pull-up
    resistor inside the Pi. You may see a clean TTL edge or a slightly slow
    edge (~1 µs rise time) — both are fine for ms-scale measurements.

COLLECTING STATISTICS WITHOUT MANUALLY READING EACH VALUE
  - Most bench scopes (Rigol DS1054Z, Siglent SDS1104X-E, Keysight DSOX1204G)
    have a Statistics mode under Measure → Statistics. Enable it, set it to
    accumulate. Walk away and let it run for 10 minutes to collect 500+ samples
    automatically. Then photograph the statistics screen.
  - Alternatively: use the scope's USB data export to save waveform CSV files
    and write a short Python script to extract Δt values.

TRIGGERING ON BEAM BREAKS
  - The beam sensor is active-LOW and has 1 ms software debounce. On the scope,
    you will see a clean falling edge on beam break. Set trigger to
    falling edge, ~1.5 V threshold to capture the first edge cleanly.

SCOPE TIME REFERENCE
  - For Measurements 8 and 10 where you need an absolute time reference,
    use the scope's internal timebase and read the delta from the waveform
    directly. You do not need wall-clock synchronisation between the scope and
    the Pi for relative Δt measurements.

RECOMMENDED ORDER
  Do measurements in this order on a single afternoon:
  1. First: Measurement 1 (FSM latency) — this is the main result.
  2. Then: Measurement 2 (timeout jitter) — same probe setup, just change
     the trial definition.
  3. Then: Measurement 4 + 7 (audio latency + LED sync) — re-probe CH1 to
     LED left, add audio jack probe to CH2. Takes 15 min to set up.
  4. Then: Measurement 6 (valve) — move CH1 probe to valve pin.
  5. Finally: Measurement 9 (load test) — repeat 1+2+4 with 12 cages running.
  6. Measurements 3, 10, 11, 12: secondary, do on a second session if time allows.
