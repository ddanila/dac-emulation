# Plan: one sustained-state frame from the K7222 reference monitor

Written 2026-11-18, revised 2026-11-21. This plan supersedes `README.md`,
`single-frame-acceptance.md`, `phase-a-evidence.md` and
`reference/k7222-11/full-path-requirements.json` wherever they disagree. Those
files stay as the record of what exists.

This file holds the method and a short status. Evidence goes in
`phase-a-evidence.md`.

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

- Switching power converter. The frame uses ideal rails (see "Rails and controls").
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

## Status (2026-11-21)

**Goal blocked reason (2026-11-21): Phase A cannot be signed off.** A5 cannot
produce a bounded, document-consistent design point because the active
19-port T3 model conflicts with the .11 page-4 terminal labels: it omits
X3:1 and X1:2, joins X1:3 to X2:3 where the drawing joins X1:2, and includes
X1:16 without a resolved page-4 mapping. A separate, source-checked 20-pin
KiCad candidate corrects the visible external connections, but its winding
sections, turns, return and drive are still hypotheses. An opt-in connected
20-port assembly now exists; the default connected path still uses the
source-contradicted 19-port model. In the corrected 20-port prescribed-drive
screens, neither
the eight-sign screen (seven completed cases) nor the five-point booster-turn
screen finds a case that jointly matches sampled EHT, TBY7 current and C21.
Those screens are conditional sensitivities, not an installed winding ratio or
periodic operating point. The permitted equivalent-T3 fallback also needs
A5-derived ratios and bounded losses and parasitics, which are not yet
qualified. A1, A2 and A6 remain open; A3 and A4 are done. This is an internal
source, model and evidence gap, not an external dependency or approval wait.
To unblock A5, resolve or bound the X1:16 mapping and internal graph, qualify
the source-corrected connected candidate, then qualify the drive,
returns, yoke transfer and settled C21 voltage before selecting T3 parameters
or the equivalent fallback.
The partial [design point](reference/k7222-11/design-point.json) now binds the
corrected 20-port source read and candidate reports by hash. Its earlier
19-port turn and polarity lists are explicitly historical, and its
EHT/collector calculation is only a conditional voltage proxy.

The .11 scan still does not settle T3's full return graph, tap order or
high-voltage cold end. The
[historical function-only core](reference/k7222-11/t3-functional-core.json) assigns six
of 19 terminals and cannot determine winding ratios; the cross-revision
[TV ÜHA78 bridge](reference/k7222-11/t3-tv-variant-source-read.json) would
bypass the .11 V21 rectifier and cannot supply the missing pin map. The
H2-coupled X2:4 drive waveform has no source-qualified L1/L2 electrical
bounds. The 16/70 mH values in the
[unequal-choke screen](reference/k7222-11/t3-brimar-asymmetric-choke-screen.json)
come from a different tricolor circuit and do not bound the installed chokes.
The [link disposition](reference/k7222-11/t3-centering-link-disposition.json)
effect-bounds E1+E2 versus E3+E4 only within five conditional TBY7 cases;
the installed pair remains unknown and both stay as labelled alternatives.
Without a bounded X2:4 waveform, the documented EHT and collector pulse
cannot establish a T3 winding ratio. The active T3 values remain placeholders.
The [corrected HV-winding comparator](reference/k7222-11/t3-hv-winding-comparator.json)
puts the conditional EHT/collector *voltage* proxy at 17.49–21.78; it is not
an HV/drive turns ratio. The source-unqualified return voltage, loaded drive
pulse and .11 winding graph prevent converting it to physical turns. The
cross-revision 2,409-turn ÜHA78 winding therefore cannot close this gap.

A subsequent [page-4 terminal-identity audit](reference/k7222-11/page4-t3-terminal-identity-audit.json)
found a more immediate A1/A5 model contradiction: V21's pads are labelled
X3:1/X3:2, while X1:2 is a separate T3 upper-bank terminal drawn to X2:3.
The scan visibly names 20 magnetic terminals; the 19-port model omits X3:1
and X1:2, includes an X1:16 not visibly labelled on page 4, joins X1:3 to
X2:3 and relies on
an earlier HV read that conflated the X3 and X1 labels. That read is
superseded. All numerical T3 stage screens using this graph remain historical
sensitivities; even their passing sampled checks cannot qualify an installed
.11 design point. Resolve the manual-only X1:16 mapping, then rebuild the
wrapper, source comparison and affected screens before using them to bound
a ratio.
The separate [20-terminal page-4 graph candidate](reference/k7222-11/t3-page4-visible-graph.json)
now compiles with X3:1 and X1:2 and excludes X3:2/EHT and the page-4-unseen
X1:16. Its four winding groups and section order are explicit hypotheses.
A [committed 20-pin KiCad interface](circuits/k7222-11-horizontal-output-page4.kicad_sch)
and its [fresh comparison](reference/k7222-11/page4-t3-visible-wrapper-comparison.json)
pass 10/10 scoped export checks, including X3:1–V21 anode,
X1:2–X2:3 and both booster link pairs. It is now selectable for an experimental
connected solve with the [explicit provisional section parameters](reference/k7222-11/t3-page4-provisional-parameters.json),
while the default path remains the historical 19-port model. All other
component pin nets are unchanged; no section parameters are qualified.
The magnetic compiler now supports bounded
HV-overwind coupling across multiple candidate sections and passes a
synthetic 20-port solve; this does not qualify the parameter bounds. Resolve
the manual's
connection-16 mapping and source-visible continuity before promoting it.
An [eight-sign 20-port stage screen](reference/k7222-11/t3-page4-visible-stage-screen.json)
transfers the old 1,768-turn comparator to X3:1–X1:1 and assumes two
one-turn bridges. At 20 ms, seven signs solve and one aborts; no completed
case jointly matches sampled EHT, TBY7 current and C21. The two signs near
11–12 kV EHT keep C21 near 23.7 V. This is a prescribed-drive sensitivity
under unqualified section turns and return, not an A5 ratio or sign selection.
A [five-point booster-section screen](reference/k7222-11/t3-page4-booster-turn-screen.json)
scales the three provisional X2:13-to-X2:10 sections from 1.75 to 28 turns
each. All complete at 20 ms, but C21 stays at 1.80–23.75 V and no case
jointly meets sampled EHT, TBY7 current and C21. Changing that one assumed
turn span cannot close this conditional gap; other section, return and
installed-drive alternatives remain open.
Both 20-port screens were regenerated after the connected adapter change;
their input hashes match the current files and their numerical results are
unchanged. This establishes reproducibility of these conditional screens only.

A scoped [page-4 booster comparison](reference/k7222-11/page4-booster-comparison.json)
found that the model had exchanged T3 X2:10 and X2:13: the source connects
V16/C26 to X2:13 and C21's lower terminal to X2:10. The external pins are
now corrected. The [paired tap-order screen](reference/k7222-11/t3-booster-pin-order-screen.json)
shows that this correction changes the conditional stage strongly unless its
unverified internal section order is also changed. The previously reported
T3 stage voltages and rail crossings used the old external assignment and
cannot qualify the corrected model. A5 must carry both tap orders as labelled
alternatives until the actual stage boundary can select a candidate or
support a fallback ratio.
The corrected [20 ms paired result](reference/k7222-11/t3-booster-pin-order-screen.json)
keeps the legacy section order near 3.57 kV EHT and −4.82 V across C21;
the visible-order alternative reaches 11.71 kV but only 23.72 V across C21.
A [four-sign source-order screen](reference/k7222-11/t3-source-order-polarity-screen.json)
finds no joint sampled EHT/current/C21 match. These are fixed prescribed-drive,
single-return cases, so A5 must still bound the drive, returns and installed
yoke transfer before pruning the remaining graph alternatives.
The [source-corrected 39–43 V rail screen](reference/k7222-11/t3-source-order-rail-c21-screen.json)
keeps C21 at only 23.72–26.10 V across four 20 ms cases; 42.504–43 V meets
sampled EHT and transferred TBY7 current while still missing C21. R5-equivalent
rail movement within that comparator interval does not close this conditional
discrepancy. The actual X2:4 drive and winding/return alternatives remain the
next A5 discriminants.
The [six corrected return cases](reference/k7222-11/t3-source-order-return-c21-screen.json)
give zero joint sampled EHT/current/C21 matches at 20 ms. Four keep EHT and
current in band with C21 at 23.72–24.12 V; the open/shared-floating case
raises C21 to 52.85 V but leaves only about 117 V EHT. This narrows the
conditional return choice without proving an installed connection or periodic
state. A later [scoped page-4 conductor read](reference/k7222-11/page4-t3-internal-links-comparison.json)
confirms the drawn X2:10–X1:15 and X2:11–X1:13 pairings already used in the
model; these two links therefore do not explain the C21 gap. Bound X2:4 drive
and the remaining winding/return alternatives before selecting a graph.
A [three-level prescribed-base screen](reference/k7222-11/t3-source-order-base-level-screen.json)
holds the corrected source-order graph and TBY7 return case fixed while
changing only V18's assumed base-high level from 0.8 to 1.8 V. All three
20 ms samples meet EHT and current bands, but C21 remains at 23.70–23.72 V.
This engineering range does not bound the installed base drive or X2:4 pulse.

The [Brimar TBY7 class](reference/k7222-11/yoke-brimar-110deg-comparator.json)
provides a bounded comparator, not an installed AE9VT identification. The
[K7222.25 operating crosscheck](reference/k7222-11/k7222-25-operating-crosscheck.json)
names AE9VT and corroborates the 39–43 V 41P and 60–70 V boost scales in a
later Robotron stage. Its differential reading corrected the partial
design point: 60–70 V is across C21, whose other terminal is at 41P, giving
a conditional 99–113 V trace node. It does not supply .11 winding ratios or
tap order. The
[conditional R5 rail screen](reference/k7222-11/t3-brimar-rail-boundary-screen.json)
crosses its lower-current proxy near 42.504 V with 11.72 kV sampled EHT;
the [six-scenario link/choke screen](reference/k7222-11/t3-brimar-link-sensitivity.json)
keeps that crossing within 42.219–42.570 V after widening its exploratory
L1/L2 lower case to 16 mH. Both use an unverified T3 graph,
exploratory L1/L2 and a prescribed drive. Neither establishes installed
yoke currents, T3 ratios or a sustained operating point. The permitted
conditional [return boundary screen](reference/k7222-11/t3-brimar-return-boundary-screen.json)
screens all six upper-return/cold-end combinations: two fail this
conditional stage's sampled current/EHT checks and four pass at both 50 and
25 ns maximum steps. A [C21 differential probe](reference/k7222-11/t3-brimar-boost-boundary-screen.json)
finds only 23.67–23.70 V across C21 in those four passing cases at the 5 ms
sample, below the .11 page-4 60–70 V annotation; none of the six sampled
cases matches all three current/EHT/C21 checks. A
[20 ms initial-state screen](reference/k7222-11/t3-brimar-boost-settling-screen.json)
brings one passing return case to about 23.7 V across C21 from both its
original 22.5 V and a corrected 65 V start. Thus the short run's initial
voltage alone does not explain that conditional stage's mismatch. It still
cannot qualify the source-connected, periodic .11 operating point. The
permitted
function-derived/equivalent T3 fallback still needs A5-derived ratios and
class-bounded loss and parasitics. A cross-revision U52/54 core statement and
an independent U52/H21 catalog now bound a class geometry, but the .11 core,
gap and material remain unidentified; an area/path-only stage screen misses
the sampled EHT band. A conditional effective-inductance screen shows that
an extra-reluctance gap proxy can reproduce the prior rail case. A firsthand
K7222.25 repair account confirms core spacer plates but gives no thickness;
neither result identifies a .11 core or winding. Switching to the fallback
alone cannot close A5.

**Phase A completion is blocked at A5.** The source-contradicted 19-port T3
graph must be corrected before its numerical screens can qualify a design
point. Within that historical graph, none of six conditional return cases
jointly meets sampled EHT, yoke current and the 60–70 V C21 annotation. The
corrected 99–113 V trace-node range gives only a conditional HV/collector
voltage proxy: the settled C21 voltage, actual collector/drive pulse, T3
tap/return graph and installed yoke transfer are not qualified. The current
conditional stage cannot validate a T3 ratio, and the allowed equivalent
fallback still lacks A5-derived ratios and bounded loss/parasitics. A1's
full-page source comparisons, A2's sourced joint device bounds and stress
checks, and A6's remaining class-typical transfers are also open; A3 and A4
are done. This is
an internal evidence and implementation gap, not an external wait or approval
request. To unblock A5,
carry unreadable connections and both link pairs as labelled bounded
alternatives, bound L1/L2 and the field/current transfer, qualify settled C21
voltage and the actual collector/drive pulse, then parameterize the fallback
and close the other open rows below. Detailed findings and receipts are in
[phase-a-evidence.md](phase-a-evidence.md).

**Keep this section short.** It holds one row per item: what is still unmet
and the next step. Results, numbers and source reads go in
[phase-a-evidence.md](phase-a-evidence.md) and the reports under
`reference/k7222-11/`, not here. Change a row only when its unmet condition or
next step changes. The narrative that used to follow is in
[phase-a-status-archive.md](phase-a-status-archive.md).

The numerical T3 screens cited below are pre-correction historical probes,
except the labelled [pin-order screen](reference/k7222-11/t3-booster-pin-order-screen.json).
Their sampled values must be regenerated for a selected source-corrected
candidate before they can support A5 closure.

| Item | Still unmet | Next step |
|---|---|---|
| A1 | A new page-4 terminal inventory finds 20 visible magnetic labels, including X3:1 and X1:2, and draws X1:2–X2:3; V21 pads are X3:1/X3:2; the earlier X1:1/X1:2 diode read and its comparison are superseded. Second netlists for pages 3–4 and 9–10 are partial: local branches match, the full pages are not compared. Page 16's independent pin comparison and function checks are closed in the source-review gate; its separate unvalued meter cable remains an A6 transfer problem. Page 18 has three model-scope gaps and no working contrast path. The page-10 diode/threshold feedback branch now matches 18/18 selected terminals, but the page-10 C23 schematic/manual conflict is resolved for the model in favor of Fig. 12 by its functional explanation and a <2% paired-stage topology screen; physical board wiring remains unverified. Scoped page-4 X2:4/C31/C32-to-H2/X5:5 and V16/C26/C21-to-T3 booster branches now match fresh exports after correcting the exchanged X2:10/X2:13 model pins; a later two-link read confirms the drawn X2:10–X1:15 and X2:11–X1:13 conductors, but the complete page remains open. Still unqualified: the full T3 return, tap order and HV cold end; T2 secondary phase and return; installed E2 and E1–E4 links; C30 population; L1's crossing with the flyback line. | Finish the pin-to-pin comparisons. Carry each connection the scan cannot settle as a labelled, bounded alternative. |
| A2 | All 64 frame-path instances have provisional register rows; none is fully qualified. The [board-device](reference/k7222-11/a2-implicit-default-audit.json) and [MAA723 internal-device](reference/k7222-11/a2-internal-device-audit.json) audits find zero screened implicit defaults; the latter has 48 provisional A6 parameter bounds. The [exact Tesla MAA 723 catalog](https://teslakatalog.cz/download/tesla_katalog_1_1986_bw.pdf) confirms its no-H 10-pin function map and tighter reference, standby, load and line-regulation limits. The [nine-case corner screen](reference/k7222-11/maa723-internal-corner-screen.json) passes all five exact-type isolated DC comparisons at 25 °C, but four low-pass corners deliver only about 62 mA in a 9.5 V/6.5 V intended-150 mA engineering probe. Its pass-device attribution isolates the provisional BF/IKF lower bounds; restoring both nominal values gives about 150 mA, while the registered drive upper bound does not rescue their low corner. The [vertical stress screen](reference/k7222-11/vertical-output-stress-screen.json) puts V27 mean collector power at 1.775 W, above the BD139 free-air comparator; horizontal V18 exceeds its reverse-base comparator; T3 remains assumed-bound. The period SU 165 limits check only V18's handwritten candidate, not its installed identity or reverse-base rating. Installed package, other device identities, joint bounds, temperature and stress conditions remain open. | Source MAA723 pass/drive behavior or build an externally bounded equivalent; then qualify joint bounds, temperature and connected stress, including V27/V28 thermal/SOA and horizontal V18 drive. |
| A3 | Done: all 17 source-hashed shapes, 2 kByte timing, bounded EO2-equivalent bandwidth/probe loading and the declared grid stimulus are machine-checkable. TP8's 17 V crest is checkable; its separate 10 V annotation stays `reference-incomplete` with an explicit G4 explanation if it remains unresolved. A sustained connected score belongs to Phase B. | None for the Phase A method. |
| A4 | Done. | None. |
| A5 | [design-point.json](reference/k7222-11/design-point.json) is partial. The current 19-port T3 graph omits source-visible X3:1 and X1:2, carries manual-only X1:16 and misassigns the X2:3 upper return; all its numerical stage screens are historical conditional sensitivities until rebuilt. A separate [20-terminal source-visible graph candidate](reference/k7222-11/t3-page4-visible-graph.json) now has an opt-in connected KiCad assembly with explicitly provisional section parameters; it has no qualified turns, return or drive and is not the default model. The external booster pins now match page 4, but the prior six-case stage is historical because it used exchanged X2:10/X2:13 model pins; under that old assignment it gave zero sampled current/EHT/C21 matches. A 20 ms two-initial-state screen brings one return case to about 23.7 V across C21, still below the 60–70 V annotation; no source-connected periodic ratio is qualified. The T3 return/tap alternatives, winding ratios, upper/lower tap signs and installed tube/yoke geometry lack complete bounded arguments. The [function-only T3 core](reference/k7222-11/t3-functional-core.json) retains one of four HV/G1 sign combinations without assuming the scan-order tap graph, but assigns only six of 19 terminals. The [full-graph screens](reference/k7222-11/t3-g1-polarity-filter.json) retain four of 16 candidates within the unverified graph; neither result qualifies turns or returns. A [series-return audit](reference/k7222-11/t3-series-return-audit.json) shows that the current graph reaches ground through X2:5 while X1:16 is not directly grounded, so a cross-revision grounded-footpoint report cannot select X1:16=0. A [scoped X2:4 return read](reference/k7222-11/page4-t3-x2-return-comparison.json), [drive-voltage audit](reference/k7222-11/t3-drive-voltage-audit.json) and [conditional pulse screen](reference/k7222-11/t3-drive-pulse-screen.json) show that the existing EHT/collector proxy cannot fix an HV/drive ratio without a source-bounded X2:4 waveform. A [centring-return screen](reference/k7222-11/t3-centering-return-screen.json) adds the H2 rail path but cannot qualify the waveform with only exploratory L1/L2 bounds. The [link disposition](reference/k7222-11/t3-centering-link-disposition.json) keeps both E1–E4 pairs as labelled alternatives: in five conditional TBY7 choke cases their sampled current, EHT and drive-peak differences stay below 0.02%, though the installed pair and native connected effect remain unknown. A [core-loss material comparator](reference/k7222-11/t3-core-loss-comparator.json) gives a 25 kHz/200 mT reference; the [conditional stage](reference/k7222-11/t3-drive-pulse-screen.json) now resolves 0.198 T maximum absolute flux and 0.723 W in its assumed 10 kΩ loss shunt, but neither qualifies installed 16 kHz loss. The active horizontal 4 mH/2 ohm winding lies outside a cited 31 cm/90° yoke family; a [paired-winding stage screen](reference/k7222-11/t3-yoke-class-stage-screen.json) moves the conditional differential pulse and EHT widely across that family, so the active-stage pulse cannot bound A5 ratios. The [B31-G axial screen](reference/k7222-11/yoke-axial-geometry-screen.json) finds the active 280 mm gun-to-screen path longer than the family's 253 mm maximum overall length. A [neck-clearance screen](reference/k7222-11/yoke-neck-clearance-screen.json) finds the active 10 mm inner radius equals the family's approximate outside neck radius; at a 230 mm path and 25 mm field, full width requires an inner radius of at least 9.365 mm. A [joint screen](reference/k7222-11/yoke-joint-geometry-screen.json) finds three broad-family current matches but zero matches to the sampled winding's own transferred horizontal and vertical bounds. A new [Brimar paired class](reference/k7222-11/yoke-brimar-110deg-comparator.json) supplies 31 cm/110°/20 mm-neck TBY3/TBY5/TBY7 electrical and current comparators; [TBY7 gives 11.51 kV](reference/k7222-11/t3-yoke-brimar-stage-screen.json) in the conditional T3 stage, but the active 2 Ω winding differs from its 8.8 Ω and the class is not an AE9VT identification. A [reduced-ray geometry screen](reference/k7222-11/yoke-brimar-geometry-screen.json) finds zero of nine common-field geometries matching both transferred current bounds. A [class-boundary calculation](reference/k7222-11/a5-yoke-class-boundary.json) supplies TBY7 current and ideal trace-voltage candidates but does not identify AE9VT or its field. A [conditional rail screen](reference/k7222-11/t3-brimar-rail-boundary-screen.json) crosses the transferred lower current near 42.504 V within the R5 equivalent range, with sampled EHT in band; it cannot qualify the T3 graph. A [prescribed-base level screen](reference/k7222-11/t3-source-order-base-level-screen.json) keeps C21 at 23.70–23.72 V across 0.8–1.8 V assumed base-high levels; this does not bound installed drive. | Resolve or bound the X1:16 mapping and upper return, qualify the opt-in 20-port connected candidate against full source comparisons and affected screens, then bound the X2:4 drive and remaining graph; extend the corrected tap-order and four-sign screens across drive, return and yoke alternatives and qualify settled C21 voltage and the collector/drive pulse. Bound L1/L2 electrical behavior; then bound the H2-coupled X2:4 waveform and differential drive pulse while carrying both E1–E4 pairs as labelled alternatives. Carry unreadable internal returns and tap signs as labelled bounded alternatives. Use the TBY7 current/trace-voltage boundary and screened rail range to test the T3 tap, boost and return alternatives, then parameterize the function-derived/equivalent T3 fallback with A5-derived ratios and class-bounded loss and parasitics; source-bound B31G22/AE9VT axis-specific field geometry and installed yoke currents, then check document consistency. Connected EHT/lock and operating-point stress belong to Phase B. |
| A6 | The [register](reference/k7222-11/class-typical-register.json) now bounds live heater cold resistance and electrical temperature slope with a pure-tungsten class comparator, and records a same-size Philips yoke electrical/current class. The new Brimar 31 cm/110°/20 mm-neck paired yoke class has bounded electrical and transferred-current entries. B31G22 material and thermal transfer, emission, G4 effect on cut-off, T3 parasitics, installed AE9VT sensitivity/geometry and the measuring cable remain unqualified. | Add cited bounds for the remaining families and re-run the stage checks they affect. |

Order: A5 (T3 graph or its fallback), A2, A1, A6, then B1. Phase C waits
for B8.

### Findings that stand

Each of these changed the model or how a target is read. Details and reports
are in the evidence log.

- **Contrast and IS.** Incoming INTENS (X9:5), V5's IS output to the neck
  (X3:2) and the HRS wiper at V1's base are three separate nets; the earlier
  INTENS-to-neck passthrough was wrong. IS is active low. With the detailed
  page-3/4 wiring the bright cathode sits near 0.3 V against the documented
  15 V and does not respond to R2. The manual's Fig. 6 terminal assignment
  gives 13–16 V and is available as
  `--contrast-topology manual-fig6-equivalent`. It is a labelled equivalent,
  bound into the calibration freeze, and not the default.
- **T3 (historical 19-port candidate).** The active 1,000-turn HV winding gives an ideal ratio of 15.6. The
  design point needs 28–36, and two cross-revision ÜHA78 reports give 1,768
  and 2,409 turns. Eight of sixteen polarity candidates survive the flyback
  sign check, but only within the now source-contradicted tap graph. Its
  X1:3/X2:3 tie is superseded by the drawn X1:2/X2:3 conductor; the HV
  cold-end connection remains unread.
- **T3 equivalent.** The older passive coupled-winding candidate changes
  with a non-driving flux probe and develops irregular pulses in two bounded
  connected runs. The newer AC-loss, grounded-HV-cold equivalent gives about
  79.7 Vpp TP17 and 11.48 kV EHT on a refined prescribed-drive stage. At
  50/25 ns with a 200 ns base edge it meets stage periodicity and solver
  budget. The labelled connected alternative holds TP17 near 77–78 Vpp in
  its unfinished prefix, but EHT is below 11 kV and the solver stops at the
  two-field input/contrast boundary. Its graph, loss and drive remain
  provisional; neither equivalent is a frozen design point.
- **Horizontal drive.** No prescribed-drive sweep reaches TP15 (36–54 Vpp)
  and 11–12 kV together. With an ideal 45 Vpp TP15 source, the cases that
  reach about 11.3 kV put more than 50 V of reverse bias on V18's base
  against a 9 V class limit, so that equivalent driver is rejected as it
  stands.
- **P09A.** The `LM709_FAMILY` substitute failed a DC follower check. The
  labelled `P09A_EQUIV` fallback is in the live assembly.
- **TP8.** The manual's 17 V is crest-to-zero, not peak-to-peak. Earlier
  pass and fail results against 17 Vpp are void.
- **Controls.** R4 uses the transcribed page-9 centring bridge, which
  replaced the DC-current equivalent. R5 uses the rail-scale equivalent. R1
  uses the page-3/4/18 pot connections. None has been exercised on a grid.
- **Measuring cable.** The page-16 inset has a series capacitor and unvalued
  shunts. A direct DC voltage at X3 cannot stand in for the 0.1/3.6 mV
  service readings.
- **Connected runs.** No native-grid run has completed three locked fields.
  The 50 ns and 200 ns partial runs disagree by 22% on mean EHT over the same
  window, so neither qualifies the other. Horizontal output pulses continue,
  but the TP17-mapped pulse is below the manual guideline in their early
  complete bins. The passive T3 equivalent changes partial-run TP17 amplitude
  but develops irregular collector and pulse bursts, so its EHT and pulse
  swing do not establish a joint steady operating point. Shorter startup runs
  end near 5 kV. None of this is evidence about the sustained state.

`make test-monitor` checks the tools and that saved reports reproduce. It
needs the pinned runtime (`MONITOR_RUNTIME`) and the source PDFs under
`build/`. A green run is not Phase A evidence.

## What the result may be called

A frame that passes with no equivalent stage is a **documented-reference
K7222.11/.21 frame**: anchored to the manufacturer's manual, with ideal supply
rails and declared class-typical values. With equivalent stages it is a
**documented-reference frame with equivalent stages**, and the stages are
listed. Neither is a measurement of any physical monitor.
`full_monitor_qualified` and `specimen_validated` stay false.
