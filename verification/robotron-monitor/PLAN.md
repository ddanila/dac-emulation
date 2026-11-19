# Plan: one sustained-state frame from the K7222 reference monitor

Written 2026-11-18. This plan supersedes the open-ended blocker lists in
`README.md`, `single-frame-acceptance.md` and
`reference/k7222-11/full-path-requirements.json` wherever they disagree. Those
files stay as the record of what exists.

## Goal

Render **one frame of a native Robotron 1715 firmware screen** through the
component-level K7222.11/.21 circuit model, with the monitor in a **sustained
warm state**: heater and tube at thermal equilibrium, and every electrical
waveform repeating field to field. Scan currents, high voltage and electrode
voltages are solved by the circuit; nothing prescribes the beam position.

"Sustained" means periodic steady state, not a simulated warm-up from cold.

## Non-goals

These are parked, not deleted. None of them blocks the goal.

- Switching power converter. The frame uses ideal 12 / 22 / 41 / −16 V rails.
- Cold start, warm-up sequence, 16-field sustained recordings.
- Diagnosis of the museum specimen, the fault atlas, any .13/.23/.25 revision.
- Real-time or in-browser simulation.
- New work on the trajectory/phosphor renderer beyond calibration. It is
  already converged and fast enough for one frame.

## Why two phases

The pipeline runs end to end today, but horizontal never locks and the image is
an unreadable smear. Sweeping parameters has not fixed it, because nothing in
the model is compared with the documentation's reference values. Phase A fixes
that method; Phase B then builds toward the frame stage by stage. Doing B
without A repeats the last four days.

## Evidence tiers

| Tier | Meaning | May be used to |
|---|---|---|
| `documented` | Printed value or specification in the .11/.21 documents | Set values, gate |
| `documented-guideline` | Manual *Richtwert* (approximate waveform value) | Calibrate or gate, at ±20% |
| `ocr-candidate` | Machine reading, not yet reviewed | Flag disagreements only |
| `inferred` | Derived from documents with a stated argument | Set values, reported as inferred |
| `assumed` | Engineering guess inside declared bounds | Fill gaps; sensitivity must be reported |

## Phase A: correct the method

### A1. Read the documents properly

Run the existing local multi-pass OCR pipeline (kept outside this repository;
five vision-model passes, a classic table engine, per-cell vote, review viewer)
on the source PDFs, re-downloaded into `build/` and checked against
`sources.json` hashes.

- Parts lists: schematic set pages 6–8, 12–15, 17, as tables.
- Operating manual pages 9–21 and 29–32, as text.
- High-zoom designator scan of schematic pages 3–4, 9–10, 16, 18.

Diff the result against `reference/k7222-11/inventory.json`. The inventory is
the comparison target, never an arbiter prior. Schematic connectivity, diode
direction and winding polarity stay human review in KiCad.

**Gate:** every one of the 260 inventory entries is either confirmed by at
least three agreeing passes or carries a human review mark. Known unreadable
values (C15 and similar) stay unresolved.

### A2. Complete the reference register

`service-observations.json` holds only peak-to-peak swing for 16 test points,
all marked `not-yet-evaluated`. Extend it from manual pages 20–21 and 29–32:

- Per test point: polarity, DC level, period, pulse width, shape class, and the
  operating conditions the manual states.
- Horizontal retrace time, picture width and height, centring and focus
  targets, and the adjustment procedure steps.
- Check why test point 16 is absent from the register.
- Look for a B31G22 data sheet (deflection angle, heater, cut-off voltage).

**Gate:** every test point has its node mapped to a model node, or a written
reason why it cannot be.

### A3. Split calibration from validation

- **Calibration set:** test points 14, 15 and 17, high voltage 11–12 kV,
  retrace time, picture size. These may set `assumed` parameters (flyback T3
  ratios and leakage, yoke inductance and field per ampere, L4 coupling, tank
  inductance) inside their declared bounds.
- **Held-out set:** every other test point. A held-out failure triggers a
  review of transcription and device models against the sources. It never
  triggers parameter fitting.
- **Trims** (horizontal hold R24, height, linearity, centring, focus,
  brightness, contrast) are set by the manual's adjustment procedure and
  recorded. That is how the real monitor was set up.
- Calibrated values are frozen before the native frame is rendered. The
  rendered image is never used to choose a parameter or a T3 candidate.

### A4. Reorder the acceptance gates

**Blocking (the frame is not accepted without these):**

| # | Gate | Limit |
|---|---|---|
| G1 | Horizontal lock: every line sync edge has one flyback; phase variation over the last three fields | ≤ 0.01 line |
| G1b | Adjacent-line jitter | ≤ 0.5 dot (about 36 ns) |
| G2 | Periodicity of high voltage, both yoke currents, G2/G4 and core flux over the last three fields | ≤ 1% |
| G3 | Calibration set | within ±20%; high voltage 11–12 kV |
| G4 | Held-out test points | within ±25%, each miss explained |
| G5 | Geometry on a full-screen grid: picture size versus the manual; linearity error on both axes | 90–105%; ≤ 10% |
| G6 | Electrical refinement (half timestep) and a second initialisation | ≤ 1% |
| G7 | Optical refinement (existing check) | ≤ 2% |
| G8 | Readability: correlation with the logical reference after one global affine fit, used for scoring only | ≥ 0.7 |

**Reported, not blocking:** signed energy ledger, iterated
interception-current feedback, heater heat balance, solver step audits.

### A5. Use proper test content

- Synthetic grid and cross-hatch patterns are allowed for calibration and for
  G1–G6. They stay labelled synthetic.
- The final frame uses a native capture with a full text screen. The current
  capture holds only a two-line loader banner; take a later one.

### A6. Score stages against the manual before connecting them

Add one scoring tool that reads the register, measures the mapped nodes in any
bench or assembly run, and reports measured versus expected for each test
point. Every Phase B step ends with its output.

## Phase A status: blocked (2026-11-19)

The A1 source-review gate has not passed. Of 260 inventory entries, 227 are
machine-confirmed, none has a human review mark, and 33 remain open. Human
review is also outstanding for schematic pages 3, 4, 9, 10, 16 and 18,
especially T3 winding/pin connectivity and diode direction, the horizontal
centring bridge, and external brightness wiring. The current gate report is
`build/monitor/phase-a/source-review-gate-current-20261118.json`; the local
review guide and mark template are described in
[`phase-a-evidence.md`](phase-a-evidence.md).

A3 has no passing sustained-state grid calibration or calibration freeze.
The T3/TP17 path still needs source review before its startup diagnostics can
be used to select a candidate. Brightness and 012-6931:R4 horizontal centring
are not bound to verified model controls. The manual's 012-6931:R5 picture-width
trim acts through converter feedback, while this plan excludes the converter
and uses fixed rails; R5 therefore cannot adjust width in the current model.

Resume by completing the human source marks and resolving those connections,
then decide whether to include the R5 converter feedback path or revise the
width-trim requirement for ideal rails. Bind the remaining controls, run the
synthetic grid to sustained state, and freeze calibration only after its
documented gates pass. The Phase A requirements above remain in force.

## Phase B: build toward the frame

Each step runs on ideal rails and must pass before the next starts.

| Step | Work | Pass when |
|---|---|---|
| B1 | Vertical chain (sync filter, oscillator, integrator, output, yoke) scored against test points 1–8 | All eight within ±25% |
| B2 | Horizontal oscillator and phase detector, open loop, test points 9–13 | Points within ±25%; R24 moves the free-running period across 62.5 µs with ±3% margin; tuning is monotonic around the operating point |
| B3 | Horizontal output, T3 and yoke driven by an ideal drive. Prune the 16 T3 candidates by pulse polarity and amplitude, then calibrate | G3 passes; at least one candidate survives; all survivors are carried forward |
| B4 | Close the horizontal loop on a grid pattern | G1, G1b, G2 |
| B5 | Warm state: heater solved from its own branch, temperature held at equilibrium, tube emission loading the high-voltage rail | G2 still passes with the tube load |
| B6 | Geometry: set field per ampere and trims by the manual procedure on the grid, then freeze | G5 |
| B7 | Render the native full-text frame at full resolution | G1–G8 |
| B8 | Report held-out results and the sensitivity of the frame to each `assumed` parameter at its bounds; archive under `examples/` and update `README.md` | Report published |

The non-monotonic tuning curve already measured in the isolated oscillator
bench is treated in B2 as a suspected transcription or model error, not as a
property to work around.

If B4 fails while B1–B3 pass, debug in this order: output stage with ideal
drive, closed loop with an ideal flyback reference pulse, full loop.

## Decision points

- **After A1:** if more than about 10% of inventory entries change, re-run the
  existing stage benches before starting B1.
- **After B3:** if no T3 candidate survives, the hypothesised winding topology
  is wrong. Stop and revisit the winding map before any loop work.
- **After B4:** if lock still fails with every test point in range, stop and
  decide whether to continue circuit-level work or to accept a behavioural
  phase-lock stage for this frame.

## What the result may be called

A passing frame is a **documented-reference K7222.11/.21 frame**: anchored to
the manufacturer's manual, with ideal supply rails and declared assumptions.
It is not a measurement of any physical monitor. `full_monitor_qualified` and
`specimen_validated` stay false.
