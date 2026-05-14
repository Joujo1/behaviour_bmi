# FSM Latency Optimization — Complete Reference

**Goal:** Reduce beam-break → LED-write round-trip from ~3 ms to as low as possible.  
**Result:** ~200 µs measured on scope (Ch1 = beam falling edge, Ch2 = LED rising edge).  
**Hardware:** Raspberry Pi 4 (BCM2711), PREEMPT_RT kernel.

---

## Baseline (before any changes)

```
GPIO edge → pigpiod DMA ring buffer (1µs polling)
  → notification pipe → Python pigpio callback thread
  → queue.put() → FSM thread wakeup + GIL acquisition
  → _handle_beam() → transition_to() → enter_state()
  → _dispatch_action() → _pi.write() → Unix socket → pigpiod
  → GPIO register write
```

| Segment | Cost |
|---|---|
| pigpiod input notification (DMA → Python callback) | ~200–500 µs |
| `queue.put()` → FSM thread wakeup + GIL | **~1.5–2 ms** (dominant) |
| FSM state lookup + dispatch | ~10 µs |
| `_pi.write()` via pigpiod Unix socket | ~200 µs |
| **Total** | **~3 ms** |

---

## Changes — overview

| # | Change | File(s) | Saves |
|---|---|---|---|
| 1 | Migrate pigpiod → gpiod v2 kernel interrupts | `gpio_handler.py` | ~300–500 µs |
| 2 | Direct `/dev/gpiomem` mmap GPIO writes | `gpio_handler.py` | ~200 µs/write |
| 3 | Fast-path callback — bypass the FSM queue for LED/valve | `gpio_handler.py`, `engine.py` | ~1.5–2 ms |
| 4 | Hold-timer fast-path — same bypass on hold expiry | `engine.py` | same |
| 5 | SCHED_FIFO RT threads (gpiod monitor prio 75, FSM prio 70) | `gpio_handler.py`, `engine.py` | ~100–200 µs |
| 6 | CPU core isolation (core 3 dedicated to RT tasks) | kernel cmdline | ~50–100 µs |
| 7 | Python GIL check interval 5 ms → 100 µs | `main.py` | ~50 µs |
| 8 | Remove kernel RT throttle (`sched_rt_runtime_us = -1`) | `main.py`, sysctl | eliminates 50 ms stalls |
| 9 | `mlockall(MCL_CURRENT\|MCL_FUTURE)` | `main.py` | removes page-fault spikes |
| 10 | CPU `performance` frequency governor | systemd service | removes freq-scaling spikes |
| 11 | Software fan PWM (pigpiod hardware PWM replaced) | `gpio_handler.py` | prerequisite for #1 |
| 12 | Eliminate pigpiod completely | all files | prerequisite for #1 |

---

## Change 1 — Migrate from pigpiod to gpiod v2

### Why pigpiod was the bottleneck

pigpiod monitors GPIO inputs by polling a DMA ring buffer every 1 µs, detects an edge, then sends a notification through a Unix socket pipe to the Python process. That notification pipeline has an irreducible floor of ~300–500 µs even with PREEMPT_RT, because:
- DMA ring: up to 1 µs polling latency
- Unix socket: context switch + pipe drain
- pigpio alert thread wakeup in Python

In addition, pigpiod conflicts with gpiod when both attempt to manage the same GPIO hardware registers simultaneously — having both running caused trials to fail entirely.

### What gpiod v2 does instead

The kernel GPIO character device (`/dev/gpiochip0`) delivers edge events via hardware interrupt → kernel GPIO subsystem → file descriptor readable event. `select()` on that fd wakes the Python monitor thread within the interrupt service latency (~tens of µs on PREEMPT_RT). There is no DMA ring buffer and no IPC hop.

### gpio_handler.py — complete rewrite

**Before (pigpiod v1 style):**
```python
import pigpio
_pi = pigpio.pi()
# setup output
_pi.set_mode(pin, pigpio.OUTPUT)
# write output
_pi.write(pin, 1)
# monitor input
_pi.callback(pin, pigpio.EITHER_EDGE, handler)
# handler timestamp
tick → _tick_to_mono(tick)  # DMA timestamp, offset-corrected
```

**After (gpiod v2):**
```python
import gpiod
from gpiod.line import Bias, Direction, Edge, Value

# setup all outputs — single request object for all pins
_gpiod_out_req = gpiod.request_lines(
    '/dev/gpiochip0',
    consumer='bmi-out',
    config={pin: gpiod.LineSettings(direction=Direction.OUTPUT,
                                    output_value=Value.INACTIVE)
            for pin in output_pins},
)

# setup all beam inputs with edge detection — single request object
_gpiod_in_req = gpiod.request_lines(
    '/dev/gpiochip0',
    consumer='bmi-beam',
    config={pin: gpiod.LineSettings(direction=Direction.INPUT,
                                    edge_detection=Edge.BOTH,
                                    bias=Bias.PULL_UP)   # or PULL_DOWN
            for tgt, pin in BEAM_PINS.items()},
)

# monitor thread: single fd, read_edge_events() returns a list
fd = _gpiod_in_req.fd
ready = select.select([fd], [], [], 0.1)[0]
for ev in _gpiod_in_req.read_edge_events():
    pin    = ev.line_offset                    # which beam sensor
    t_mono = ev.timestamp_ns / 1e9            # CLOCK_MONOTONIC seconds
    is_falling = ev.event_type.name == 'FALLING_EDGE'
```

**Key gpiod v1 → v2 API changes:**

| v1 | v2 |
|---|---|
| `gpiod.Chip('gpiochip0')` | `gpiod.request_lines('/dev/gpiochip0', ...)` |
| `chip.get_line(pin)` | — (no per-line objects in v2) |
| `line.request(consumer, type, flags)` | `gpiod.LineSettings(direction=, edge_detection=, bias=)` |
| `line.set_value(1/0)` | `request.set_value(pin, Value.ACTIVE/INACTIVE)` |
| `line.get_value()` | `request.get_value(pin)` |
| `line.event_get_fd()` (per line) | `request.fd` (one fd for all lines in request) |
| `line.event_read()` → `ev.sec, ev.nsec, ev.type` | `request.read_edge_events()` → `ev.line_offset, ev.timestamp_ns, ev.event_type.name` |
| `gpiod.LINE_REQ_FLAG_BIAS_PULL_UP` | `Bias.PULL_UP` |
| `gpiod.LINE_REQ_EV_BOTH_EDGES` | `edge_detection=Edge.BOTH` |
| `gpiod.LineEvent.FALLING_EDGE` | `ev.event_type.name == 'FALLING_EDGE'` |

**Timestamp alignment:** `ev.timestamp_ns / 1e9` uses `CLOCK_MONOTONIC` by default (gpiod v2 `LineSettings.event_clock` defaults to `Clock.MONOTONIC`). This matches `time.clock_gettime(time.CLOCK_MONOTONIC)` used for `_trial_start` in engine.py — so `t = t_mono - _trial_start` is always on the same clock.

**Removing pigpiod from the Pi:**
```bash
sudo systemctl stop pigpiod
sudo systemctl disable pigpiod
```

---

## Change 2 — Direct `/dev/gpiomem` mmap for output writes

On BCM2711 (Pi 4), `/dev/gpiomem` exposes the GPIO peripheral registers directly. Writing `GPSET0`/`GPCLR0` is a single `struct.pack_into` call — ~1 µs — with no system call, no IPC, no kernel context switch.

Previously each output write went: Python → Unix socket → pigpiod process → GPIO register (~200 µs round-trip).

**In `gpio_handler.py`:**
```python
_gpio_mem: mmap.mmap | None = None
_GPSET0 = 0x1C   # byte offset — set  pins 0–31 (write 1-bits to set)
_GPCLR0 = 0x28   # byte offset — clear pins 0–31 (write 1-bits to clear)
_GPLEV0 = 0x34   # byte offset — read  pins 0–31

def _init_fast_gpio() -> None:
    fd = os.open('/dev/gpiomem', os.O_RDWR | os.O_SYNC)
    _gpio_mem = mmap.mmap(fd, 256, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
    os.close(fd)

def _drive(pin: int, state: bool) -> None:
    struct.pack_into('I', _gpio_mem, _GPSET0 if state else _GPCLR0, 1 << pin)
    # fallback: _gpiod_out_req.set_value(pin, Value.ACTIVE if state else Value.INACTIVE)
```

GPSET0 and GPCLR0 are bit-mask write-only registers — setting a bit sets or clears the corresponding GPIO pin. No read-modify-write, no race hazard. Concurrent writes from multiple threads to different pins are safe.

All output pins (LEDs 13/19/26, valves 0/5, audio 9/10, fan 8, strip 25) are within BCM 0–31, so one register covers everything.

---

## Change 3 — Fast-path callback (eliminates the queue/thread hop)

The dominant cost (~1.5–2 ms) was: callback thread posts event to `queue.Queue` → FSM thread wakes up, acquires GIL, dequeues, runs `enter_state()`, which calls `_dispatch_action()`, which calls `gpio_handler.set_led()`.

**Solution:** Execute the LED/valve writes *directly in the gpiod monitor thread* (SCHED_FIFO 75) before even posting to the queue. The FSM thread then re-executes the same writes later (idempotent — writing the same GPIO value twice is a hardware no-op).

### `gpio_handler.py` — `fast_reaction` hook

```python
_fast_reaction_fn = None   # set by start_monitoring()

def start_monitoring(on_event, fast_reaction=None) -> None:
    global _fast_reaction_fn
    _fast_reaction_fn = fast_reaction
    ...

def _gpiod_monitor(on_event) -> None:
    ...
    for ev in req.read_edge_events():
        ...
        if _fast_reaction_fn is not None:
            _fast_reaction_fn(target, is_active)   # ← fires BEFORE queue post
        on_event(target, is_active, t_mono)         # ← posts to FSM queue
```

### `engine.py` — fast table and reaction

**`_build_fast_table()`** — called once per `load()`. Precomputes:
```
(state_id, beam_target) → [list of action dicts (led_on/led_off/valve_open/valve_close)]
```
for every zero-hold `beam_break` transition. Exit actions of the current state and entry actions of the next state are both included. `play_clicks` is excluded (needs its own thread). `hold_ms > 0` transitions are excluded (they must wait for the hold to complete).

**`_fast_reaction(target, is_active)`** — registered as `fast_reaction` with `start_monitoring()`:
```python
def _fast_reaction(self, target: str, is_active: bool) -> None:
    if not is_active:
        return
    state_id = self._current_state_id   # GIL-atomic read in CPython
    if state_id is None:
        return
    fast_acts = self._fast_table.get((state_id, target))
    if fast_acts:
        self._fast_execute(fast_acts)
```

**`_fast_execute(actions_list)`:**
```python
def _fast_execute(self, actions_list: list) -> None:
    for act in actions_list:
        atype = act['type']
        tgt   = act.get('target')
        if   atype == 'led_on':      gpio_handler.set_led(tgt, True)
        elif atype == 'led_off':     gpio_handler.set_led(tgt, False)
        elif atype == 'valve_open':  gpio_handler.set_valve(tgt, True)
        elif atype == 'valve_close': gpio_handler.set_valve(tgt, False)
```

**Correctness:** `_current_state_id` is a single Python object reference; reads are GIL-atomic in CPython. The FSM thread is the sole writer. The fast reaction never touches state machine state — it only calls the same GPIO functions the FSM would call, so the re-execution is a harmless no-op.

---

## Change 4 — Hold-timer fast-path

For transitions with `hold_ms > 0`, the beam sensor must be held active for `hold_ms` milliseconds before the transition fires. The hold timer callback (`_on_hold_complete`) previously only posted to the FSM queue — so the LED write waited for the queue hop after the hold expired.

**Fix in `engine.py`:** Call `_fast_execute_transition()` directly in the timer callback before posting to the queue:

```python
def _on_hold_complete(self, target: str, next_state: str, expected_state: str) -> None:
    if self._current_state_id == expected_state:
        self._fast_execute_transition(expected_state, next_state)   # ← immediate write
    self._event_queue.put(('hold', target, next_state, expected_state))

def _fast_execute_transition(self, from_state_id: str, to_state_id: str) -> None:
    _FAST_TYPES = frozenset(('led_on', 'led_off', 'valve_open', 'valve_close'))
    fast_acts = []
    from_state = self._states.get(from_state_id)
    if from_state:
        fast_acts += [a for a in from_state.get('exit_actions', [])
                      if a.get('type') in _FAST_TYPES]
    to_state = self._states.get(to_state_id)
    if to_state:
        fast_acts += [a for a in to_state.get('entry_actions', [])
                      if a.get('type') in _FAST_TYPES]
    self._fast_execute(fast_acts)
```

---

## Change 5 — SCHED_FIFO RT scheduling for Python threads

Both the gpiod monitor thread and the FSM thread are elevated to `SCHED_FIFO` (hard real-time) and pinned to CPU core 3.

**In `gpio_handler.py` (monitor thread, prio 75):**
```python
def _set_rt_priority(priority: int = 75) -> None:
    SCHED_FIFO = 1
    class _Param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    ctypes.CDLL("libc.so.6").sched_setscheduler(0, SCHED_FIFO, ctypes.byref(_Param(priority)))
    os.sched_setaffinity(0, {3})   # pin to isolated core 3
```

**In `engine.py` (FSM thread, prio 70):**
```python
def _set_rt_priority(priority: int = 70) -> None:
    # same implementation
    os.sched_setaffinity(0, {3})
```

Priority hierarchy: gpiod monitor (75) > FSM (70) > everything else. The monitor thread will preempt the FSM thread if both are runnable, ensuring beam events are captured with minimal jitter.

**In `systemmd.txt` (cage_controller.service):**
```ini
CPUSchedulingPolicy=fifo
CPUSchedulingPriority=70
LimitMEMLOCK=infinity
```
This gives the whole Python process SCHED_FIFO from startup, before the threads set their own priorities.

---

## Change 6 — CPU core isolation

Added to `/boot/firmware/cmdline.txt` (single line, appended to end):
```
isolcpus=3 nohz_full=3 rcu_nocbs=3 irqaffinity=0-2
```

| Parameter | Effect |
|---|---|
| `isolcpus=3` | Removes core 3 from the kernel scheduler's load-balancing pool. Normal processes are never scheduled on core 3 unless explicitly pinned there. |
| `nohz_full=3` | Disables the periodic scheduler tick (CONFIG_HZ jitter) on core 3. The core only gets interrupted when it actually needs to do scheduler work. |
| `rcu_nocbs=3` | Offloads RCU (read-copy-update) callbacks from core 3 to other cores. Eliminates a source of random ~100 µs interrupt latency. |
| `irqaffinity=0-2` | Hardware IRQs are handled on cores 0–2 only. Core 3 is not interrupted by device IRQs (network, USB, I2C, etc.). |

**Requires a reboot.** Verify after reboot:
```bash
# The Python process's RT threads should show cpu=3
grep Cpus_allowed_list /proc/$(pgrep -f main.py)/status
```

The gpiod monitor thread and FSM thread both call `os.sched_setaffinity(0, {3})` to pin themselves to core 3 after the OS grants it via `isolcpus`.

---

## Change 7 — Python GIL check interval

Added to `main.py` at module level (before any threads start):
```python
sys.setswitchinterval(0.0001)   # 100 µs, down from default 5 ms
```

The GIL check interval is how often CPython checks whether another thread wants the GIL. The default 5 ms means a thread that just woke from a kernel interrupt (the gpiod monitor) could wait up to 5 ms for the GIL if another thread is running Python bytecode. Reducing to 100 µs cuts this worst-case to 100 µs.

---

## Change 8 — Remove kernel RT throttle

Added to `main.py` at module level:
```python
try:
    with open('/proc/sys/kernel/sched_rt_runtime_us', 'w') as _f:
        _f.write('-1\n')
except OSError:
    pass
```

The Linux kernel defaults to `sched_rt_runtime_us = 950000` and `sched_rt_period_us = 1000000` — meaning SCHED_FIFO tasks are throttled to 95% CPU time, and the kernel forces a ~50 ms stall every second to prevent RT tasks from starving normal tasks. Writing `-1` removes this cap entirely.

This is also set persistently in `/etc/sysctl.d/99-rt.conf`:
```
kernel.sched_rt_runtime_us = -1
```
Apply without reboot:
```bash
sudo sysctl -p /etc/sysctl.d/99-rt.conf
```

Without this, the RT threads would stall for ~50 ms every second regardless of all other optimizations.

---

## Change 9 — Memory locking (`mlockall`)

Added to `main.py` at module level:
```python
_libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
_libc.mlockall(ctypes.c_int(3))   # MCL_CURRENT=1 | MCL_FUTURE=2
```

`mlockall(MCL_CURRENT | MCL_FUTURE)` pins all current and future memory pages into RAM, preventing them from being swapped out. Without this, the first access to a page that was swapped out causes a page fault — which can stall a thread for hundreds of µs or more. The `LimitMEMLOCK=infinity` in the systemd service file grants the process permission to lock unlimited memory.

---

## Change 10 — CPU performance frequency governor

Added `cpu-governor.service` (see `systemmd.txt`):
```ini
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
```

The default `ondemand` or `powersave` governor scales CPU frequency down when idle and ramps it back up on load. That ramp takes ~50–200 µs. With `performance`, all cores run at maximum frequency at all times, eliminating frequency-scaling latency spikes.

---

## Change 11 — Software fan PWM

GPIO 8 (FAN_PIN) has no hardware PWM on BCM2711. Previously pigpiod provided software PWM. After eliminating pigpiod, a threading-based software PWM was implemented:

```python
_fan_pwm_stop: threading.Event = threading.Event()
_fan_pwm_thread: threading.Thread | None = None

def set_fan_pwm(duty: float, freq: float = FAN_PWM_FREQ) -> None:
    # ...
    def _pwm_loop():
        while not _fan_pwm_stop.is_set():
            _drive(FAN_PIN, True)
            _fan_pwm_stop.wait(on_time)
            if _fan_pwm_stop.is_set():
                break
            _drive(FAN_PIN, False)
            _fan_pwm_stop.wait(off_time)
        _drive(FAN_PIN, False)

    _fan_pwm_thread = threading.Thread(target=_pwm_loop, daemon=True, name='fan-pwm')
    _fan_pwm_thread.start()
```

`threading.Event.wait()` is used instead of `time.sleep()` so the thread exits cleanly and immediately when `_fan_pwm_stop.set()` is called.

---

## Change 12 — Complete pigpiod elimination

pigpiod and gpiod cannot coexist — pigpiod's DMA process writes to the same GPIO hardware registers, causing gpiod kernel interrupt setup to fail (trials would not start, LEDs would never fire). The same conflict was observed when mixing RPi.GPIO and pigpiod.

**Removed from all Python files:**
- `import pigpio`
- `_pi = pigpio.pi()` and all `_pi.*` calls
- `_pi.write()`, `_pi.set_mode()`, `_pi.callback()`
- `_tick_to_mono()` (DMA tick conversion helper)
- Tick anchor synchronization logic (`_tick_anchor`, `_mono_anchor`)
- `_gpio_cb_rt_set` flag (pigpio callback RT elevation)

**On the Pi:**
```bash
sudo systemctl stop pigpiod
sudo systemctl disable pigpiod
```

---

## File-by-file summary of changes

### `gpio_handler.py` — complete rewrite

| Section | Change |
|---|---|
| Imports | Removed `pigpio`, `time`. Added `gpiod`, `from gpiod.line import Bias, Direction, Edge, Value`. |
| Globals | Replaced `_pi`, `_gpiod_out_chip`, `_gpiod_out_lines` (per-line dict) with `_gpiod_out_req` (single LineRequest). Replaced `_gpiod_chip`, `_gpiod_fd_map` (per-line fd map) with `_gpiod_in_req` (single LineRequest) + `_pin_to_target` dict. Removed tick-anchor globals. Added `_fan_pwm_stop`, `_fan_pwm_thread`. |
| `_set_rt_priority()` | Added `os.sched_setaffinity(0, {3})` — pin to core 3. |
| `_init_fast_gpio()` | New — opens `/dev/gpiomem`, mmaps 256 bytes. |
| `_drive()` | Rewritten — mmap GPSET0/GPCLR0 primary path; gpiod v2 `set_value()` fallback. Removed pigpio path. |
| `_read_pin_level()` | Rewritten — mmap GPLEV0 primary; gpiod `get_value()` fallback for both out and in requests. |
| `setup()` | Rewritten — single `gpiod.request_lines()` call for all output pins. Removed pigpio init. |
| `cleanup()` | Rewritten — `_gpiod_out_req.release()` instead of per-line release. |
| `set_fan_pwm()` | Rewritten — software PWM thread replacing pigpiod hardware PWM. |
| `_stop_fan_pwm_thread()` | New — sets stop event, joins thread. |
| `start_monitoring()` | Rewritten — single `gpiod.request_lines()` for all beam pins; builds `_pin_to_target` reverse map; accepts `fast_reaction` callback. |
| `_gpiod_monitor()` | Rewritten — single `req.fd`, `select()`, `req.read_edge_events()`, `ev.line_offset`/`ev.timestamp_ns`/`ev.event_type.name`. |
| `stop_monitoring()` | Rewritten — `_gpiod_in_req.release()` instead of per-line release + chip close. |

### `engine.py`

| Section | Change |
|---|---|
| Imports | Added `import os`. |
| `_set_rt_priority()` | Added `os.sched_setaffinity(0, {3})`. |
| `__init__()` | Added `self._fast_table: dict = {}`. |
| `load()` | Added `self._build_fast_table()` call at end. |
| `start()` | Added `fast_reaction=self._fast_reaction if self._fast_table else None` to `start_monitoring()` call. |
| `_on_hold_complete()` | Added `self._fast_execute_transition()` call before queue post. |
| `_build_fast_table()` | New method — precomputes `(state_id, target) → [action_dicts]`. |
| `_fast_reaction()` | New method — GIL-atomic state read, fast table lookup, immediate GPIO write. |
| `_fast_execute_transition()` | New method — collects exit+entry actions for a state pair, calls `_fast_execute()`. |
| `_fast_execute()` | New method — directly calls `gpio_handler.set_led/set_valve`. |
| Docstring | Updated timestamp reference from `ev.sec + ev.nsec` (v1) to `ev.timestamp_ns / 1e9` (v2). |

### `main.py`

| Section | Change |
|---|---|
| Imports | Added `ctypes`, `ctypes.util`, `os`. |
| Module level | Added `sys.setswitchinterval(0.0001)`. |
| Module level | Added RT throttle removal (`/proc/sys/kernel/sched_rt_runtime_us = -1`). |
| Module level | Added `mlockall(MCL_CURRENT \| MCL_FUTURE)` via ctypes. |
| Comments | Updated "pigpio callback" → "gpiod monitor" in two places. |

### `systemmd.txt`

| Section | Change |
|---|---|
| Removed | Full `pigpiod.service` block. |
| `cage_controller.service` | Added `CPUSchedulingPolicy=fifo`, `CPUSchedulingPriority=70`, `LimitMEMLOCK=infinity`. Removed `After=pigpiod.service`, `Wants=pigpiod.service`. |
| Added | `cpu-governor.service` — sets `performance` cpufreq governor at boot. |
| Added | sysctl RT tuning section — `kernel.sched_rt_runtime_us = -1` in `/etc/sysctl.d/99-rt.conf`. |
| Setup steps | Renumbered; removed all pigpiod steps; added Step 7 for migrating from pigpiod. |
| Useful commands | Removed `systemctl status pigpiod`, `ps -eo ... grep pigpiod`. Added core isolation verification. |

---

## Latency after all changes

| Source | Before | After |
|---|---|---|
| GPIO interrupt → Python callback | ~300–500 µs (pigpiod DMA + pipe) | ~30–80 µs (kernel interrupt + poll) |
| Queue/thread hop | ~1.5–2 ms | **0 µs (eliminated by fast-path)** |
| GPIO output write | ~200 µs (pigpiod socket) | **~1 µs (mmap GPSET0/GPCLR0)** |
| RT throttle stalls | up to 50 ms/s | **0 (sched_rt_runtime_us = -1)** |
| **Total measured** | **~3 ms** | **~200 µs** |

**~15× improvement.**

The remaining ~200 µs is composed of:
- Kernel interrupt service + `poll()` wakeup: ~20–60 µs (PREEMPT_RT floor)
- GIL acquisition by the monitor thread: ~10–100 µs (bounded by `setswitchinterval(0.0001)`)
- `_fast_reaction()` execution + mmap write: ~2–5 µs

---

## Deployment checklist

```bash
# 1. Stop and disable pigpiod (if previously used)
sudo systemctl stop pigpiod
sudo systemctl disable pigpiod

# 2. Install python3-gpiod (v2)
sudo apt install python3-gpiod

# 3. Deploy updated service files
sudo nano /etc/systemd/system/cage_controller.service   # paste from systemmd.txt
sudo nano /etc/systemd/system/cpu-governor.service      # paste from systemmd.txt

# 4. Create RT sysctl config
sudo nano /etc/sysctl.d/99-rt.conf
# add line: kernel.sched_rt_runtime_us = -1
sudo sysctl -p /etc/sysctl.d/99-rt.conf

# 5. Reload systemd and start services
sudo systemctl daemon-reload
sudo systemctl enable cpu-governor.service
sudo systemctl start cpu-governor.service
sudo systemctl enable cage_controller.service
sudo systemctl restart cage_controller.service

# 6. Enable CPU core isolation (requires reboot)
sudo nano /boot/firmware/cmdline.txt
# Append to the SINGLE existing line (no newline):
#   isolcpus=3 nohz_full=3 rcu_nocbs=3 irqaffinity=0-2
sudo reboot

# 7. Verify
cat /proc/sys/kernel/sched_rt_runtime_us        # should be -1
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor  # should all be 'performance'
grep Cpus_allowed_list /proc/$(pgrep -f main.py)/status    # should show core 3
journalctl -u cage_controller.service -f         # check for errors
```
