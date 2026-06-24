# Adding and Changing Click Waveform

The click stimulus has two separate layers: the **timing** of each click (generated on the PC and sent to the Pi) and the **waveform** played for each click (stored in the ItsyBitsy M4 audio MCU firmware). Changing the click rate statistics affects the first layer; changing the sound of each individual click affects the second.

---

## How the pipeline works

1. **PC (cage_runner.py)** calls `generate_clicks()` in [ui/click_generator.py](../../ui/click_generator.py), which returns two lists of timestamps — `left_clicks` and `right_clicks` — in seconds.

2. The timestamps are embedded in the trial JSON sent to the Pi.

3. **Pi (actions.py)** receives the trial JSON. When the `play_clicks` action fires, `_fire_click_triggers()` runs on a `SCHED_FIFO 85` thread. It busy-waits to each scheduled timestamp and drives a 50 µs TTL pulse on the corresponding audio GPIO pin (left = GPIO 9, right = GPIO 10, from [RPi_main/config.py](../../RPi_main/config.py)).

4. **ItsyBitsy M4 MCU** receives each TTL pulse and immediately plays back the pre-programmed click waveform stored in its flash.

---

## The timing generator

`generate_clicks()` in [ui/click_generator.py](../../ui/click_generator.py):

```python
def generate_clicks(left_rate, right_rate, duration, seed=None, min_ici=2*CLICK_WIDTH_S) -> dict:
```

| Parameter | Default | What it controls |
|---|---|---|
| `left_rate` | — | Mean clicks/sec for the left channel (Poisson rate) |
| `right_rate` | — | Mean clicks/sec for the right channel |
| `duration` | — | How many seconds of click train to generate |
| `seed` | `None` | RNG seed — set in the trial definition for reproducibility |
| `min_ici` | `2 × CLICK_WIDTH_S` (6 ms) | Minimum inter-click interval (start-to-start). Clicks drawn closer than this are shifted forward; none are dropped. |

`CLICK_WIDTH_S = 0.003` s (3 ms) is defined in [RPi_main/config.py](../../RPi_main/config.py).

The generator draws inter-click intervals from an exponential distribution (`ICI ~ Exp(1/rate)`). This is a Poisson process — clicks are statistically independent and memoryless.

### Changing the statistical model

To use a different click statistics model (e.g. regular, gamma-distributed, or correlated), replace `_poisson_train()` in `click_generator.py` with your own function. The return value must still be a sorted list of float timestamps in seconds.

### Changing `min_ici`

If you add a new waveform to the ItsyBitsy that is longer than 3 ms, you should increase `CLICK_WIDTH_S` in [RPi_main/config.py](../../RPi_main/config.py). The `min_ici` defaults to `2 × CLICK_WIDTH_S` so clicks never overlap and distort each other.

---

## The click waveform (ItsyBitsy firmware)

The actual audio waveform — what the click sounds like — is compiled into the ItsyBitsy M4 firmware. To change the waveform:

1. Edit the audio sample array in the ItsyBitsy firmware source (CircuitPython or C, stored in the MCU's flash).
2. Flash the updated firmware to the ItsyBitsy (see [setup/04_itsybitsy_mcu.md](../setup/04_itsybitsy_mcu.md)).
3. If the new waveform is longer than 3 ms, update `CLICK_WIDTH_S` in [RPi_main/config.py](../../RPi_main/config.py).

The Pi side does not know or care what the waveform sounds like — it only fires TTL trigger pulses at the scheduled times.

---

## Click pulse hardware parameters

| Constant | Value | Location |
|---|---|---|
| `CLICK_PULSE_US` | 50 µs | [RPi_main/config.py](../../RPi_main/config.py) |
| `CLICK_WIDTH_S` | 0.003 s (3 ms) | [RPi_main/config.py](../../RPi_main/config.py) |
| `AUDIO_SRATE` | 48,000 Hz | [RPi_main/config.py](../../RPi_main/config.py) |
| Left audio pin | GPIO 9 | [RPi_main/config.py](../../RPi_main/config.py) |
| Right audio pin | GPIO 10 | [RPi_main/config.py](../../RPi_main/config.py) |

`CLICK_PULSE_US` is the width of the TTL trigger pulse sent to the ItsyBitsy. 50 µs is sufficient for reliable detection; do not reduce it below ~10 µs without testing.
