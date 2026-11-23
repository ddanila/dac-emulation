# Plan: one sustained-state frame from the K7222 reference monitor

Revised 2026-11-23. This file holds the method, the next steps and a short
status. It holds no work log: results live in the reports under
`reference/k7222-11/`, and history lives in the commits.

## Ground rules

1. **No human, no measurements.** The only inputs are the .11/.21 documents
   (schematics, parts lists, operating manual), public data for the same class
   of parts and tubes, and textbook knowledge of CRT monitors. No gate may need
   a human mark, a named reviewer or a bench reading.
2. **The work never stops to ask.** Every decision point has a default. A stage
   that cannot pass is replaced by a labelled equivalent (see "Fallbacks") and
   the work moves on. The outcome is always a frame with an honest label.
3. **Budget.** An open question gets at most three solver runs or one re-read
   of the page. After that its default or fallback is taken. Sweeps that a
   step itself calls for (calibration inside bounds, trim searches, B8
   sensitivity) do not count against this. A Phase B step that has not passed
   after one day of work takes its fallback. Progress is counted in Phase B
   steps scored against the manual, not in reports written.
4. **Accept what the documents can check.** A model that reproduces every
   documented value at its boundary is accepted. A detail that no document can
   distinguish (an internal winding join, an installed link, a part's safe
   operating area) is not a blocker. It is carried as a bounded alternative
   and reported in B8.
5. **Commit and push every increment.** Any change that runs and leaves the
   tests green is committed and pushed to `main` at once: a fixed target, a
   corrected net, a new score, a partial step. Work is never held back until
   a step passes.
6. **This file shows the current state, not the path to it.** When a result
   changes a target, a default, a step or a fallback, edit that line in place,
   in the same commit as the result. The Status table carries the latest
   scored value of each step against its limit. Nothing is appended: no dates,
   no "tried X, then Y". The commit message says why.

## Goal

Render **one frame of a native Robotron 1715 firmware screen** through the
component-level K7222.11/.21 circuit model, with the monitor in a **sustained
warm state**: heater and tube at thermal equilibrium, and every electrical
waveform repeating field to field. Scan currents, high voltage and electrode
voltages are solved by the circuit; nothing prescribes the beam position.

"Sustained" means periodic steady state, not a simulated warm-up from cold.

## Named goals

A standing instruction can name one of these, as in "Goal B8 as per PLAN.md".
Both are worked under the ground rules above, in the order of "Steps", and the
unit of work is the next unscored Phase B step.

| Name | Done when |
|---|---|
| **Goal B3** | B0–B3 are passed or on a named fallback: the vertical chain and horizontal oscillator are scored against the manual, and the horizontal output stage holds every port value of its table in periodic steady state |
| **Goal B8** | B0–B8 are passed or on a named fallback: the native full-text frame is rendered and labelled, and the B8 report is archived under `examples/` |

For either goal:

- A step is finished only when the scorer or gate tool shows its "Pass when"
  condition, or when its fallback has been taken and labelled.
- "Blocked" is not a valid state. A labelled frame with equivalent stages is a
  valid result.
- No new audit, source comparison or stress check is written unless a failed
  Phase B gate points at a specific part.
- Before each push, run the tests of the tools that changed. Run the whole
  suite (`make test-monitor`, a few minutes) once per finished step.
- Tests follow the rules in the repository's `AGENTS.md`: they check behaviour
  or a value against a limit, never a saved report byte for byte. A stale test
  is deleted or rewritten, not refreshed. A tool that refuses to run because
  an upstream report or sheet hash changed has that refusal removed.

## Non-goals

Parked, not deleted. None of them blocks the goal.

- Switching power converter. The frame uses ideal rails.
- Cold start, warm-up sequence, 16-field sustained recordings.
- Diagnosis of the museum specimen, the fault atlas, any .13/.23/.25 revision.
  The PC1715 service manual's K7222.25 text is used as a cross-check only.
- Real-time or in-browser simulation. Phase C prepares for it.
- Part stress, thermal and safe-operating-area qualification.
- New provenance or gate tooling, and new audits of pages already transcribed.

## Evidence tiers

| Tier | Meaning | May be used to |
|---|---|---|
| `documented` | Printed value or specification in the .11/.21 documents | Set values, gate |
| `documented-guideline` | Manual *Richtwert* or handwritten service annotation | Calibrate or gate, at ±20% |
| `agent-read` | Agent reading of a page image; two reads that differ in crop, resolution or model agree | Set values |
| `design-derived` | Calculated from documented values with a standard design equation | Set values and bounds |
| `class-typical` | Typical for this class of part or tube, with a cited source and bounds | Fill gaps; sensitivity reported in B8 |

A parameter left out because no document prints it is less correct than a
bounded typical value.

## Model closure (former Phase A): closed

The model is complete enough to score. Nothing in this section blocks Phase B.

| Item | State |
|---|---|
| Parts and values | 260 inventory entries; no open frame-path part review |
| Device models | All 64 frame-path devices have a register row with a source and bounds. That is the definition of done |
| Waveform targets | All 17 test points are machine-checkable: amplitude, shape, 2 kByte timing, EO2 bandwidth and probe load |
| Tools | No human requirement remains |
| Class-typical register | Exists. A value still missing takes a class-typical entry when its stage first needs it |
| Design point | Reworked in B0 from the port values below |

**Open alternatives.** Each has a default in the model. B8 reports the frame's
sensitivity to each one. None is investigated further unless a Phase B gate
fails and points at it.

| Alternative | Default |
|---|---|
| T3 internal joins, tap order, high-voltage cold end, manual-only X1:16 | 20-port page-4 graph with the X1:1–X1:7 bridge; cold end grounded; X1:16 unused |
| AE9VT yoke inductance, resistance and field per ampere | Inductance from the 16.0 µs retrace and the printed tuning capacitors; resistance `class-typical`; field per ampere set by picture size in B6 |
| T2 secondary phase and return | The phase that turns V18 off when V13 conducts (stated in the PC1715 manual) |
| E1–E4 centring links | E1+E2 (the pairs differ by under 0.02%) |
| C30 populated | Populated |
| V13 lead order on page 9 | The order that produces a vertical ramp |
| V24 present | Present, as in manual Fig. 12 and the parts list |
| C23 wiring on page 10 | Manual Fig. 12 |
| SYN on X3:6 or X3:7 | X3:6, as on page 18 |
| Contrast path | `manual-fig6-equivalent` (the page-3/4 wiring gives 0.3 V where 15 V is documented) |
| A3 amplifier | `P09A_EQUIV` |

## Horizontal output stage: documented targets

These port values define the stage. All voltages are to chassis, as are the
other handwritten notes on schematic page 4.

| Quantity | Target | Source |
|---|---|---|
| High voltage | 11–12 kV | page 4 |
| Boost voltage, C21 boost node to chassis | 60–70 V | page 4; PC1715 manual p. 85: raised "from 39…43 V to 60…70 V" |
| V18 collector flyback peak | about 400 V (320–480 V) | page 4 |
| G2 supply | about +350 V | page 4 |
| G1 at minimum brightness | about −25 V | page 4 |
| Test point 17 | 80 Vpp | manual |
| Test point 15 (V13 collector) | 36–54 Vpp | manual |
| Retrace / line | 16.0 µs / 62.5 µs | manual |
| 41P rail | 39–43 V, set by R5 | manual |

**The boost voltage is not the voltage across C21.** C21 sits between the 41P
feed and the boost node, so about 24 V across C21 is the documented operating
point. The cross-check: 65 V × 5.57 (the ideal flyback ratio for 46.5/16 µs)
gives 362 V, which agrees with "about 400 V". Reading 60–70 V as the
difference would need 550–630 V at the collector and contradicts that note.
Stage runs under the earlier winding graph settled at a 66 V boost node with
11.6–11.7 kV and the yoke current in band. The corrected graph has not yet
been scored against these targets.

## Calibration policy

- **Calibration set:** the port values above, retrace time and picture size.
  These may move `design-derived` and `class-typical` parameters inside their
  bounds.
- **Held-out set:** every other test point. A held-out miss triggers one
  re-read of the transcription and a look at the device models. It never
  triggers parameter fitting.
- **Trims** are set by running the manual's adjustment procedure on the model
  (B6).
- Calibrated values are frozen before the native frame is rendered. The
  rendered image never chooses a parameter.

## Rails and controls

- **R5 (width).** With ideal rails, R5 is one common scale factor on the
  converter-derived rails, with 41P inside 39–43 V. Recorded as "R5 equivalent".
- **R4 (horizontal centring).** The transcribed page-9 bridge. Expected near
  neutral, since the model has no gun misalignment.
- **R1 (brightness).** Page-3/4/18 pot connections; `class-typical` 10 kΩ with
  5 kΩ as its bound.

## Acceptance gates

| # | Gate | Limit |
|---|---|---|
| G1 | Horizontal lock: every line sync edge has one flyback; phase variation over the last three fields | ≤ 0.01 line |
| G1b | Adjacent-line jitter | ≤ 0.5 dot (about 36 ns) |
| G2 | Periodicity of high voltage, both yoke currents, G2/G4 and core flux over the last three fields | ≤ 1% |
| G3 | Calibration set: amplitude and shape | within ±20%; high voltage 11–12 kV; boost 60–70 V |
| G4 | Held-out test points: amplitude and shape | within ±25%; at most three misses, each with a written cause |
| G5 | Geometry on a full-screen grid: picture size versus the manual; linearity on both axes | 90–105%; ≤ 10% |
| G6 | Electrical refinement (half timestep) and a second initialisation | ≤ 1% |
| G7 | Optical refinement | ≤ 2% |
| G8 | Readability: correlation with the logical reference after one global affine fit, used for scoring only | ≥ 0.7 |

Reported, not blocking: signed energy ledger, interception-current feedback,
heater heat balance, solver step audits.

## Phase B: build toward the frame

### Rules for every simulation

- **Start at the operating point, never from cold.** Initialise the reservoir
  states (high-voltage capacitance, boost, G2/focus and coupling capacitors)
  from the design point, then correct the slow states by charge balance until
  their net change per field is under 1%.
- **Only the sustained state is evidence.** Nothing is pruned or chosen from a
  startup window.
- **Solver budget.** A bench whose median accepted step stays below 20 ns has
  a model defect, usually a winding or junction with no loss or capacitance.
  Fix it with bounded `class-typical` parasitics; do not wait for the run.
- **Stage alone before connected.** The horizontal stage reaches periodic
  steady state on its own bench (two consecutive lines agree within 0.1%).
  Its end state initialises the connected run. Whole fields are simulated only
  from B4 on, and then at most four.
- **Independent solves run in parallel**, one per CPU core, each in its own
  output directory.
- **One solver.** Every Phase B run and every test uses the pinned ngspice 47
  runtime, `build/monitor/runtime-phase-a-gcc16-verified`. `make test-monitor`
  sets `MONITOR_RUNTIME` to it; a bare `unittest` run without that variable
  skips the runtime tests. Saved
  reports made with the system ngspice may be re-scored in B0, but a result
  that passes a step is produced on the pinned runtime.
- **Every run records its cost:** wall time, simulated time, accepted steps,
  median step.

The circuit solve (ngspice) is the cost. Porting the Python tools or moving
the solve to a GPU would not shorten a run. Target: one connected field in
under ten minutes. Missing the target does not block the frame.

### Steps

B1 and B2 do not depend on T3. They run in parallel with B0 and B3.

| Step | Work | Pass when |
|---|---|---|
| B0 | **Fix the targets.** Change the C21 target to boost node to chassis in `design-point.json`, the K7222.25 cross-check and the T3 screens. Add the collector-peak check. Derive the T3 port ratios from the table above. Make the 20-port bridge graph the default. Re-score the saved corrected runs; run nothing new first | `design-point.json` is complete and no longer marked partial |
| B1 | Vertical chain (sync filter, oscillator, integrator, output, yoke) scored against test points 1–8. Settle the R59/R60 roles by sweep | All eight within ±25% with matching shape |
| B2 | Horizontal oscillator and phase detector, open loop, test points 9–13 | Points within ±25%; 62.5 µs lies inside R24's range; tuning is monotonic around the operating point |
| B3 | Horizontal output, T3 and yoke on an ideal drive, from the design point to periodic steady state. Calibrate inside bounds | Solver budget met; every port value in the table within G3 |
| B4 | Close the horizontal loop on a grid pattern | G1, G1b, G2 |
| B5 | Warm state: heater solved from its own branch and held at equilibrium; tube emission loads the high-voltage rail. Cut-off tied to the documented cathode levels (35 V dark, 15 V bright) | G2 still passes with the tube load |
| B6 | **Virtual service procedure.** Run the manual's adjustment steps (pages 30–32) on the grid with virtual instruments. Each trim is a bounded one-dimensional search. Focus is the smallest centre spot at 20 µA. Freeze | G5; calibration freeze verifies |
| B7 | Render the native full-text frame at full resolution | G1–G8 |
| B8 | Report held-out results and the frame's sensitivity to every `class-typical` parameter and every open alternative; archive under `examples/` | Report published |

If B4 fails while B1–B3 pass, debug in this order: output stage with ideal
drive, closed loop with an ideal flyback reference pulse, full loop.

## Phase C: speed, after the frame

Phase C starts when B8 is published. The accepted frame and its traces are
the reference. Nothing here may change a Phase B result.

| Step | Work | Pass when |
|---|---|---|
| C1 | Profile one frame from the run receipts: circuit solve, trace export, trajectories, phosphor | A table with the largest item named |
| C2 | Compiled circuit solver: C++ generated from the netlist and device register for this one fixed circuit (fixed topology and step, tabulated device curves) | Last-field waveforms within G6's 1% of ngspice; G1–G5 still pass; speed-up reported |
| C3 | GPU for trajectories and phosphor, only if C1 shows the optical stage is a large share after C2 | Image within G7's 2% of the CPU render |
| C4 | State how far one frame is from the 19.5 ms field time and whether real time is reachable with a reduced model | Written assessment |

If C2 cannot meet 1% at a fixed step, it stays a preview solver with its
error stated, and ngspice remains the reference.

## Fallbacks (decided in advance)

A step has failed when its gate is still missed after the budget in ground
rule 3. Then:

- **B3, T3 does not reach its port values:** use an equivalent T3, an ideal
  multi-winding transformer whose ratios are the port voltages in the table
  divided by the collector pulse, with class-typical leakage, capacitance and
  loss. It needs no internal winding graph.
- **B1 or B2 fails:** replace only the failing sub-stage by an equivalent
  source that reproduces its documented test-point waveform.
- **B3, no drive reaches test point 15 and the high voltage together:** drive
  V18's base from an equivalent source limited to its 9 V reverse-base rating.
- **B4, no lock with every test point in range:** use a behavioural phase-lock
  stage for this frame.
- **Anything else:** substitute the smallest equivalent that reproduces the
  documented behaviour at that stage's boundary, and continue.

Every equivalent stage is named in the result label and in the B8 report. If
a later result explains the failure, restore the component-level stage and
re-run the gates from there.

## Status

One row per step. "State" holds the step's latest scored values against
their limits, or "passed" or the fallback's name. Edit rows in place.

| Step | State | Next |
|---|---|---|
| Model closure | Closed by rule | — |
| B0 | Open. Saved targets still use the C21 difference; default model is still the 19-port graph | Do B0 as written |
| B1 | Not scored. Stage benches exist for sync filter, oscillator, integrator and output | Score test points 1–8 |
| B2 | Not scored. The isolated oscillator bench shows a non-monotonic tuning curve, treated as a transcription or model error | Score test points 9–13 |
| B3 | Not scored on the corrected graph. Its connected startup runs end near a 60 V boost node and 10.4 kV | Run the stage bench from the B0 design point |
| B4–B8 | Not started. No connected run has completed three locked fields | After B1–B3 |
| Phase C | Waits for B8 | — |

### Findings that stand

- **Contrast and IS.** INTENS (X9:5), V5's IS output to the neck (X3:2) and
  the HRS wiper at V1's base are three separate nets. IS is active low.
- **TP8.** The manual's 17 V is crest-to-zero, not peak-to-peak.
- **TP17** is 80 Vpp, and the register includes test point 16.
- **T3 pins.** Page 4 shows 20 magnetic terminals. V21 sits on X3:1/X3:2,
  X1:2 joins X2:3, X1:1 joins X1:7, V16/C26 go to X2:13 and C21 to X2:10.
- **P09A.** The `LM709_FAMILY` substitute failed a DC follower check.
- **Measuring cable.** The page-16 inset has a series capacitor and unvalued
  shunts, so a DC voltage at X3 cannot stand in for the 0.1/3.6 mV service
  readings.
- **Timestep.** 50 ns and 200 ns connected runs disagreed by 22% on mean high
  voltage; use 50 ns or finer and let G6 decide.

`make test-monitor` checks the tools and that saved reports reproduce. It
needs the source PDFs under `build/`. A green run is not a Phase B result.

## What the result may be called

A frame that passes with no equivalent stage is a **documented-reference
K7222.11/.21 frame**: anchored to the manufacturer's documents, with ideal
supply rails and declared class-typical values. With equivalent stages it is
a **documented-reference frame with equivalent stages**, and the stages are
listed. Neither is a measurement of any physical monitor.
`full_monitor_qualified` and `specimen_validated` stay false.
