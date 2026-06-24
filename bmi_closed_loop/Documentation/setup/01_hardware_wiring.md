# Wiring and Setting Up All Hardware

The cage hardware is built around the Raspberry Pi's 40-pin GPIO header and a custom PCB that carries all peripheral connections. The schematic below shows the full layout.

![Wiring schematic](../architecture/img/Schematic%20bsc_Steckplatine.png)

---

## Overview

The PCB has two sides. One side connects to the Raspberry Pi via a **ribbon cable** attached to the 40-pin GPIO header. The other side carries the **ItsyBitsy M4 Express** as an additional audio peripheral.

All beam-break sensors, LEDs, solenoid valves, the fan, and the strip light connect to the PCB, which routes signals to the correct Pi GPIO pins.

The ItsyBitsy M4 receives TTL trigger pulses from the Pi (left audio = BCM GPIO 9, right audio = BCM GPIO 10) and plays back the pre-programmed click waveform on the corresponding speaker channel whenever a pulse arrives. For flashing new firmware to the ItsyBitsy, see [setup/04_itsybitsy_mcu.md](04_itsybitsy_mcu.md).

---

## GPIO pin summary

| Function | BCM Pin | Direction |
|---|---|---|
| Beam left | 2 | Input |
| Beam center | 3 | Input |
| Beam right | 4 | Input |
| Valve left | 0 | Output |
| Valve right | 5 | Output |
| Audio left (ItsyBitsy trigger) | 9 | Output |
| Audio right (ItsyBitsy trigger) | 10 | Output |
| Fan | 8 | Output (PWM) |
| LED left | 13 | Output |
| LED center | 19 | Output |
| LED right | 26 | Output |
| Strip light | 25 | Output |

All of these are defined in [RPi_main/config.py](../../RPi_main/config.py) and should not be changed without also updating the PCB wiring.
