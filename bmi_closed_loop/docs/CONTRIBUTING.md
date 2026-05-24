# Contributing — behaviour_bmi

Coding standards and conventions for this codebase. The short version lives
in `CLAUDE.md` at the repo root; this document has the rationale and
extended examples.

---

## Guiding principle

Code in this project runs real-time hardware loops on a Raspberry Pi and
drives neural recording experiments. Clarity and correctness matter more
than cleverness. When in doubt, write the straightforward thing.

---

## Module structure

Every Python file follows this layout:

```python
"""
Module docstring — one paragraph.

Explain the module's role, key contracts, and anything that would surprise
a reader. Include protocol specs or wire formats where relevant.
"""

# Standard library
import os
import threading

# Third-party
import flask

# Local
import config
from shared.logger import get_logger

logger = logging.getLogger(__name__)
```

The `logger` line always comes right after imports, before any other code.
Import groups are separated by one blank line; no blank line within a group.

---

## Naming

Every name should communicate its purpose without requiring the reader to
look at the implementation. Ask: "could someone misread what this is for?"
If yes, rename it.

**Abbreviations**: only when unambiguous in context (`ip`, `fps`, `tcp`,
`udp`, `gpio`). Avoid all other abbreviations.

**Single-letter variables**: only in trivially obvious comprehensions
(`[x * 2 for x in values]`). Never in loop bodies, callbacks, or anywhere
a reader might need to track what it is.

Examples of the standard:

```python
# good
for cage_id in range(1, config.N_CAGES + 1):
    listener = UDPreceiver(port, callback)

# bad — l is ambiguous, abbreviation obscures meaning
for l in listeners:
    l.stop()
```

---

## Type hints

All function and method **signatures** get full type hints. Do not annotate
variable declarations inside function bodies — the reader can infer them,
and the annotations add noise without adding information.

```python
# correct
def write_frame(self, frame: Frame) -> None:
    header = struct.pack(">IId", frame.cage_id, frame.seq, frame.timestamp)

# wrong — body annotation adds nothing
def write_frame(self, frame: Frame) -> None:
    header: bytes = struct.pack(">IId", frame.cage_id, frame.seq, frame.timestamp)
```

Use Python 3.10+ syntax throughout:
- `X | None` not `Optional[X]`
- `list[X]` not `List[X]`
- `dict[K, V]` not `Dict[K, V]`
- `tuple[X, Y]` not `Tuple[X, Y]`

---

## Docstrings — Google style

### When to write one

| Code | Rule |
|---|---|
| Module | Always |
| Public class | Always (at minimum one line) |
| Public function / method | Always |
| Private function / method | Only if behavior is non-obvious |
| `__init__` with non-trivial params | Document params in the class docstring |

### Format

One-liner when name + signature are fully self-explanatory:

```python
def cancel_timeout(self) -> None:
    """Cancel the running state timeout timer."""
```

Full Google style when args or behavior need explanation:

```python
def pop_frame_events(self, frame_ts_us: int | None) -> tuple[str | None, list]:
    """Return events whose timestamp <= frame_ts_us; hold the rest for later.

    Called from the picamera2 encoder thread. Passing None drains everything
    (used when no trial is active).

    Args:
        frame_ts_us: Frame timestamp in microseconds (CLOCK_MONOTONIC epoch).
            Pass None to drain all buffered events unconditionally.

    Returns:
        Tuple of (current_state_id, list_of_events).
    """
```

Use `Args:`, `Returns:`, `Raises:` sections. Never `:param x:` Sphinx style.
Never document what is already obvious from the name and type hints.

---

## Inline comments — WHY only

A comment should answer "why does this code exist / why is it written this
way?" — not "what does it do?" (the code already says that).

Write a comment when:
- There is a hardware constraint that forced a non-obvious choice
- There is an RT-timing or thread-safety invariant the reader must know
- The code works around a specific OS/library/kernel behaviour
- A value was arrived at empirically (e.g. a tuned threshold)

```python
# correct — explains a latency constraint that isn't obvious from the code
sys.setswitchinterval(0.0001)  # 100µs: gpiod thread acquires GIL faster after beam-break

# correct — explains why -1 is safe and what it overrides
with open('/proc/sys/kernel/sched_rt_runtime_us', 'w') as f:
    f.write('-1\n')  # remove the 95% RT throttle; gives RT tasks unlimited CPU

# wrong — restates what the code obviously does
sys.setswitchinterval(0.0001)  # set the switch interval
```

---

## Logging

Always use the standard library logger, named `logger`, at module level:

```python
logger = logging.getLogger(__name__)
```

Never use `log`, never use a custom wrapper at call sites, never create a
logger inside a function.

Use `%`-style format strings in every log call — never f-strings. The
logging module is lazy: the string is only interpolated if the message
is actually emitted. This matters in high-frequency paths.

```python
# correct
logger.info("Cage %d: %d frame(s) missing (expected %d, got %d)", cage_id, gap, expected, actual)

# wrong
logger.info(f"Cage {cage_id}: {gap} frame(s) missing")
```

### Levels

| Level | When to use |
|---|---|
| `DEBUG` | Per-event detail, state transitions, queue depths, timing measurements |
| `INFO` | Lifecycle events: start, stop, connect, disconnect, trial begin/end |
| `WARNING` | Unexpected but recoverable: missed frame, bad packet, fallback path taken |
| `ERROR` | Failures that need operator attention |

---

## Error handling

### Hardware / network / I/O boundaries

Catch specific exception types, log with enough context to diagnose, then
either continue (if the operation is non-fatal) or re-raise:

```python
try:
    with open('/proc/sys/kernel/sched_rt_runtime_us', 'w') as f:
        f.write('-1\n')
except OSError:
    pass  # non-fatal if not root; set permanently via sysctl.d instead
```

```python
try:
    data, addr = self._socket.recvfrom(65536)
except OSError as exc:
    logger.error("UDP receive error on port %d: %s", self._port, exc)
    break
```

### Internal logic

Let it raise. Do not add `try/except` around code that "shouldn't fail" as
a defensive measure. Trust invariants and let bugs surface as exceptions with
clear tracebacks rather than silently swallowing them.

Never use bare `except:` or `except Exception:` unless you immediately
re-raise or call `logger.error(..., exc_info=True)`.

---

## Config

Each layer of the system has exactly one config file that owns all tunable
values for that layer. No magic numbers in logic files — if a value needs to
change, there should be exactly one place to change it.

```
RPi_main/config.py         GPIO pin assignments, timing constants, camera params
bmi_closed_loop/config.py  Ports, file paths, cage count, Valkey address
```

If a value is shared between layers (e.g. a port number used on both Pi and
PC), it lives in the lower-level layer's config and is passed up explicitly
or replicated with a comment pointing to the source of truth.

---

## Line length and argument formatting

Keep function calls on one line unless the result is genuinely hard to read.
Do not split arguments across lines simply because there are several of them.

```python
# preferred — readable on one line
listener = UDPreceiver(port, build_frame_callback(writer, cage_id, stats), on_drop=drop_cb)

# only split when the line is too long or arguments are complex expressions
writer = FrameWriter(
    cage_id,
    session_directory,
    stats_dict=camera_stats,
    compress=config.COMPRESS_FRAMES,
)
```

The practical threshold: if it fits in ~100 characters and each argument is
readable, keep it on one line.

---

## Section dividers — large classes only

For classes with many clearly distinct groups of methods, use a minimal
section comment:

```python
# -- Public interface --

def start(self) -> None: ...
def stop(self) -> None: ...

# -- FSM thread --

def _run(self) -> None: ...
```

Do not use dividers in short classes or in modules. Do not pad with long
lines of dashes.
