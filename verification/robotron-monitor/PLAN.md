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
netlist and open reads, A3 waveform descriptors, A6 register, then B1. A5 comes
early because it is cheap and its result tells A1 and A2 which parts matter.
Phase C (speed) waits for B8.

## Phase A goal completion blocker (2026-11-19)

**Tracked-goal blocked reason:** The goal requires all Phase A done conditions
to pass, with the results documented, committed and pushed. The partial results
are pushed, but A1, A2, A3, A5 and A6 remain open. Most critically, A1's
independent source-to-KiCad pin comparison has not established T3's winding
connections and polarity. Its X1:3-to-X2:3 return and other taps remain
provisional, so A5 cannot freeze the winding graph, ratios, candidate list or
design point as source-verified. The page-18 check now compares the physical
pins of all 18 labelled board-cable pairs, but six signals have functional
model-scope gaps. A separate comparison matches the yoke connector and four
winding endpoints. The panel read and deck now agree that R2 is a two-wire
KRA/KRS rheostat: KRA reaches board R4's left/wiper node and KRS reaches V1's
emitter. A fresh KiCad export matches all six main-board X1 physical pins;
the connected contrast stage remains unscored.
The source-first page-9 checks cover only the 16-pin 5.1 V reference branch
and eight endpoints of the four-part sync input. Other A1 sheet checks, A2
device-model coverage, A3 waveform/scorer validation and A6 bounded values
are unfinished. The bounded source-review and fallback rules above allow
progress without a human reviewer or physical measurement.

The decisive technical uncertainty within A1 is the T3 winding topology.
Manual page 19 names
X1:1 and X1:16 as the high-voltage winding terminals; schematic page 4 puts
V21 between X1:1 and the X1:2 EHT output. The model now uses those terminal
roles, with X1:2 outside the magnetic graph. The provisional X1:3-to-X2:3
return and other tap continuity and polarity still lack an independent
pin-to-pin source check. The A5 winding ratios, polarity and candidate list
therefore cannot be frozen from the current model. The isolated startup
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
return paths before the A5 design point is calculated. Where the
documents cannot settle a parameter, the A1/A5 bounded `class-typical` route
applies; the plan does not require a human or a physical measurement.
A source-first page-9 read now matches all 16 pins in the seven-part 5.1 V
reference branch, including the zener, transistor and capacitor polarities.
A separate source-first read matches all eight endpoints of R3/C2/C1/R20 in
the vertical sync input. Its enlarged crossing review confirms that SYNC does
not join the 0 V return bus. The remaining page-9 circuit and page 10 still
lack a complete second netlist.
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
while their connections remain in the open page-4 and page-10 netlist reviews.
Seven converter-only entries are
outside the A1 gate.

Other required close-out work is also missing. The A2 coverage report counts
64 frame-path device instances in 30 printed-type families. Twenty-eight have
provisional device-model register coverage (six individual devices, fourteen
1AE15 diodes across two active model aliases, and eight 1AD50 clamp diodes);
32 assembled instances
have no entry. V19/V20 on 012-6921 and L1/L2 on 012-6931 are absent from the
current ideal-rail assembly. None of the twenty-eight instances yet closes all
A2 parameter checks. The V18 horizontal-output model now passes a BU508AF-class
DC gain and saturation proxy; its inductive switching, parameter bounds and
connected-stage stress remain unchecked. A separate current-fed turn-off
diagnostic shows that its transfer interval is sensitive to model TF and TR;
it does not reproduce the data-sheet inductive timing test.
The page-9 V3 reference zener now passes a BZX84-C5V1-class 5 mA voltage and
differential-resistance comparison. Its original ZC5.1 rating, omitted TT
parameter and connected-stage stress remain open.
The waveform scorer now supports separately loaded SPICE solves for the bounded
EO 203 probe equivalent and records an explicit grid stimulus choice. No
connected stage score yet has all required loaded probes or recorded trims (A3).
The class-typical register collects
43 cited bounded entries, but tube emission/heater, T3 parasitics, yoke
sensitivity and other frame-path model values still lack sourced bounds (A6).
All three A4 controls are now bound in the ideal-rail
assembly: R4 and R5 use declared equivalents, and external R1 uses the
page-3/4/18 pot connections. Their effects have not been measured on a grid;
the A1 independent netlist check may revise provisional connections.
The partial A5 calculation also exposes a narrow tube/yoke geometry constraint:
the default 40 mm yoke field clips before the documented half-width, while a
12 mm internal neck aperture exceeds a B31-G family outline's outside radius.
A 34.7 mm active-field trial narrowly reaches the width in the reduced model,
but the inner tube clearance and yoke extent remain unverified. These are
recorded in `phase-a-evidence.md`; the connected grid startup traces do not
establish a sustained-state solution.

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
