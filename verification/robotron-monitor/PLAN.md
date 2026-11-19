# Plan: one sustained-state frame from the K7222 reference monitor

Written 2026-11-18, revised 2026-11-19. This plan supersedes `README.md`,
`single-frame-acceptance.md`, `phase-a-evidence.md` and
`reference/k7222-11/full-path-requirements.json` wherever they disagree. Those
files stay as the record of what exists.

## Ground rule: no human, no measurements

The emulator is built without a person in the loop and without any measurement
of a real monitor. The only inputs are:

- the .11/.21 documents (schematics, parts lists, operating manual);
- public data for the same class of parts and tubes;
- textbook knowledge of how CRT monitors work and are designed.

Every reading, connection and decision is made by an agent and recorded with
its evidence. No gate may require a human mark, a named reviewer or a bench
reading.

**The work never stops to ask.** Every decision point below has a default.
When a stage cannot be made to pass, it is replaced by a labelled equivalent
and the work moves on (see "Fallbacks"). The outcome is always a frame with an
honest label. This rule was confirmed by the project owner on 2026-11-19 and
applies to anything this plan did not foresee: take the option that keeps the
frame closest to the documented circuit, record it, and continue.

## Goal

Render **one frame of a native Robotron 1715 firmware screen** through the
component-level K7222.11/.21 circuit model, with the monitor in a **sustained
warm state**: heater and tube at thermal equilibrium, and every electrical
waveform repeating field to field. Scan currents, high voltage and electrode
voltages are solved by the circuit; nothing prescribes the beam position.

"Sustained" means periodic steady state, not a simulated warm-up from cold.

## Non-goals

These are parked, not deleted. None of them blocks the goal.

- Switching power converter. The frame uses ideal rails (see "Rails and R5").
- Cold start, warm-up sequence, 16-field sustained recordings.
- Diagnosis of the museum specimen, the fault atlas, any .13/.23/.25 revision.
- Real-time or in-browser simulation. Phase C prepares for it but does not
  deliver it.
- New work on the trajectory/phosphor renderer beyond calibration.
- New provenance or gate tooling. Enough exists. Add code of that kind only
  when a stage result cannot be checked without it.

## What the first day of implementation showed

The first revision of this plan was followed for one day (about 60 commits).
The register, scorer, test content and gate contract were built and are sound.
No stage was scored against the manual and no field completed. Five causes,
each fixed in this revision:

1. **Human gates deadlocked the work.** A1 required human marks on 33 parts and
   six schematic pages; G3/G4 required a named waveform reviewer. No human is
   available, so nothing could pass.
2. **Phase A absorbed calibration.** A calibration freeze needs a locked,
   connected grid run, which is Phase B work. Phase A could never finish.
3. **The connected monitor was run before its stages.** The plan asked for
   stage scoring first (A6). The connected grid run was tried instead, from a
   cold start, and its first milliseconds were read as diagnostics. Startup
   says nothing about the sustained state.
4. **T3 values were guesses, not design values.** Turns, leakage and
   capacitance were placeholders with fourfold bounds, never derived from the
   documented voltages. The auxiliary winding had almost no damping, so it
   rang at megahertz rates, the solver step fell to 1.5 ns and a field could
   not finish. Damping was withheld because no document prints it.
5. **Three controls had no place in the model.** Width trim R5 lives in the
   excluded converter; centring R4 and the brightness control were not
   transcribed.

## Evidence tiers

| Tier | Meaning | May be used to |
|---|---|---|
| `documented` | Printed value or specification in the .11/.21 documents | Set values, gate |
| `documented-guideline` | Manual *Richtwert* (approximate waveform value) | Calibrate or gate, at ±20% |
| `agent-read` | Direct agent reading of a page image: two independent reads agree, crop and hash recorded | Set values |
| `design-derived` | Calculated from documented values with a standard design equation, argument written down | Set values and bounds |
| `class-typical` | Value typical for this class of part or tube, with a cited public source or textbook range and declared bounds | Fill gaps; sensitivity must be reported |
| `ocr-candidate` | Single machine reading, not confirmed | Flag disagreements only |

`class-typical` replaces the old `assumed`. Transferring a typical value from
comparable parts is allowed and expected: winding resistance, capacitance and
core loss of a flyback transformer, heater and cut-off data of a 31 cm
monochrome tube, yoke sensitivity. A model with a parameter left out because
no document prints it is less correct than one with a bounded typical value.

## Phase A: method (close out, do not extend)

Phase A is finished when the six items below are done. It produces no gate
result and no calibration. It is a closing exercise: an item that cannot be
closed after one bounded attempt takes a `class-typical` value with bounds and
the work moves on.

### A1. Close the source review without a human

- **Parts.** Of 260 inventory entries, 227 are machine-confirmed. For the 33
  open ones, an agent reads the page image at high zoom twice, independently,
  and checks the reading against the part's role (standard value series,
  rating, what the circuit needs). Each entry ends as `agent-read` or as
  `class-typical` with bounds.
- **Independent reads.** Two reads by the same model of the same image tend
  to repeat one error. The two reads must differ in at least one of: crop,
  resolution, model. A classic OCR reading counts as one of them.
- **Triage.** Only parts in the ideal-rail frame path block. Converter-only
  parts (most of page 15, fuse P1) are recorded and do not block.
- **Sensitivity before effort.** Where a stage bench exists, vary the open
  part across the plausible readings first. If no test point of that stage
  moves by more than 2%, take the most plausible reading and close the entry.
- **Second netlist.** Part values were audited five times; the connections
  were transcribed once. For schematic pages 3–4, 9–10, 16 and 18, an agent
  extracts a pin-to-pin net list from the page images without seeing the KiCad
  files. Diff it against the KiCad export. Every difference is re-read and
  settled; agreement is recorded as `agent-read`.
- **Connectivity.** A connection, diode direction or winding polarity is
  confirmed by function, not by a reviewer:
  - static checks on the netlist: every node has a DC path, electrolytic and
    rectifier orientation agree with the rail sign they serve, every
    transistor has a plausible DC operating point;
  - the stage bench reproduces its documented test points (Phase B).
  A transcription that passes both stands. One that fails is re-read from the
  page image before any parameter is touched.
- **Conflicts inside the documents** are settled by simulation where possible.
  Example: pages 15 and 32 disagree on which of R59/R60 acts on the upper
  screen half; sweep each in B1 and record which half moves.

### A2. Give every device a model

The inventory marks 77 parts as identity-only: 33 diodes, 21 transistors,
4 zeners, 4 integrated circuits, 8 inductors, 4 transformers and 3 others.
Their type is printed but their electrical behaviour is not, and the source
audit never covered it. These parts decide oscillator frequency, switching
times and rectifier behaviour, so they matter more than the 33 open values.

- For each frame-path semiconductor, take parameters from public data-book
  values for the printed type, or for the nearest documented equivalent type.
  Tier `class-typical`, source cited, bounds from the data book's spread.
- Parameters that must not be left at simulator defaults: current gain range,
  transition frequency and saturation voltage for transistors; storage and
  fall time for the horizontal output and driver transistors; recovery time
  and capacitance for the damper, pulse and high-voltage rectifiers; zener
  voltage and impedance.
- Inductors and transformers other than T3 get values by the same
  `design-derived` route as T3 (A5).
- Record all of it in one device-model register next to the inventory.

**Done when:** every frame-path device has a model with a source and bounds,
and no frame-path device uses an unexamined simulator default.

### A3. Make the manual's waveforms machine-checkable

The register already holds amplitude, period and node for all 17 test points.
Add shape descriptors read from the figures on manual pages 20–21 (tier
`agent-read`): polarity of the pulse relative to its baseline, shape class
(sawtooth, pulse, parabola, composite), and duty where it can be read. The
scorer checks them. This replaces the named waveform reviewer.

Also fix what the comparison means:

- **Operating mode.** The manual gives two modes. The native S550 frame is the
  2 kByte mode: 62.5 µs line with 16.0 µs retrace, 19.5 ms field with 1.5 ms
  retrace. Every target, and the T1 setting, is taken for that mode. The
  1 kByte values (17.2 µs, 2.08 ms) are recorded and not used.
- **Instrument.** The manual's values were read on an EO2 service
  oscilloscope. Peak-to-peak of a narrow pulse depends on bandwidth, and a
  probe loads a high-impedance node. The scorer applies a `class-typical`
  bandwidth limit and probe load for that instrument before it measures, and
  reports the raw value beside it.
- **Picture content.** State which input the manual's waveforms assume where
  it says so; otherwise score on the grid pattern and record that choice.

### A4. Remove human requirements from the tools

Delete the requirements; do not build a replacement review system.
`phase_a_review.py` and `phase_a_gates.py` drop the reviewer fields and accept
the existing audit entry with a reading, crop hash and argument. The A1
prerequisite counts frame-path entries only. `calibration_contract.py` stops
refusing the three controls once they are bound as described below.

### A5. Design point and document consistency

Calculate the intended operating point from documented values, before any
simulation, and write `design-point.json`:

- retrace time and tuning capacitance give the effective inductance;
- rail voltage and the trace/retrace ratio give the collector flyback peak;
- that peak and 11–12 kV give the high-voltage ratio, through the rectifier
  arrangement drawn;
- test points 14 and 17 constrain the feedback and rectified flyback paths
  after their source connections are settled; test point 15 is the V13 driver
  collector and checks drive, not a winding ratio;
- picture size, tube/yoke geometry, field per ampere and high voltage give
  the peak yoke currents;
- the vertical yoke values follow the same way from test points 1–8.

Replace the placeholder T3 values and fourfold bounds with these values and
tighter bounds. Fix each winding's polarity from its function: the
high-voltage rectifier and every pulse rectifier must conduct in the phase
their load needs. This prunes the 16 candidates before any simulation.

The same calculation checks the documents against themselves. If two
documented values cannot both hold (for example retrace time against the
printed tuning capacitor and any plausible yoke), one of them was misread:
re-read both before going on.

**Done when:** every T3 ratio and yoke value carries a tier and an argument,
the candidates left are listed with reasons, and no pair of documented values
contradicts another.

### A6. Class-typical register

Collect every `class-typical` value in one file with its source, bounds and
the stage it affects: tube data for a 31 cm monochrome tube (deflection
angle, heater, cut-off tied to the documented 35 V dark and 15 V bright
cathode levels), yoke sensitivity, T3 parasitics, instrument data. B8's
sensitivity report runs over this file.

### Already done and kept

Register with test point 16 and the TP17 correction (80 Vpp). Scoring tool
`service_score.py`. Synthetic grid and cross-hatch captures. Native full-text
capture. Calibration/validation split and freeze contract. Gate recomputation
from traces.

## Calibration policy (unchanged in substance)

- **Calibration set:** test points 14, 15 and 17, high voltage 11–12 kV,
  retrace time, picture size. These may move `design-derived` and
  `class-typical` parameters inside their bounds.
- **Held-out set:** every other test point. A held-out failure triggers a
  re-read of the transcription and a review of the device models. It never
  triggers parameter fitting.
- **Trims** are set by running the manual's adjustment procedure on the model
  (B6) and recorded.
- Calibrated values are frozen before the native frame is rendered. The
  rendered image never chooses a parameter or a T3 candidate.

## Rails and controls

- **Rails and R5.** The manual sets picture width with R5, which changes the
  converter's output voltage. With ideal rails, R5 is represented by its
  effect: one common scale factor on the converter-derived rails. Its range is
  `design-derived` from the page-10 feedback divider at the two ends of R5.
  Width is trimmed with this factor and the result is recorded as "R5
  equivalent". The converter itself stays out.
- **Horizontal centring R4 (012-6931).** Transcribe the page-9 bridge by agent
  reading. If a link stays ambiguous, use the standard equivalent, a bounded
  DC current through the yoke, tier `class-typical`. The model has no gun
  misalignment, so the setting is expected near neutral.
- **Brightness (external R1).** Transcribe from page 3. The pot value is
  handwritten, so it is `class-typical` at 10 kΩ with the 5 kΩ alternative as
  its bound.

## Acceptance gates

**Blocking:**

| # | Gate | Limit |
|---|---|---|
| G1 | Horizontal lock: every line sync edge has one flyback; phase variation over the last three fields | ≤ 0.01 line |
| G1b | Adjacent-line jitter | ≤ 0.5 dot (about 36 ns) |
| G2 | Periodicity of high voltage, both yoke currents, G2/G4 and core flux over the last three fields | ≤ 1% |
| G3 | Calibration set: amplitude and shape descriptors | within ±20%; high voltage 11–12 kV |
| G4 | Held-out test points: amplitude and shape descriptors | within ±25%; at most three misses, each with a written cause |
| G5 | Geometry on a full-screen grid: picture size versus the manual; linearity error on both axes | 90–105%; ≤ 10% |
| G6 | Electrical refinement (half timestep) and a second initialisation | ≤ 1% |
| G7 | Optical refinement (existing check) | ≤ 2% |
| G8 | Readability: correlation with the logical reference after one global affine fit, used for scoring only | ≥ 0.7 |

**Reported, not blocking:** signed energy ledger, iterated
interception-current feedback, heater heat balance, solver step audits.

## Phase B: build toward the frame

Each step runs on ideal rails and ends with the scorer's output. A step must
pass, or take its fallback, before the next starts.

### Rules for every simulation

- **Start at the operating point, never from cold.** Initialise reservoir
  states (high-voltage capacitance, boost and G2/focus capacitors, coupling
  capacitors) from the design point of A5. Then correct the slow states by
  charge balance until their net change per field is under 1%. G6's second
  initialisation checks that the result does not depend on the start.
- **Only the sustained state is evidence.** No candidate is pruned, and no
  parameter chosen, from a startup window.
- **Solver budget.** A bench whose median accepted step stays below 20 ns, or
  whose line-rate nodes cross their midrange far more often than once per
  line, has a model defect: usually a winding or junction with no loss or
  capacitance. Fix the model with bounded `class-typical` parasitics. Do not
  wait for the run.

- **Stage alone before connected.** The horizontal stage is brought to
  periodic steady state on its own bench, over lines, not fields: stop when
  two consecutive lines agree within 0.1% on yoke current, collector voltage
  and core flux. Its end state initialises the connected run. Only B4 onward
  simulates whole fields, and then at most four.
- **Run independent solves in parallel.** T3 candidates, bound sweeps, trim
  searches, the two G6 variants and B8's sensitivity runs are separate solver
  processes. Run them side by side, one per CPU core, each in its own output
  directory. Results must not depend on how many ran at once.
- **Record the cost.** Every run writes wall time, simulated time, accepted
  steps and median step to its receipt. Speed work is chosen from these
  numbers, not from guesses.

### Where the time goes

The circuit solve is the cost. In the recorded runs the solver needed 324 s
for 5.2 ms and 1,523 s for 14 ms of simulated time, at a median step near
1.5 ns. The solver (ngspice) is already compiled code. Python only builds the
deck and reads the trace, and the beam trajectory code already has a native
C++ path. So, for the reference frame:

- Do not port the Python tools to a compiled language. It would not shorten
  a run.
- Do not move the circuit solve to a GPU. Each time step depends on the last
  and the matrix is small; there is nothing to run in parallel.
- Get speed from the four rules above, in this order of payoff: solver budget
  (remove the stiffness), start at the operating point, stage alone before
  connected, parallel solves.

**Target:** one connected field solves in under ten minutes on this machine.
If B4 cannot reach that after the rules are applied, record the receipts and
continue at the speed available; it does not block the frame.

### Steps

| Step | Work | Pass when |
|---|---|---|
| B1 | Vertical chain (sync filter, oscillator, integrator, output, yoke) scored against test points 1–8. Settle the R59/R60 roles by sweep | All eight within ±25% with matching shape |
| B2 | Horizontal oscillator and phase detector, open loop, test points 9–13 | Points within ±25%; 62.5 µs lies inside R24's range; that range is consistent with the documented 14.338–16.338 kHz; tuning is monotonic around the operating point |
| B3 | Horizontal output, T3 and yoke on an ideal drive, started at the design point and run to periodic steady state. Prune the remaining T3 candidates by pulse polarity and amplitude, then calibrate | Solver budget met; test points 14, 15, 17, high voltage and retrace time within G3; at least one candidate survives |
| B4 | Close the horizontal loop on a grid pattern | G1, G1b, G2 |
| B5 | Warm state: heater solved from its own branch, temperature held at equilibrium, tube emission loading the high-voltage rail. Tube data is `class-typical` for a 31 cm monochrome tube; cut-off is tied to the documented cathode levels (35 V dark, 15 V bright) | G2 still passes with the tube load |
| B6 | **Virtual service procedure.** Bind the remaining controls, then run the manual's adjustment steps (pages 30–32) on the grid with virtual instruments: the meter reads the node the manual names, the ruler reads grid geometry. Each trim is a bounded one-dimensional search to the manual's target. Focus is the setting of smallest centre spot at 20 µA beam current. Freeze | G5; calibration freeze verifies |
| B7 | Render the native full-text frame at full resolution | G1–G8 |
| B8 | Report held-out results and the sensitivity of the frame to each `class-typical` parameter at its bounds; archive under `examples/` and update `README.md` | Report published |

The non-monotonic tuning curve already measured in the isolated oscillator
bench is treated in B2 as a suspected transcription or model error.

If B4 fails while B1–B3 pass, debug in this order: output stage with ideal
drive, closed loop with an ideal flyback reference pulse, full loop.

## Phase C: speed, after the frame

Phase C starts only when B8 is published. The accepted frame and its traces
are then the reference that any faster implementation is checked against.
Nothing here may change a result of Phase B.

| Step | Work | Pass when |
|---|---|---|
| C1 | **Profile.** From the run receipts, split the time of one frame into circuit solve, trace export, trajectories and phosphor | A table of where the time goes, with the largest item named |
| C2 | **Compiled circuit solver.** Generate C++ for this one fixed circuit: fixed topology, fixed time step, device curves as tables, matrix structure worked out once at build time. The netlist and device register stay the single source; the C++ is generated from them, not written by hand | Last-field waveforms agree with the ngspice reference within G6's 1% on every monitored probe; G1–G5 still pass on its output; speed-up over ngspice reported |
| C3 | **GPU for the optical stage.** Electron trajectories and phosphor deposition are independent per sample, so they suit a GPU. Do this only if C1 shows the optical stage is a large share once C2 is in | Image agrees with the CPU render within G7's 2%; speed-up reported |
| C4 | **Decide on real time.** With C2 and C3 measured, state how far one frame is from the 19.5 ms field time and whether real time is reachable with a reduced model | Written assessment |

If C2 cannot meet the 1% agreement at a fixed step, keep it as a fast preview
solver with its error stated, and keep ngspice as the reference.

## Fallbacks (decided in advance)

A step has failed when its gate is still missed after (a) one re-read of the
stage's transcription against the page images and (b) a sweep of its
`design-derived` and `class-typical` parameters across their bounds. Then:

- **A5/B3, no T3 candidate survives:** the hypothesised winding graph is
  wrong. Regenerate candidates from function alone (which terminal feeds which
  rectifier or load). If that also fails, use an equivalent T3: an ideal
  multi-winding transformer with the A5 ratios and class-typical leakage,
  capacitance and loss.
- **B1 or B2 fails:** replace only the failing sub-stage by an equivalent
  source that reproduces its documented test-point waveform.
- **B4, no lock with every test point in range:** use a behavioural phase-lock
  stage for this frame.
- **After A1, more than about 10% of frame-path entries changed:** re-run the
  existing stage benches before B1.

- **Anything else:** a blocker with no entry here gets the same treatment.
  Record what failed and what was tried, substitute the smallest equivalent
  that reproduces the documented behaviour at that stage's boundary, and
  continue.

Every equivalent stage is named in the result label and in the B8 report. An
equivalent stage is not final: if a later re-read or stage result explains the
failure, restore the component-level stage and re-run the gates from there.

## Status before the 2026-11-19 agent-review migration

Phase A tooling exists but still demands human marks (A4 above). A1 stands at
227 machine-confirmed and 33 open entries, with no second netlist. A2 has 77
identity-only devices. No stage has been scored. The
connected grid runs under `build/monitor/phase-a/` are startup diagnostics of
an under-damped T3 placeholder and establish nothing about the sustained
state; they are not to be extended.

Next, in order: A4 tool change, A5 design point, A2 device models, A1 second
netlist and open reads, A3 connected waveform scoring, A6 register, then B1. A5 comes
early because it is cheap and its result tells A1 and A2 which parts matter.
Phase C (speed) waits for B8.

## Phase A goal completion blocker (2026-11-19)

**Goal completion blocked reason:** The page-3/4 source read corrected
the V19/V1 mapping and local wiring, but it did not close the independent
netlist or transistor C/E review. The 300 and 600 dpi T3 reads still cannot
establish the proposed X1:3-to-X2:3 return or internal tap order. Its eight
surviving flyback-sign candidates depend on that unverified winding graph, so
A5 cannot freeze the ratios, polarities or complete design point. A2 still
has eight assembled horizontal-board magnetic devices without register
entries; both page-9 centring chokes now have provisional models in the
ideal-rail assembly. The last archived loaded A3 diagnostic, run
before the new transistor proxies, failed TP8's manual voltage range and did
not establish field-to-field periodicity. A refreshed A3 score is missing. A6
still lacks bounds for frame-path values. Only A4 meets its done condition.
Because the tracked goal requires all six Phase A items documented, committed
and pushed, the pushed partial results cannot complete it.

This blocks **completion**, not further implementation: no human approval or
hardware measurement is needed. Use the bounded fallbacks above, but keep
unverified connections, generic device aliases and conditional stage results
labelled as such. The remaining done-condition gaps are:

| Item | Evidence still needed for completion |
| --- | --- |
| A1 | Finish the independent page 3–4 and 9–10 pin comparisons beyond the now transcribed local branches and page-9 centring bridge, including transistor C/E polarity and remaining page-edge traces; record conditional alternatives for any T3 connections that the scan cannot settle, settle page 18's six functional model-scope gaps and connected contrast check, and close page 16's source-observation check. The installed E1–E4 pair is not identified. |
| A2 | Model and bound every frame-path device. Fifty-six of 64 instances have provisional register coverage; eight assembled horizontal-board magnetic instances have none. Both page-9 centring chokes are now present, but their original values and connected sensitivity remain unqualified. None of the 56 closes every qualification check. |
| A3 | All 17 manual waveform shape descriptors are registered; score connected stages with the required loaded probes, stimulus and recorded trims. |
| A5 | A conditional vertical current/voltage calculation exists. Resolve or explicitly bound the T3 tap/return graph, freeze the winding ratios and polarities, and qualify the complete tube/yoke design point. |
| A6 | Complete cited bounds for the remaining tube, T3, yoke and other frame-path model values; the current register has 190 partial entries. |

All five printed `1SA20C` instances and both `1SC60A` instances now use
separate [BC546B-class NPN model aliases](circuits/k7222-11-small-transistor-models.cir)
with cited parameter bounds in the A2 and A6 registers. The
[isolated class check](reference/k7222-11/small-transistor-class-check.json)
passes nominal gain, saturation and transition-frequency comparisons against
the [onsemi BC546B data sheet](https://www.onsemi.com/download/data-sheet/pdf/bc546-d.pdf).
This is a class comparator, not a claim that either printed type is a BC546B.
Original ratings, every printed-arrow read, connected current/voltage/thermal
stress, joint bounds and implicit BJT defaults remain unqualified. The eight
assembled devices without register rows are L1, L3, three L4 sections, T1,
T2 and T3 on board 012-6921. Both 012-6931 L1/L2 centring chokes now have
bounded provisional RL models in the source-addressed
[page-9 bridge sheet](circuits/k7222-11-centering.kicad_sch). The
[independent source comparison](reference/k7222-11/page9-centering-comparison.json)
matches nine local component terminals; the
[isolated bridge check](reference/k7222-11/centering-bridge-check.json)
passes both conditional link polarities. The installed E1–E4 pair, original
choke construction and connected-stage effect remain open. The earlier
midpoint-neutral current-source equivalent has been replaced by this branch.

The [page-4 V20 source read](reference/k7222-11/page4-v20-source-read.json)
and [page-3 R11/R37 read](reference/k7222-11/page3-r11-r37-source-read.json)
now distinguish V19 on page 3 from V1 on page 4. The source routes `12P` to
R38 left/R39 upper, V19's upper lead to R39 lower and parallel R40/C34 left,
and the lower return to V6/V19/V20. The assembled branch includes V19 and
V20, with its R38/R39/R40/C34 feeds corrected. Separately, page-4 V1 has its
R3/upper lead on `35P`, base fed by R1/R3, and lower lead on the KRS contrast
line. R11.2 runs from `12P` to `sync_feed`, R11.1 from `sync_feed` to
`sync_c`, C33 bridges those nodes, and R37 biases `sync_c` from `12P`.
An [isolated DC polarity comparison](reference/k7222-11/page3-4-transistor-polarity-functional-check.json)
supports the current lower-emitter NPN assignment for V6/V19/V20: its
`h_feedback` output swings 12.0 to 0.044 V under two input states, whereas
reversed NPN and PNP alternatives swing less than 0.6 V. The separate V1
check gives a 21.19–24.80 V KRS adjustment over the R4 range; the PNP
alternative stays near 35 V, and reversed NPN enters unqualified reverse
base-emitter bias. This is functional support for four local C/E assignments,
not a printed-arrow read or an original-device fit. The C/E assignments and
class transistor models remain provisional;
original device parameters, connected stress, the full page-3/4 comparison
and a connected contrast score remain open.

The former V10 lower-return and V1-to-`00` mismatches were cropped-label
errors: the page-3 right transistor is V19; V10 is in the upper oscillator
and V1 is on page 4. V10's separate `h_reactemit` network and V1's KRS lower
lead match the source reads. The fresh export matches the corrected local
branches, while the complete page-3/4 graph, transistor polarity and T3
connections still need source review, not a human reading or physical
measurement.

These are independent completion failures, not just one T3 issue. The
[device-model coverage report](reference/k7222-11/device-model-coverage.json)
records the A2 gap, and the [design point](reference/k7222-11/design-point.json)
explicitly remains partial rather than a calibration freeze. The
[Phase A evidence log](phase-a-evidence.md) records conditional stage results,
not a completed connected A3 score. Resolving the T3 connection review would
unblock the A5 calculation, but it would not by itself close A2, A3 or A6.
The tracked goal can be marked complete only after each row above has its
required evidence and the final results are documented, committed and pushed.

The former `LM709_FAMILY` P09A substitute failed a basic isolated DC follower:
the [reproducible check](reference/k7222-11/lm709-dc-follower-check.json) gives
12.54258 V output for a +1 V input at ±15 V and 2 kΩ load. It has been
replaced in the live assembly by the labelled `P09A_EQUIV` fallback, keeping
the source compensation connections. The
[isolated class check](reference/k7222-11/p09a-equivalent-class-check.json)
passes eight nominal LM709C-class response and rail-current checks, with
provisional parameter bounds in A2/A6. The printed P09A identity is still
unknown. The [connected diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic-p09a-equivalent.json)
passes loaded TP7 at 2.159 Vpp, but TP8 is 25.767 Vpp against the manual's
17 V ±25% guideline, and Y1 is still not field-periodic. A3 and the remaining
A2 qualification therefore stay open; the failed transistor proxy is kept
only as historical evidence.

This blocks declaring the tracked goal complete; it does not require human
review, hardware or permission. Another independent source read may resolve
T3; otherwise its possible connection graphs must remain explicit, conditional
alternatives while the stage is tested. The bounded `class-typical` fallback
applies to unprinted electrical parameters, not proof of wiring. Keep the
unverified graph and sign candidates labelled conditional until the remaining
Phase A evidence is recorded. The detailed evidence and route to completion
follow.

The latest page-4 review at 300 and 600 dpi confirms only the external T3
drive path already checked by the
[flyback-sign comparison](reference/k7222-11/t3-flyback-sign-filter.json):
X2:7 meets V18's collector and V17's cathode, V18's emitter and V17's anode
return to ground, and X2:4 is the other drive-winding endpoint. That comparison
does not independently establish the internal tap order or the X1:3-to-X2:3
return. The [winding graph](reference/k7222-11/t3-winding-hypothesis.json)
therefore remains a hypothesis; its eight surviving sign candidates cannot
serve as evidence that A1 or A5 is complete. The next source review must settle
or explicitly bound those connections before the T3 design point can be frozen.

The decisive technical uncertainty within A1 is the T3 winding topology.
Manual page 19 names
X1:1 and X1:16 as the high-voltage winding terminals; schematic page 4 puts
V21 between X1:1 and the X1:2 EHT output. The model now uses those terminal
roles, with X1:2 outside the magnetic graph. The provisional X1:3-to-X2:3
return and other tap continuity and polarity still lack an independent
pin-to-pin source check. A page-4 functional read now matches T3 X2:7 to
V18's collector and V17's cathode. An isolated positive collector pulse
selects eight of sixteen relative-polarity candidates in both magnetic
backends. This screens only the HV sign within the current unverified tap
graph. The A5 winding ratios, remaining polarities and candidate list
therefore cannot be frozen. The isolated startup
trials in `phase-a-evidence.md` neither resolve the remaining pin map nor
demonstrate the documented 11–12 kV sustained EHT.
The page-4 HV source edges now have a fresh KiCad-export comparison: T3 X1:1
meets V21's anode, V21's cathode reaches EHT, and X1:16 remains a separate
winding terminal. This partial check leaves the return and winding questions
above open.

The immediate route to resolution is A1's independent pin-to-pin transcription
of schematic pages 3–4 and 9–10, plus the remaining panel-control interconnect
checks on page 18, diffed against the KiCad exports and re-read where they differ.
Page 16 already has a complete pin comparison; its source-observation check
remains open. The source readings must settle the remaining T3 connector and
return paths before the T3 portion of A5 can be frozen. Where the
documents cannot settle a parameter, the A1/A5 bounded `class-typical` route
applies; the plan does not require a human or a physical measurement.
A source-first page-9 read now matches all 16 pins in the seven-part 5.1 V
reference branch, including the zener, transistor and capacitor polarities.
A separate source-first read matches all eight endpoints of R3/C2/C1/R20 in
the vertical sync input. Its enlarged crossing review confirms that SYNC does
not join the 0 V return bus. The remaining page-9 circuit and page 10 still
lack a complete second netlist.
A page-10 driver-and-output read now matches 26 terminals of
V18/V19/V20/V21/V26/V27/V28/R27/R29/R48 and X2 in a fresh KiCad export. It
checks all six V27/V28 terminals, all three bias-diode directions, R48's feed
to the V20/V21 junction, and the R29 shunt/R27 sense return between Y1, Y2
and 0 V. Printed arrows confirm the modeled upper NPN/lower PNP assignment;
the contradictory handwritten BD labels remain unverified. The rest of page
10 and its connected-stage function check are still open. A separate A3 read
now matches all eight active physical amplifier pins and seven C26/C27/R54/R48
compensation/output terminals in a fresh KiCad export. The functional symbol's
1–8 pin numbering is explicitly mapped to physical 3, 4, 5, 6, 9, 10, 11,
12. This closes that local connection check, not P09A model qualification or
the remaining page-10 netlist.
An additional page-10 feedback read matches ten scoped terminals of
A3/R43/R45/R46/R47/R27/X2 in the
[fresh comparison](reference/k7222-11/page10-feedback-comparison.json).
The page-14 parts list confirms the three checked feedback resistances.
R44 is already the 160 Ω ramp-output divider resistor on page 9, not a
second page-10 feedback part. The rest of the page-10 input, supply and
feedback paths remain outside this partial check; the TP8 failure is still
unexplained.
The page-18 source transcription now has all 18 labelled board-cable pairs
compared at both physical connector pins in fresh KiCad exports. Twelve signal
nets occur on both corresponding functional board models; six have model-scope
gaps. Vertical-board X2's six pins, four yoke terminal labels and assembled
winding endpoints match a separate page-18 comparison. A source-first panel
read now matches R1's represented topology and R2's corrected two-wire
rheostat between the board R4 left/wiper node and V1 emitter. All six main-board
X1 physical pins match a fresh KiCad export. Six board-cable signals still have
functional model-scope gaps, and the connected contrast stage has no score;
A1 page 18 therefore stays open.
An independent page-16 neck-board read now matches all 39 component pins and
six diode directions in a fresh KiCad export. Three audit-only connector
symbols now expose all 17 physical pins in that export, and every pin matches
the source read. The page-16 source graph has DC routes and an isolated bench
shows plausible transistor switching and cathode response. The A1 page mark
still awaits a source-observation check: that bench has no CRT emission and
cannot reproduce the page-16 C15 dark/bright measuring-cable note.
The current audit flags 26 frame-path part entries; all 26 now have agent
readings or bounded class-typical decisions. T3's two page-4 reads establish
its line-transformer identity, not its turns, internal winding connections or
polarity. V18, V21, V27 and V28 now have bounded `class-typical` candidates,
while their full connection reviews remain open on pages 4 and 10; the local
driver, bias-diode and output-pair pin check above is complete.
Seven converter-only entries are
outside the A1 gate.

Other required close-out work is also missing. The A2 coverage report counts
64 frame-path device instances in 30 printed-type families. Fifty-four have
provisional device-model register coverage (seventeen individual devices, fourteen
1AE15 diodes across two active model aliases, eight 1AD50 clamp diodes, six
horizontal diodes, two KFY18 transistors and seven BC546B-class proxies);
eight assembled magnetic instances
have no entry. V19 on 012-6921 is now assembled; L1/L2 on 012-6931 remain
absent from the current ideal-rail assembly. None of the fifty-four instances yet closes all
A2 parameter checks. The V18 horizontal-output model now passes a BU508AF-class
DC gain and saturation proxy; its inductive switching, parameter bounds and
connected-stage stress remain unchecked. A separate current-fed turn-off
diagnostic shows that its transfer interval is sensitive to model TF and TR;
it does not reproduce the data-sheet inductive timing test.
The page-9 V3 reference zener now passes a BZX84-C5V1-class 5 mA voltage and
differential-resistance comparison. Its original ZC5.1 rating, omitted TT
parameter and connected-stage stress remain open.
The three other active frame-path zeners now pass corresponding BZX84-C6V2,
C9V1 and C16 class comparisons at 5 mA. Their CJO and TT model parameters
are explicit and bounded, but historical identities, the TT range and
connected-stage sensitivity are not qualified.
The horizontal 1AL25 signal diodes and four 1YL1 flyback rectifiers now have
explicit breakdown models and nominal class comparisons for forward voltage,
reverse leakage, capacitance and recovery. The three printed 1YL1 suffixes
still share one provisional model; their factory ratings and connected-stage
stress are not established.
The V13 horizontal-driver model now passes broad SF128-family DC gain and
saturation comparisons and a 15 MHz transition-frequency proxy. The printed
SF1280 suffix is unresolved; inductive storage/fall, other simulator defaults
and connected-stage stress are still unqualified.
V10 now has its own SC237E group-E model instead of sharing V12's lower-gain
`HOR_N`. At the historical bias points, its gain, typical saturation and
transition-frequency proxies agree with the group-E data; V12's `HOR_N`
passes broad SF126-family gain, saturation and frequency checks. The second
SF1260 instance in the 5.1 V reference branch uses a separate `REG5_NPN`
alias; its provisional family gain, saturation and frequency checks now pass.
The printed suffix, connected-stage stress, joint parameter bounds and
implicit simulator defaults remain open for these transistors.
The two original-type KFY18 PNP instances now have a shared bounded model
entry. Its isolated gain, 150 mA saturation, 50 mA frequency and reverse-bias
junction-capacitance checks match the
[1987 Tesla catalog](https://teslakatalog.cz/download/tesla_katalog_2_1987_bw.pdf)
test points. The
connected-stage current, voltage and thermal stress, joint bounds and implicit
SPICE defaults remain unqualified.
Vertical V18 now has a separate `SF127C_N` model rather than sharing the
unidentified `1SA20C` oscillator alias. Its isolated group-C gain, saturation
and frequency proxies pass the historical SF127 family limits; the rest of
the page-10 pin review, connected stress, joint bounds and simulator defaults
remain open.
The active MAA723 ramp-amplifier proxy now has a provisional register entry
linked to the Robotron `MAA723H`/`uA723` family comparison and TI's 723-family
limits. Its former 200 µA drive ceiling let a 5 V class fixture collapse to
2.31 V at a 50 mA load. Bounded error-amplifier drive now gives 4.988 V at
50 mA, 4.985 V at 150 mA, 7.15 V reference and 2.30 mA standby in the
[isolated check](reference/k7222-11/maa723-model-check.json). The printed type
lacks the cross-reference's H suffix; internal device
defaults, dynamic response, current limiting, connected-stage stress and joint
bounds remain unqualified. The earlier TP7/TP8 diagnostic below predates this
model revision; the refreshed diagnostic is described after it.
The waveform scorer now supports separately loaded SPICE solves for the bounded
EO 203 probe equivalent and records an explicit grid stimulus choice. The
[earlier vertical-stage diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic.json)
records trims and separate TP7/TP8 probe solves at the native 19.5 ms field
period. TP8's loaded 18.31 Vpp passes its 17 V guideline and both shapes pass;
TP7's loaded 1.74 Vpp fails its 2.5 V guideline. The stimulus is a synthetic
field pulse, and a 2.29 V Y1 reset difference remains between late adjacent
fields. This is not a grid-stimulus or sustained connected-stage A3 score;
the remaining points and complete A3 comparison stay open.
The [refreshed loaded diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic-maa723.json)
uses the revised MAA723 proxy with the same nominal trims and synthetic
19.5 ms field pulse. TP7 rises to 1.8718 Vpp, just below the 1.875 Vpp lower
bound of the manual's ±25% guideline; TP8 passes at 18.7763 Vpp. Both shapes
pass. Adjacent late fields still differ by 2.61 V at Y1 reset (13.9% of its
swing), so periodic steady state is not established. These are conditional
stage diagnostics, not a native-grid A3 score.
That diagnostic still used the failed `LM709_FAMILY` P09A proxy. With the
labelled `P09A_EQUIV` fallback, the latest
[pre-class-model loaded diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic-p09a-equivalent.json)
at the native 19.5 ms period gives TP7 2.1594 Vpp (pass) and TP8 25.7674 Vpp
(fail against 17 V ±25%); both shapes pass. Y1's late-field reset differs by
0.5972 V, or 2.32% of its 25.768 V swing. This remains synthetic-sync and
nonperiodic, not the complete connected grid-stimulus A3 comparison.
The class-typical register collects
190 cited bounded entries, but tube emission/heater, T3 parasitics, yoke
sensitivity and other frame-path model values still lack sourced bounds (A6).
All three A4 controls are now bound in the ideal-rail
assembly: horizontal-centering R4 uses the conditional page-9 bridge,
R5 uses a declared rail equivalent, and external R1 uses the
page-3/4/18 pot connections. Their effects have not been measured on a grid;
the A1 independent netlist check may revise provisional connections.
The partial A5 calculation also exposes a narrow tube/yoke geometry constraint:
the default 40 mm yoke field clips before the documented half-width, while a
12 mm internal neck aperture exceeds a B31-G family outline's outside radius.
A 34.7 mm active-field trial narrowly reaches the width in the reduced model,
but the inner tube clearance and yoke extent remain unverified. These are
recorded in `phase-a-evidence.md`; the connected grid startup traces do not
establish a sustained-state solution.
A separate reduced-geometry vertical calculation now finds about 0.281 A peak
current for the documented 145 mm picture height at 11.5 kV, with an ideal
linear-ramp yoke voltage swing of about 13.7 V. Its height-only range is
0.254–0.307 A at the manual's ±15 mm tolerance. The current is conditional on
the assumed 40 mm field, 10 mm internal neck aperture and 20 mH/10 Ω yoke;
TP7/TP8 are separate terminal-voltage guidelines and do not measure that
differential waveform. The source-checked 3.9 Ω R27 converts the TP7 2.5 Vpp
guideline to 0.641 App of total sense current (0.471–0.818 App with TP7 and
R27 tolerances). R29 and the feedback network also return through R27, so
this is not a direct yoke-current target. The calculation advances A5 but
cannot freeze it.

To clear the completion blocker, finish the independent pin-to-pin comparison
of pages 3–4, 9–10 and 18, close page 16's source-observation check, resolve
the T3 terminal and return-path differences from source evidence, and record
bounded assumptions where the scan cannot settle winding parameters.
Then complete and verify the A2 device
models, A3 probe/stimulus scoring, A5 design point, and A6 bounded register
against their done conditions above. This requires more implementation and
source review, not an external dependency or a human measurement; the ground
rule and fallbacks above still apply.

## What the result may be called

A frame that passes with no equivalent stage is a **documented-reference
K7222.11/.21 frame**: anchored to the manufacturer's manual, with ideal supply
rails and declared class-typical values. With equivalent stages it is a
**documented-reference frame with equivalent stages**, and the stages are
listed. Neither is a measurement of any physical monitor.
`full_monitor_qualified` and `specimen_validated` stay false.
