# Drain output clamp witnesses

The candidate source is byte-bound to the build receipt used by the full drain refinement captures. The reviewer replays the retained event and peak diagnostics and checks their manifests and full-assessment identities.

For all eight data-line peak witnesses, each four-callback bus group has a common HDL time and analog entry time. The three following callbacks report a target exactly equal to max(HDL time, entry time), matching the source clamp. The signed delivery offsets explain the interpolated crossing offsets to within 2.346 fs across the three inspected thresholds. This localizes a timing mechanism; it does not prove causal sufficiency or justify removing the clamp, which prevents returning before analog entry time.

The audit lacks callback-handle state, output values and input-threshold history. A fresh instrumented candidate must expose those boundaries before attempting a correction. WR has no threshold crossings in its retained peak windows and is not covered by this correlation. The original convergence gate remains failed.

Replay:

```sh
python3 verification/robotron-keyboard/analog/postreset_drain_clamp.py --root verification/robotron-keyboard/analog/reports/postreset-drain-clamp --check
python3 -m unittest discover -s verification/robotron-keyboard/analog -p test_postreset_drain_clamp.py
```
