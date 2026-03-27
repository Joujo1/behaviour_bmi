---
name: Project context — animal behaviour experiment
description: Core research purpose and data requirements for the BMI closed-loop system
type: project
---

This is an animal behaviour research system. Every sensor event that occurs during a trial must be captured and timestamped — including IR events on sensors that are not the "target" for the current state (e.g. rat goes left when it should go center). All raw hardware data is scientific data.

**Why:** Behaviour analysis requires the complete record, not just the events that drove state transitions.

**How to apply:** gpio_handler monitors all IR sensors for the entire trial duration with both edges (entry and exit). Every edge fires a callback to the engine which always logs it, then separately decides whether to act on it for state machine logic.
