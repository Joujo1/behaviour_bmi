# Config Files

There are two config files — one per layer. Neither file is imported across the layer boundary; constants are duplicated deliberately to keep the layers independent.

---

## Pi-side: `RPi_main/config.py`

Source: [RPi_main/config.py](../../RPi_main/config.py)

### Camera

| Constant | Default | Description |
|---|---|---|
| `CAMERA_FPS` | `60` | Camera capture and encode frame rate. |
| `CAMERA_WIDTH` | `480` | Frame width in pixels. |
| `CAMERA_HEIGHT` | `320` | Frame height in pixels. |
| `CAMERA_BITRATE` | `2_000_000` | H264 encoder target bitrate (bits/sec). |
| `CAMERA_H264_IPERIOD` | `60` | Keyframe interval in frames (1 keyframe/sec at 60 fps). |
| `CAMERA_EXPOSURE_US` | `6000` | Shutter time in microseconds. |
| `CAMERA_GAIN` | `4.0` | Analogue gain. |

### Click stimulus

| Constant | Default | Description |
|---|---|---|
| `CLICK_PULSE_US` | `50` | Width of the TTL pulse sent to the ItsyBitsy per click (microseconds). |
| `CLICK_WIDTH_S` | `0.003` | Duration of one click waveform in seconds. Used to set the minimum inter-click interval. Must match `CLICK_WIDTH_S` in `bmi_closed_loop/config.py`. |
| `AUDIO_SRATE` | `48_000` | ItsyBitsy audio sample rate (Hz). Informational only — not used in Python. |

### Runtime

| Constant | Default | Description |
|---|---|---|
| `FRAME_QUEUE_MAXSIZE` | `30` | Maximum frames buffered between camera and UDP sender before drops occur. |
| `TRIAL_WATCHDOG_S` | `1200` | Hard maximum trial duration (seconds). Engine aborts if exceeded. |

### GPIO pins (BCM numbering)

| Group | Constant | Pins |
|---|---|---|
| LEDs | `LED_PINS` | left=13, center=19, right=26 |
| Valves | `VALVE_PINS` | left=0, right=5 |
| Beam sensors | `BEAM_PINS` | left=2, center=3, right=4 |
| Audio triggers | `AUDIO_PINS` | left=9, right=10 |
| Fan | `FAN_PIN` | 8 |
| Strip light | `STRIP_PIN` | 25 |

| Constant | Default | Description |
|---|---|---|
| `BEAM_ACTIVE_LOW` | all `True` | Whether a beam break is a falling edge (True) or rising edge (False) per sensor. |
| `FAN_PWM_FREQ` | `200` | Software PWM frequency for the fan (Hz). |
| `FAN_MIN_DUTY` | `30` | Minimum duty cycle when fan is running (percent). Below this the fan stalls. |

---

## PC-side: `bmi_closed_loop/config.py`

Source: [config.py](../../config.py)

### Networking

| Constant | Default | Description |
|---|---|---|
| `N_CAGES` | `12` | Number of cages in the rig. Determines how many Pi connections and UI cards are created. |
| `UDP_BASE_PORT` | `5000` | Base UDP port. Cage N receives on port `5000 + N`. |
| `PI_IPS` | auto-generated | Dict mapping cage ID → IP. Default: cage 1 = `192.168.1.101`, cage 12 = `192.168.1.112`. |
| `TCP_COMMAND_PORT` | `6000` | TCP port used for all cage command connections. |
| `FLASK_HOST` | `"0.0.0.0"` | Flask bind address. |
| `FLASK_PORT` | `5000` | Flask HTTP port. |

### Valkey

| Constant | Default | Description |
|---|---|---|
| `VALKEY_HOST` | `"localhost"` | Valkey server host. |
| `VALKEY_PORT` | `6379` | Valkey server port. |
| `VALKEY_FRAME_TTL_SECONDS` | `5` | TTL for `cage:{id}:latest_frame` key. Frames older than this are auto-deleted. |

### Database

| Constant | Default | Description |
|---|---|---|
| `POSTGRES_DSN` | `"postgresql://bmi:yaniklab@localhost/bmi_closed_loop"` | Full PostgreSQL connection string. |
| `DB_CHUNK_SIZE` | `1000` | Frames per `recordings` row. A new row is flushed to Postgres every 1000 frames. |

### File paths

| Constant | Default | Description |
|---|---|---|
| `NAS_BASE_PATH` | `/home/sentinel/Desktop/bmi/…/NAS` | Root directory for raw frame `.bin` files. |
| `LOGGING_DIR` | `/home/sentinel/Desktop/bmi/…/logs` | Directory for PC-side log files. Overridable via `BMI_LOG_DIR` environment variable. |
| `LOGGING_LEVEL` | `"INFO"` | Log level for all PC-side loggers. |
| `SCORESHEET_TEMPLATE_PATH` | `/home/sentinel/…/Scoresheet_Sample.xlsx` | Path to the welfare scoresheet Excel template. |

### Timing

| Constant | Default | Description |
|---|---|---|
| `WATCHDOG_INTERVAL_SECONDS` | `1` | How often the PC watchdog checks for dead Pi connections. |
| `WATCHDOG_DEAD_THRESHOLD_SECONDS` | `10` | If no frame is received for this long, the cage is marked dead. |
| `RECORDING_CHECK_INTERVAL_S` | `1.0` | How often `FrameWriter` checks the Valkey recording flag. |
| `TRIAL_TIMEOUT_S` | `1230` | PC-side hard trial timeout (slightly longer than the Pi's watchdog). |
| `FRAME_QUEUE_MAXSIZE` | `60` | Per-cage frame queue depth on the PC side. |
| `CLICK_WIDTH_S` | `0.003` | Must match `CLICK_WIDTH_S` in `RPi_main/config.py`. |
| `FAN_MIN_DUTY` | `30` | Minimum fan duty used by the UI fan control. |
