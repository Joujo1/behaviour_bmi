# How Click Rates Are Calculated

Click rates define the difficulty of each trial. The trial definition specifies a `left_rate` and `right_rate` (clicks per second). The side with the higher rate is the correct side. The rat's task is to identify which side is clicking faster and poke the corresponding port.

---

## Poisson click trains

Clicks on each channel follow an independent Poisson process. Inter-click intervals are drawn from an exponential distribution:

```
ICI ~ Exp(1 / rate)
```

This means clicks are statistically independent and memoryless — knowing when the last click occurred tells you nothing about when the next one will arrive.

The generator is in [ui/click_generator.py](../../ui/click_generator.py). It takes `left_rate`, `right_rate`, `duration`, and an optional `seed`, and returns two sorted lists of click timestamps in seconds.

---

## Minimum inter-click interval

To prevent two clicks from overlapping and distorting the waveform, a minimum inter-click interval (`min_ici`) is enforced. Its default value is:

```
min_ici = 2 × CLICK_WIDTH_S = 2 × 0.003 = 6 ms
```

If a drawn ICI would place the next click closer than `min_ici` to the previous one, the click is shifted forward to `last_click_time + min_ici`. No clicks are dropped — they are only delayed.

---

## Bias correction

Before clicks are generated, the active bias algorithm (if any) may adjust the left probability for the trial. The algorithm returns a `left_probability` value in [0, 1] which controls how likely the left channel is to be the high-rate side. The actual rates assigned to left and right are then drawn based on this probability.

See [reference/04_bias_algorithms.md](../reference/04_bias_algorithms.md) for how each algorithm computes this value, and [extending/04_bias_algorithms.md](../extending/04_bias_algorithms.md) for how to add new ones.

---

## What gets stored

`CageRunner` calls `generate_clicks()` before dispatching the trial. The returned timestamp lists replace `left_rate`/`right_rate` in the trial JSON as `left_clicks` and `right_clicks`. The random seed used is stored in `trial_results` for reproducibility.

To regenerate the exact same click sequence for a given trial, see [08_regenerating_stimulus.md](08_regenerating_stimulus.md).

---

## Difficulty and ratio

The difficulty of the task is controlled by the ratio of the two rates, not their absolute values. A 80/20 split (4:1 ratio) is easy; a 52/48 split is near-chance. In the Brody lab paradigm used here, typical rate pairs span roughly 6/2 to 40/20 clicks/sec across difficulty levels.
