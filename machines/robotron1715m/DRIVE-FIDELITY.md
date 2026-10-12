# Drive timing and visualization

The model is deterministic and synchronized, not a claim of 100% specimen fidelity.

Both drives keep independent motor-gated phase counters (798720 CPU clocks per
revolution at 3.9936 MHz). Read/write sector waiting uses the selected drive's
phase. Motor off freezes phase and extends an in-flight data deadline; restarting
continues that phase. No browser wall clock is used for current-core rotation.
Seek/recalibrate advances one cylinder at each latched SPECIFY interval, including
reverse motion. Seek completion is reported only after reaching the target.

The browser receives phase, cylinder, cumulative step count, selected side and
sector, and execution/write flags in each frame. Geometry represents the sampled
emulated instant; it does not invent intermediate movement between samples.
At high emulation speeds or low frame rates, several steps/revolutions can occur
between frames. Pausing freezes the view; restored state and deterministic replay
restore phase and seek timing. Hidden geometry catches up to the next sample.
Reduced-motion settings deliberately freeze the rotor. Mechanical-demo controls
remain an explicitly separate illustration. Preserved older cores retain their
legacy animation and are labeled in the museum runtime notice.

## Reference and bounds

[TEAC FD-55FV-13 specification, pp.107–109](https://retrocmp.de/fdd/teac/TEAC_FD55-FV.pdf)
gives 300 RPM, 96 tpi, and one step per track. Thus the nominal displacement is
25.4/96 mm per track, or 20.902083 mm over 79 steps. The museum previously used an
incorrect 35 mm visual estimate. The owner's exact FD-55 suffix is unverified;
carriage origin, geometry and spindle/index angular alignment are still estimates.

The document bounds motor startup below 400 ms, settling below 15 ms and head
load below 50 ms. These are limits, not measured acceleration/settling curves.
We do not pretend that an invented curve is the exact behavior of these drives.

Remaining limitations:

- Instant nominal-speed motor start/stop; no inertia, coast-down or READY delay.
- No head-load/settling dynamics, stepper electrical model or mechanical backlash.
- SPECIFY intervals quantized to CPU clocks; no physical minimum step-rate errors.
- Logical cylinders outside 0–79 are not a model of mechanical stops; visualization
  clamps them. Recalibration is functional rather than a 765 pulse-limit model.
- Raw 80×2×5×1024 sector images do not preserve index-relative sector positions,
  interleave, gaps, flux, weak bits or spindle mounting angle. Five evenly spaced
  sectors and the 4000-clock data-start offset remain idealizations.
- Read-ID still returns the next logical ID without a rotational search. Formatting
  cannot retain arbitrary physical ID layouts. Byte pacing is rounded to 128 clocks;
  lost-data, stopped-drive timeout and real index-pulse behavior are not modeled.
- Sound is synthesized and frame-sampled, not a recording or per-step acoustic model.

Further physical calibration needs the exact drive suffix, index/STEP/READY traces,
a track-preserving disk capture, and measured carriage and motor behavior. Those
unknowns should be tracked rather than described as solved by knowing sector IDs.

## Validation

Native device checks cover independent phases, wrap, motor stop/restart, sector
latency from drive phase rather than CPU time, and intermediate forward/reverse
seek positions. WASM checks cover phase snapshot restoration. Browser checks cover
wall-clock independence, hidden/reduced-motion handling, and demo/state restoration.
The CAD audit checks all 80 nominal head positions against fixed solids; this is
not a full mechanical qualification.
