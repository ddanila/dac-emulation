# Geometry-derived yoke: connected diagnostic render

This is an **unaccepted diagnostic**, not a healthy reference or a diagnosis of
the photographed monitor. The latest connected trial produces faint, distorted
native S550 loader text near the lower screen. No display gain, registration or
image-based yoke fitting was applied.

![Actual diagnostic frame](frame.png)

The four-field electrical solve (78 ms) took 179 seconds. Rendering the final
19.5 ms field at 480×360 took 135 seconds. Prior identical electrical fields are
assumed only to initialize phosphor excitation analytically. Electrical
periodicity is **not** established. Timings describe these runs, not guaranteed
throughput.

The frozen reduced yoke jointly derives R, L and field from the archived
[yoke profile](yoke-profile.json). The uniform-phase scan sample spans roughly
182×121 mm on the assumed 210×145 mm screen; illuminated samples span 166×9.6 mm.
The captured source contains only the loader banner and cursor. These sampled
extents are neither precise extrema nor proof of correct geometry. The reduced
field, gun, phosphor, exposure and tube geometry remain unmeasured hypotheses.

All 926 ordinary native sync edges have matching flybacks, but their relative
phase varies by **0.25394 line**, exceeding the **0.01-line** limit. EHT, G2,
G4, horizontal current and core flux also fail periodic waveform checks. See
[settling.json](settling.json). Correct edge counts alone do not establish lock.

The [local loop-response bench](loop-response-current/response.json) retains this
trial's recorded control ripple and checks finite perturbations at two resolutions.
Waveform phase changes translate PWL knots without resampling or altering their
shape. Three detector slopes pass the 1% refinement gate; the fourth changes by
**2.82%**, and the oscillator response changes by **7.66%**. **No combined phase-sign screen is usable yet.**
It therefore does not justify rejecting transformer polarities or selecting a
connected-loop winner. The earlier `loop-response/` archive records the preceding
trace and older phase-resampling method; it is superseded for screening.

At the time of this archive, interception-dependent electrode-current feedback
and a complete electrical power/storage/loss ledger were implementation gaps.
The later [accounting audit](../single-frame-accounting-audit/README.md) implements
these checks and records the current blockers. Optical kinetic
energy closure does not satisfy either requirement. No accepted experiment can
be issued from this archive.

## Numerical validation

The first optical refinement failed with 17.6% linear image error. Sampling
identified rays that reached the screen at a 200 µm spatial step but hit the
neck wall at 100 µm. The integrator had skipped the final aperture segment.
Both Python and C++ now stop at geometry boundaries and check the aperture
exit face. A regression uses an actual failing ray at four step sizes.
The `pre-boundary-fix-*` reports preserve the rejected result; they describe
older artifacts, not the current `frame.png`.

The corrected frame passes both optical checks: **0.000401%** linear image error
when halving trajectory/time steps, and **0.000158%** when doubling both image
dimensions and projecting by pixel area. No gain fitting or registration is used.
See [integration](integration-comparison.json) and
[spatial](spatial-comparison.json) reports. These do not qualify the electrical
trace or establish a physically accurate monitor.

## Replay and provenance

`run.cir` embeds the actual captured connector edges and circuit/model definitions.
`selection.json`, `metadata.json`, `solve.json`, `field-parameters.json` and
`example.json` record the input selection, frozen assumptions, timings and hashes.
`frame.f32` is little-endian float32 irradiance in W/m², row-major, 480×360.
The full raw trace and optical model/input archives remain under
`build/monitor/geometry-connected-audit`; large traces are not duplicated in git.
Consequently this compact example is evidence, not a standalone hash-complete
optical cache. `frame.json` retains the original full archive's hashes.

From the repository root, with the pinned monitor runtime built:

```sh
build/monitor/runtime-clean/install/bin/ngspice -b -r /tmp/geometry.raw \
  verification/robotron-monitor/examples/geometry-connected-diagnostic/run.cir
python3 verification/robotron-monitor/steady_trace.py --raw /tmp/geometry.raw \
  --start .0585 --end .078 --output /tmp/geometry-field.csv
python3 verification/robotron-monitor/periodic_frame.py \
  --trace /tmp/geometry-field.csv --output /tmp/geometry-optical --assume-periodic \
  --field-parameters verification/robotron-monitor/examples/geometry-connected-diagnostic/field-parameters.json
python3 verification/robotron-monitor/loop_response.py --trace /tmp/geometry.raw \
  --runtime build/monitor/runtime-clean --output /tmp/geometry-loop-response
```

The current loop bench uses this trial's raw trace; its stimulus record includes
the trace hash. The earlier bench is retained as superseded evidence.
The deck uses KLU and the patched runtime's saved behavioral-source current
support; an arbitrary system ngspice is not an equivalent runtime.
