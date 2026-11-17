# Robotron monitor circuit lab

**Status: working experimental pipeline; historical K7222 reconstruction is not
complete.** The included 30-component circuit is a driven flyback fixture. It is
not the K7222 SP2/SP3 circuit and must not be presented as the museum specimen.
See `sources.json` for the reference documents, SHA-256 identities, revision
boundaries and unresolved evidence. Original PDFs are not redistributed here.
The expanded search found the earlier **K7222.11/.21 schematic and parts-list
set**, plus its matching operating manual. See [reference evidence](reference-evidence.md)
for page locations and revision boundaries. These findings do not change the
experimental fixture into a historical circuit.

The reference implementation now includes the **012-6891 neck-board circuit**,
its 19 source-designated entries, bounded device assumptions, parameter-endpoint
sensitivity runs, and named-probe replay. The 260-entry inventory accounts for
the three board lists. Input conditioning, sync filtering and a standalone vertical
oscillator are also connected; the full boards and their interconnect are incomplete.
The assembly drawing identifies B31G22 / AE9VT 6802.01 for this reference.

## Steady-supply single-field work (experimental, acceptance still blocked)

The new `steady_supply.py` connects captured VIDEO/BSYN/INTENS through the
1715W output drivers and cable, input/neck circuits, horizontal oscillator and
output stage, vertical timing/output, actual 5 V regulator, and a held-temperature
CRT load. Only converter switching is replaced by ideal 12/22/41/-16 V rails.
Horizontal and vertical winding currents, flyback feedback and electrode voltages
are solved by the circuit. There is no prescribed scan current or framebuffer.

The source audit now includes 247 of 260 entries; this count is **not** a complete
or validated monitor. The steady-supply assembly uses 206 historical entries,
excluding the converter/input supply network. Nine unimplemented input-board
entries and other assembly details remain outside this experimental path. T3,
T1/T2, L4 mutual coupling, yoke parameters and semiconductor families still need
work. The new output transcription explicitly distinguishes R29 (2.7 kohm feed)
from R28 (1 Mohm brightness potentiometer) in the selected older BOM variant.

The one-field selector requires adjacent identical complete fields with active
VIDEO. Initialization may repeat that captured field, and the report explicitly
calls the preceding history an assumption. It does not require a cold heater
simulation or sixteen output fields. The earlier long local capture accidentally
used S600 keyboard firmware as its boot ROM and contained no active VIDEO. The
replacement capture uses S550: its observed field is 19.5 ms (about 51.28 Hz),
with 312 lines at 16 kHz. Always derive timing from the selected capture.

```sh
python3 verification/robotron-monitor/capture.py \
  --rom /path/to/s550.bin --prom /path/to/cas.bin --disk /path/to/tosm10.img \
  --output build/monitor/native-s550.json
python3 verification/robotron-monitor/full_path.py \
  --mode steady-supply-frame --runtime build/monitor/runtime-clean \
  --capture build/monitor/native-s550.json --candidate auto \
  --output build/monitor/steady-screen --wall-budget-hours 12
```

**This entry point currently screens circuits; it is not a finished accepted-frame
command.** It exits 2 with a report of measured failures and unfinished acceptance
work. Each candidate can run 4, 8, 16, 32 and 64 continuous fields, retaining the
last four for examination. Attempts restart from their DC operating point, not a
purported electrical checkpoint. Runtime/inputs/decks and parameter assumptions
are archived. Trial timeouts and the whole-run wall budget are enforced. Starting
LC/RC tuning estimates follow native timing; `--parameter NAME=VALUE` supplies
explicit bounded overrides. No candidate becomes a historical transformer winner.
`--linear-solver klu`, `--reltol`, `--abstol` and `--max-step-ns` expose numerical
experiments without changing physical component values. `--magnetic-parameters`
archives an explicit alternative winding parameter document.

The optional `reference/k7222-11/t3-ac-loss-parameters.json` uses a passive
one-pole R/L winding-loss network. It preserves DC resistance and total
low-frequency leakage while allowing higher AC copper loss. Analytic impedance
tests verify that behavior; its numerical values are unmeasured hypotheses,
and it is not the default or a validated transformer model.

The heater equilibrium is solved from the actual simplified branch (12 V, R22,
temperature-dependent heater resistance and the passive two-node heat model).
The assembled simulation independently measures heater power. Field checks
compare three phase-aligned waveforms, core flux, scan/reset counts, phase drift,
EHT/current bounds and heater heat balance. Electrical timestep refinement,
trajectory-interception feedback into electrode loads, integrated optical
acceptance, and reusable frame caching are still unfinished in this runner.

### Actual connected diagnostic image

[Example image](examples/steady-supply-diagnostic/frame.png) and
[its evidence report](examples/steady-supply-diagnostic/example.json) are from the
connected circuit, not the driven flyback fixture. The image is a narrow, dim band:
it exposes unresolved scan/field scaling and settling rather than demonstrating
a faithful monitor picture. The report records the rejected warm-state checks.

The archived [ngspice deck](examples/steady-supply-diagnostic/run.cir) embeds the
native captured signal edges. Four fields (78 ms) took about 213 seconds; rendering
the last field through compiled trajectories took about 362 seconds with pixel-area integration on this run.
These are measured times for this hypothesis, not a real-time performance claim.
The 4 mH horizontal yoke hypothesis avoids the severe supply loading seen with
0.4 mH; neither is a measured AE9VT value. Electrical inductance and optical
field-per-ampere are not jointly calibrated.

`steady_trace.export()` preserves the solved final-field samples with interpolated
exact endpoints. Its output remains diagnostic. `periodic_frame.run()` computes
periodic phosphor excitation analytically, including electrons arriving across
the field boundary. It writes one PNG, linear float32 irradiance, periodic optical
state and energy/provenance reports. This state is not an electrical checkpoint.
The example assumes this **unsettled** electrical field repeats for phosphor
initialization; it is not an accepted sustained warmed frame. `periodic_frame.compare()`
compares intact single-frame archives in linear irradiance without registration
or exposure fitting, including power-conserving 2x spatial projection. Pixel areas integrate arriving
energy directly; midpoint ray intervals are subdivided at pixel crossings. This
removes the old resolution-dependent bilinear footprint. On this diagnostic field,
halving the trajectory step and time interval gives a relative image error of
2.79e-7; doubling both image dimensions gives 1.37e-7 after area projection.
Both pass the 2% optical threshold, with energy residual below 1.5e-13. These
checks do not establish electrical accuracy. A tighter electrical timestep fails
in the default sparse solver; KLU and a bounded AC-loss winding hypothesis have
not yet produced an accepted refined, settled trace. A 16-field run stopped at
234 ms with a shared-core timestep failure. An exploratory KLU/AC-loss run with
warm electrode-voltage guesses completed four fields in 175 seconds, but still
showed 0.254 line of phase drift (limit 0.01) and nonperiodic EHT/yoke waveforms.
These voltage guesses are not a saved periodic electrical state.

```sh
python3 verification/robotron-monitor/steady_trace.py --raw trace.raw \
  --start .0585 --end .078 --output diagnostic-field.csv
python3 verification/robotron-monitor/periodic_frame.py \
  --trace diagnostic-field.csv --output diagnostic-optical --assume-periodic
```

These commands deliberately produce a diagnostic optical replay, without
asserting electrical settling or a specimen diagnosis.

## Fault atlas development bench

```sh
python3 verification/robotron-monitor/atlas.py \
  --output build/monitor/atlas --members 16 --held-out 8
```

The generator creates a versioned, checksummed `public/` package for the museum's
`fault-atlas.html`. Keep the complete native output directory for individual
solver logs, snapshots, decks and ensemble samples. Output directories are never
overwritten. `--scenario rail-low` and `--scenario rail-high` exercise the external
neck supply; they do not simulate the monitor's 12 V converter. `--fault ID`
selects a subset for development. The catalogue is in `atlas/catalogue.json`.

Faults address original board/component identities and leave the authored sheet
unchanged. Supported discrete mutations include resistance/capacitance scaling,
additional ESR, resistive leakage, terminal opens/shorts, and per-device BJT gain
degradation. Derived resistors retain their source target and purpose. Healthy
parameter variation and injected faults are separate records. Documented passive
tolerances and assumed device bounds are explored jointly using seeded Latin
hypercube samples; these are parameter exploration, not probability distributions.

Every published prediction requires a complete nominal/training/held-out ensemble,
a half-timestep check, and (for opens/shorts) a tenfold change in both directions
to the numerical resistance approximation. Checks compare time-weighted window
features at 1% relative tolerance with numerical floors of 1 mV / 0.1 µA; these
floors are not instrument accuracy or service limits. Predictions from failed or
indeterminate cases are withheld. Unsupported converter, connector and flyback
faults remain visible with reasons. These checks cover settled feature windows,
not every transient excursion. Transition-only faults can be indistinguishable.

Sampled feature intervals report mean, RMS, extrema and peak-to-peak variation.
Pairwise overlap and independent held-out combinations explicitly retain ambiguity
and samples outside their own training envelope. There are no diagnostic scores,
probabilities or automatically recommended live measurements. No real-monitor
faults have validated these predictions. The browser distinguishes source probes
from simulation-only quantities and retains source pages and reference points.

The diagnostic neck bench adds finite external supply/wiring impedance and a
separate healthy C1 ESR. It still uses external supplies and a constant tube load.
**This package does not meet the planned first-release gate:** the complete
power-input → horizontal drive → flyback → loaded-rail circuit is not connected.
`publication_gate.first_release_eligible` remains false independently of numerical
success. Detailed beam modeling and guided diagnosis remain deferred.

`magnetics.py` provides a separately tested shared-core transformer building block
using ngspice's `lcouple`/`core` models ([manual, §§8.2.21–22](https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf)).
Windings share one magnetic loop with explicit resistance, leakage inductance and
terminal capacitance. A shorted turn is an additional closed electrical winding.
The monotone, odd B(H) curve models reversible saturation, with an aggregate
loss resistance. Tests check energy, polarity, saturation, a shorted-turn response
and numerical refinement. This is not yet wired into historical T1/T3; their
parameters remain unresolved. Hysteresis and distributed resonances are excluded.

## Power-controller implementation status

The provisional [TDA1060 functional model](devices/README.md) now includes a
self-running timing-capacitor oscillator, feedback PWM, finite output drive,
undervoltage hysteresis and input inhibits. Manufacturer evidence, calibrated
constants, assumed constants and unsupported behavior are listed separately.
Explicit subcircuit pin contracts allow its 16 terminals through the KiCad
exporter without silently dropping pins. It is used in the provisional
converter bench below, but is not published as a diagnostic prediction.

The pale/expanding-raster implementation remains incomplete: the original
converter, horizontal and vertical stages are not connected. The thermal bench
below integrates heater/emission loading with the neck board, but does not
integrate the monitor's power or scanning circuits. Thus
there is still no model result distinguishing internal electrolytic degradation
from flyback faults for the reported symptom. Passing controller tests does not
satisfy the full-monitor release gate described above.

## Continuous neck/heater lifecycle

```sh
python3 verification/robotron-monitor/lifecycle.py --output build/monitor/neck-warmup
python3 verification/robotron-monitor/lifecycle.py --output build/monitor/neck-warmup-refined --step .025
```

This separate bench solves the exported 19-entry neck circuit and a coupled
heater/cathode model continuously from cold to 300 seconds. Heater electrical
power heats two thermal masses; conduction and radiation remove heat. Emission
depends on cathode temperature and electrode voltages. Anode and grid currents
return to the electrical cathode and load the neck circuit. The old constant
beam-current and socket-capacitance loads are replaced, not counted twice.
All tube parameters in `electrothermal.py` are bounded engineering assumptions.
The external 10.7 V heater and 11 kV anode supplies are bench stimuli, not solved
monitor outputs or proof of the installed tube's operating conditions.

`lifecycle.json` records elapsed checkpoints at 1, 2, 5, 10, 20, 30, 60, 120,
180 and 300 seconds, named fields, parameter bounds, fault mutation, coverage,
source/deck/sample hashes and solver settings. Checkpoints read one continuous
trajectory; they do not restart the circuit. The manifest remains `incomplete`
on solver failure or timeout. A completed **bench run** is explicitly distinct
from full-monitor qualification. Checkpoints are observations, not restartable
solver state files. No multirate approximation is used.

DC video/intensity permits a slow thermal characterization; this is not a raster
simulation or an averaged scan. Capacitor ESR is constant, and the supplies are
external. Width, height, focus, phosphor brightness and flyback behavior are not
predicted. Raw samples and this versioned manifest remain separate from replay
v1/v2; their existing contracts and browser limits are unchanged.

The tests cover warm-up, blanking, cooldown, electrode-current balance, thermal
energy balance, the connected neck lifecycle, and 1% timestep refinement.
These are numerical/component checks, not validation against a real monitor.

Fault operation `capacitor_degradation` accepts `capacitance_factor` (at most 1)
and `esr_factor` (at least 1) on the same source-addressed capacitor. It requires
an explicit healthy ESR and adds only the excess resistance. For example:

```json
{"target":"012-6891:C1","operation":"capacitor_degradation","capacitance_factor":0.1,"esr_factor":10}
```

Supply this JSON with `lifecycle.py --fault FILE`, or through the existing
`reference.run(..., fault=...)` API for switching-window checks. Healthy ESR
assumptions are now inserted from the profile's `parasitics` list, preserving
their source target and parameter. An unmodeled capacitor is rejected; it does
not become a negative diagnosis. Leakage remains a separate fault operation.

Run the 15-case C1 matrix (C ×0.5/0.1/0.01, ESR ×3/10/30, separately and
jointly on the same capacitor), plus nominal and numerical refinement:

```sh
python3 verification/robotron-monitor/investigations/check_capacitors.py \
  --matrix --output build/monitor/capacitor-matrix
```

This matrix holds other parameters nominal. It is not the planned 64-training /
32-held-out full-monitor ensemble. Leakage is not combined into this matrix.

## Reference stage workflow

```sh
python3 verification/robotron-monitor/reference.py --output build/monitor/neck
python3 verification/robotron-monitor/reference.py --output build/monitor/neck-window \
  --start .0001 --stop .0004 --parameter q_bf=18
python3 verification/robotron-monitor/sensitivity.py --output build/monitor/neck-sensitivity
python3 verification/robotron-monitor/trajectory.py --output build/monitor/rays.json
```

`profiles/k7222-11-neck.json` selects the editable KiCad sheet, external bench,
model cards, named probes and finite parameter ranges. The circuit is read from
KiCad on every run. `SourceId` retains original board/designator identity even
when KiCad/SPICE references differ. Duplicate, missing and foreign identities
fail. The bench supplies voltage at the neck connector; these sources are not a
substitute for the missing power and deflection boards. The cathode load is a
constant 20 µA test load, not a modeled tube or heater.

Runs snapshot source files, profile, inventory, code and generated deck with
hashes. Recording windows retain absolute times and integrate from zero; they
do not restart the circuit at the recording boundary. The runner bounds both
saved samples and estimated integration steps. It is not yet a multirate
thermal/lifecycle solver. Parameters outside the declared ranges are rejected.
`sensitivity.py` runs each endpoint separately and reports time-weighted mean,
RMS and extrema. These are neither confidence intervals nor joint worst cases.

Coverage is reported independently of successful simulation. The neck board
accounts for 19 entries; 241 other board entries remain unconnected. Assembly
interconnects and spark gaps also remain outside this bench. A successful neck
run always has `bounded-stage`, never full-monitor qualification.

`trajectory.py` is a separate field-solver prototype: relativistic Lorentz
integration through a parameterized gun/lens potential and a smooth finite yoke
field, nine launch rays, curved-screen intersection, clipping and energy-error
diagnostics. Its JSON output retains the actual paths and assumptions. Tests
cover conservation, polarity, voltage dependence and spatial-step refinement.
It is **not yet coupled** to either electrical runner or phosphor replay. Its
electrode geometry, field shape and beam distribution remain assumed; they have
not been bounded/calibrated as a B31G22 model. Existing fixture playback still
uses `optics.py`.

## Local workflow

Requires Python 3.10+, ngspice (tested with 45.2) and KiCad CLI (tested with 10.0.6).
No Python dependencies or server are needed. From the repository root:

```sh
python3 verification/robotron-monitor/lab.py --output build/monitor/my-baseline
python3 verification/robotron-monitor/lab.py --output build/monitor/my-collapse \
  --name 'Vertical drive removed' --set V3=0
python3 verification/robotron-monitor/lab.py --output build/monitor/my-focus \
  --name 'Focus divider changed' --set R10=40meg
make test-monitor
```

Open `replay.mcrt` in the museum's `monitor.html` page. Import and comparison
operate entirely in the browser. Existing runs are never overwritten. Inspect
`report.json`, `connectivity.json`, `run.cir`, `samples.txt`, and both tool logs.
A failed run retains `FAILED.txt` and does not produce an accepted replay.

Copy `circuits/fixture.kicad_sch` before experimenting. Edit it in KiCad, including
connections, values and additional components, then pass `--schematic PATH`.
Connectivity is exported by KiCad, not read from a parallel hardcoded circuit.
The `Purpose` properties identify each element. `make_fixture.py` bootstraps the
reference fixture only; it is never run by the simulation workflow.

The initial adapter supports numbered R/C/L/D/Q/V/B/I primitives; Q pins are
collector, base, emitter and two-terminal parts follow SPICE terminal order.
Use simple named nets and `0` for ground. Keep the output-probe contract below
when rewiring. Model cards and transformer coupling are in `fixture-models.cir`;
copy and pass `--models PATH` to change these. Unsupported primitives and missing
pins fail explicitly. Local SPICE decks are trusted local code, not sandboxed
input; the browser only reads the bounded binary recording.

R3 is the EHT bleeder, V3 is vertical drive, V4 video, R9/R10 the focus divider,
L1/L2 the coupled windings, L3/L4 the horizontal/vertical yokes, and B1 the beam
load. The probe contract is collector/anode/focus/cathode voltages, L3/L4 currents
and B1 current. Adding arbitrary devices requires a supported SPICE model;
changing these probe names requires updating the adapter, not guessing mappings.

## What the fixture models

Individual resistors, capacitors, inductors, diodes and generic bipolar transistor
models are solved by ngspice. Coupled windings include leakage through a coupling
coefficient and explicit secondary loss; a damper diode and resonant capacitor
participate in horizontal retrace. EHT is rectified into a capacitor with bleeder,
focus-divider and beam loads. Video drives a transistor cathode stage. B1 uses a
bounded, assumed emission law and loads the EHT rail inside the solver.

This fixture deliberately has ideal drive sources. It does **not** implement the
K7222 sync separator, free-running oscillator, vertical amplifier, power converter,
booster network, tuned multiwinding transformer or core saturation. The generic
transistors are not SU165/SSY20A device qualifications. Its heater stimulus is
accelerated to exercise the pipeline and is not a physical warm-up prediction.

The optical model computes momentum from acceleration voltage, a uniform-yoke
magnetic kick, a paraxial trajectory and intersection with a spherical phosphor
surface. A parameterized focus error changes the Gaussian spot size. Inputs
outside the optical model's angle/spot domain produce no visible landing; they
do not become a fabricated centered spot. Energy deposition conserves the
in-screen portion; exponential phosphor decay is evaluated in simulation time.
Display exposure is fixed across experiments. This is not a 3D field solve or
measured B31 tube/lens/phosphor model. Screen shape and optical parameters remain
estimates separate from canonical museum CAD.

## Emulator input capture

```sh
make build/robotron-monitor-capture
python3 verification/robotron-monitor/capture.py --rom ROM2048 --prom CAS256 \
  --disk DISK --output capture.json
python3 verification/robotron-monitor/lab.py --capture capture.json \
  --output build/monitor/captured-video
```

Omitting `--chargen` retains the initial character generator, which firmware may
subsequently populate; alternatively supply exactly 4096 bytes. The wrapper
records ROM/PROM/disk/optional-font and native executable hashes. The runner mounts the disk
read-only. Boot ticks are CPU ticks. New captures use `dac-monitor-input-v2`
and a 179.712 MHz integer timebase: 45 ticks per CPU cycle and 13 per dot.
The observational adapter serializes the core's row-latched glyphs without host
RGB frames or changes to machine state. E03 connector INTENS is inverted HGLT.
BSYN follows the transcribed E05 one-shots, E07 four-line shift register and E04
latch, rather than treating blanking as sync. Nominal one-shot duration is 1060
ticks (approximately 5.9 µs); this is schematic-derived logic, not measured
propagation or temperature behavior. A stopped raster produces a valid static capture.

Events are `[tick, VIDEO, BSYN, INTENS]`, with initial state at zero and a final
duration sentinel. Revision, qualification, assumptions and time origin are
mandatory in v2. Capture observes up to the last 40 ms of boot to initialize
sync state. Pixel content still inherits the core's row-latched rendering; reset
and register-write observation retain CPU-cycle resolution. No emulator state
layout or browser core ABI changes. Legacy v1 remains readable by the original
VIDEO-only fixture; it cannot qualify the new three-signal path.

## Loaded computer-to-monitor signal path

See [source audit and model boundaries](reference/1715w/README.md).
The separate bench connects source-addressed KiCad output, 012-6921 receiver,
012-6931 vertical input filter and 012-6891 neck sheets. It uses finite output
impedance and slew, distributed cable R/C, a shared return resistance, T200
input loading, input clamps, sync buffering and intensity/contrast conditioning.
The horizontal phase-control and vertical oscillator are outside this bench;
their loads are explicit bounded resistors. Supplies remain external.

```sh
make build/robotron-signal-pattern test-robotron-video-output
build/robotron-signal-pattern highlight > build/monitor/signal-highlight.json
python3 verification/robotron-monitor/signal_path.py \
  --capture build/monitor/signal-highlight.json --output build/monitor/signal-one
python3 verification/robotron-monitor/verify_signal_path.py \
  --capture build/monitor/signal-highlight.json --output build/monitor/signal-checks
python3 verification/robotron-monitor/export_signal_path.py \
  --verification build/monitor/signal-checks/verification.json \
  --case nominal --output build/monitor/qualified-video-path.mcrt
```

Patterns: black, white, alternating dots, bars, checkerboard, synthetic text and
highlight. Each uses the shared output logic. They are declared synthetic, not
firmware captures. Fault cases independently change driver strength/slew, cable
capacitance, return resistance, sync presence/width, intensity state, input clamp
leakage or sync bias. Exact interventions are recorded in the generated deck and
input snapshot; they are exploratory severities, not diagnosed component values.

Every run archives source inputs, effective stimulus, exported netlists, solver
logs, hashes and metrics. A failed solve stays incomplete and has no usable
replay. The verifier compares 0.5 ns and 0.25 ns sampling, and four versus eight
cable sections, over 60 µs. Acceptance requires 1% agreement with 1 mV/100 ps
absolute floors, identical edge counts and no disappearing measured features.
The exporter requires both nominal and selected-case acceptance and binds that
result to the recording's hashes. Numerical convergence does not establish
physical accuracy. A single run is explicitly unqualified numerically.

Metrics include extrema, mean, threshold edge counts, median rising-edge
interval (`period_s`), median high width and 10–90% rise time. These characterize
the recorded waveform; an interval is not necessarily a clock period or sync
lock. The browser overlays computer connector, monitor connector and receiver
output on common timestamps, with each voltage's return reference identified.
There are no inferred screen dimensions, brightness or flyback diagnoses.

## Replay contract

`.mcrt` consists of magic `DACCRT1\n`, a little-endian uint32 JSON header length,
UTF-8 metadata and contiguous binary chunks. Version 1 stores source/model/deck/
tool hashes, changes, electrical inventory, solver settings, limitations and an
explicit `experimental-fixture` qualification. Each chunk has payload-relative
offset, byte length and SHA-256. Frame chunks are 160×112 unsigned-byte phosphor
luminance with simulation timestamps. One trace chunk contains little-endian
float64 rows: time, collector V, anode V, focus V, horizontal A, vertical A,
cathode V, beam A, x m, y m, spot sigma m, and landing-valid flag.

Viewer limits: 64 MiB total, 1 MiB metadata, 250001 trace rows, 2001 frames, one
second simulated duration. Hashes detect corruption, not source authenticity.
The parser rejects overlap, truncation, non-finite samples, invalid time ordering,
unexpected dimensions and unsupported versions. It never follows recording URLs
or interprets recording text as HTML. Seeking uses recorded simulation time and
does not integrate phosphor again at browser frame rate.

## Historical reconstruction still required

- Independently review the transcribed .11/.21 parts lists and matching operating manual.
  Its 012-6921/012-6931/012-6891 boards must remain separate from the
  .13/.23 012-6922/012-6934/012-6952 boards and the unrelated MON 3 drawings.
  The .13 scans still omit most values; the two-page redraw is incomplete.
- Transcribe 012-6921 and 012-6931 and the assembly interconnect as hierarchical
  KiCad sheets; independently review the neck sheet and protection gaps.
  Retain historical designators and explicitly unresolved values.
- Establish transformer winding polarity and taps, inductances, losses, core
  saturation, distributed capacitance and yoke characteristics. Do not tune them
  merely until the screen looks plausible.
- Implement all missing circuit stages, including flyback energy recovery and
  supply coupling, and qualify startup, shutdown, sync loss and component faults.
- Establish device, tube and phosphor models from datasheets/measurements; compare
  documented service waveforms and numerical refinement independently.
- Calibrate the schematic-derived output/receiver models against service data and
  specimen measurements before claiming accurate physical connector voltages.
- Add historically qualified recordings and map their nodes to the museum's
  specimen geometry only once that board/tube identity is established.

Numerical tests establish fixture behavior, not historical or specimen accuracy.

### Replay version 2

The stage runner writes `DACCRT2\n`, the same header/chunk framing as v1, with
`start_time`, `end_time` and elapsed `duration`. Trace fields are named and carry
units plus original source identifiers. The first field is always time in
seconds; column counts are declared, not inferred from a fixture. Metadata
includes effective parameters, their declared ranges and source coverage.
Electrical-only stages have no phosphor frames. The viewer explicitly shows
that absence and disables fixture-specific line/frame stepping. Comparisons
match model/source identity and unit, using absolute time. New atlas probes have
stable IDs; older v2 recordings fall back to source ID and name within one model.
Version 1 remains supported within its separate fixture contract.
V2 limits are 128 fields, 250001 rows, 120 seconds absolute end time, and the
same 64 MiB file / 1 MiB header budgets. Trajectory JSON is a separate prototype
format; v2 does not yet carry trajectories or a schematic picking map.

## Electrical-trace optical backend (partial full-path implementation)

`beam_render.py` takes SI electrical samples through the existing nine-ray
relativistic trajectory integrator and an energy-accounted phosphor surface.
Input columns, in order, are `time,anode_v,grid2_v,focus_v,cathode_v,horizontal_a,vertical_a,beam_a`.
Beam current is current entering the modeled gun after separately modeled grid
capture, before trajectory interception. Electrode voltages share a reference;
the cathode voltage is subtracted once. There are no framebuffer pixels or
prescribed beam coordinates in this interface.

```sh
python3 verification/robotron-monitor/beam_render.py \
  --trace electrical.csv --output build/monitor/optical-run --frames 3
python3 verification/robotron-monitor/full_path_audit.py \
  --output build/monitor/full-path-audit-new
```

The first command produces PNG, linear little-endian float32 optical power
(W/m²), provenance/energy reports and a v3 replay. Exposure is fixed, never
normalized per frame. Optical efficiency, decay and tube fields are explicit
assumptions, not measured luminance or calibrated B31G22 behavior. The solver
subdivides electrical intervals for temporal resolution, beam displacement and
clipping transitions, includes electron flight time, and accounts for retained,
emitted, clipped, intercepted and in-flight energy. Failed exports never publish
a final replay. A run starts with an empty phosphor surface unless an explicit optical state is
restored. An absolute 300 s timestamp does **not** establish a 300 s warm-up
simulation or electrical/thermal continuation.

The audit exits 2 while blocked. It currently exports nine KiCad sheets and
counts **171 of 260** historical entries connected. This is coverage, not
qualification. See `reference/k7222-11/full-path-requirements.json` for the
remaining power, horizontal, vertical assembly, tube-loading, settled initialization and
validation gates. **No complete-monitor picture or warm-up sequence is claimed.**

### Vertical oscillator and source correction

`profiles/k7222-11-vertical-oscillator.json` runs the 11-component V5/V11
oscillator from the original schematic and operating manual p13, figure 8.
Its external 12 V source and C12 stand-in are explicit bench fixtures; the
sync filter, MAA723/output and yoke are not attached. The assumed 50 kΩ R22
setting and generic transistor model produce about 24.33 ms free-running period
and 10.5 V swing. Tests check startup, trim direction and timestep refinement;
this is not a calibrated field rate or a demonstration of synchronization.

That same manufacturer explanation confirms V6's cathode faces R28 and its
anode faces V5 base. The sync-filter sheet now follows that direction. The
signal-path matrix was rerun after the correction: nine cases accepted,
stuck-intensity withheld. Earlier recordings with reversed V6 are superseded.

### Replay version 3

`DACCRT3\n` retains checksummed framing, with variable 8–2048 pixel dimensions
(up to 1,048,576 pixels), square pixels, fixed display exposure and named traces.
It supports a window up to one second at absolute times up to 3600 s, sparse
recorded ray paths and at most 120 generated frames, within bounded memory/file
budgets. Linear exports are separate artifacts. The viewer consumes recorded
images and paths, and rejects comparisons with mismatched display parameters.

The only accepted v3 qualification is `experimental-optical-bench`, with
`full_monitor_qualified: false`. This version is a backend test contract, not a
way to promote an arbitrary electrical trace to historical monitor accuracy.
Each renderer instance is single-use. Optical continuation is implemented below;
electrical/thermal continuation and multirate warm-up remain unfinished. No synthetic v3 recording is installed as the museum default.

### Additional transformer search, 2026-11-17

The [annotated K7222 horizontal-stage drawing](https://www.robotrontechnik.de/ablage/forum/K7222_HK.jpg)
corroborates external X1/X2 connections in the existing .11/.21 scan. Its colored
annotations obscure details and do not establish every internal winding section
or relative polarity. The [combi-vision 310 scan](https://www.tiffe.de/Robotron/misc/combivision-310.pdf)
was inspected and rejected as a replacement winding map: page 8 identifies
**ÜHA75**, not ÜHA78. Both downloads are hash-indexed in `sources.json`.
The original T3 winding/polarity specification remains unresolved; repair-coil
turns and modified cold-end wiring are not silently substituted for it.


## Connected-stage and candidate work

The source audit now gives all 260 inventory entries an explicit disposition:
171 connected/modeled entries and 89 unresolved implementations. “Modeled” means
connected in an audited source sheet, not validated as part of a complete assembly.
Assembly completeness, candidate topology and historical qualification remain
separate gates. No missing component is marked assembly-only just to improve a
coverage count.

The stage runner accepts `additional_schematics` in a profile. Every sheet is
archived and exported through KiCad; net labels join the exported circuits.
Repeated source identities or SPICE references fail before simulation. This
allows assembly of existing sheets without copying their components or retaining
duplicate bench loads.

```sh
python3 verification/robotron-monitor/reference.py \
  --profile verification/robotron-monitor/profiles/k7222-11-vertical-sync.json \
  --output build/monitor/vertical-sync-new --stop .30 --step 2e-6
python3 verification/robotron-monitor/reference.py \
  --profile verification/robotron-monitor/profiles/k7222-11-regulator5.json \
  --output build/monitor/regulator5-new --stop .06 --step 2e-6
```

The vertical profile connects the original sync filter to V5/V11, with exactly
one C12 and no dummy oscillator-input resistor. Synthetic finite-impedance field
sync begins at 40 ms. The current model locks to a 20.8 ms period; removing sync
from 90 to 150 ms permits approximately 24.68 ms free-running intervals before
reacquisition around 248 ms. Recovery is not instantaneous. The actual receiver,
vertical integrator, output stage and yoke are still absent from this profile.

The seven-component V4 regulator profile transcribes R9/R10/R11, V3/V4 and C7/C5.
R9 is a three-terminal potentiometer with the original 100-ohm total resistance.
With assumed midpoint trim and generic transistor/zener models, the load-step
bench produces approximately 5.10 V at 20 mA and 5.01 V at 80 mA, then recovers.
C5 is 1000 µF; the earlier C8/47 µF assignment is superseded (C8 belongs to
converter soft-start). The load steps now occur at 100/200 ms to allow startup
settling. Tests also cover lower input voltage and timestep refinement. The complete
switching converter, transistor heating and device SOA remain outside this bench.

### Explicit T3 hypotheses

```sh
python3 verification/robotron-monitor/transformer_candidates.py \
  --output build/monitor/t3-candidates-new
```

This emits 16 relative-polarity candidates for one explicitly hypothetical
five-group winding/tap graph. A global magnetic polarity reversal is canonicalized
away. **This is not an exhaustive enumeration of internal topologies**: the scan
order/continuity hypothesis itself remains unverified. The factory drawing is
still missing, and external bridges must be separately transcribed/reviewed.

`compile_model(graph, candidate, parameters)` generates a shared-core SPICE
subcircuit with individual tapped sections. Each numerical turns/resistance/
leakage/capacitance value requires bounds and a rationale; the function does not
invent T3 values or choose a candidate. Synthetic ngspice tests verify tapped
voltage ratios, polarity reversal and reflected load. These are tests of the
compiler and magnetic model, not simulations of the real transformer. The audit
records candidates as unevaluated, and no full-path candidate replay is published.

### Optical continuation

`beam_render.py --state PREVIOUS/optical-state.json` resumes the previous optical
window. Every successful render now saves phosphor excitation, cumulative energy
ledgers, pending electron arrivals, geometry/resolution settings and the final
electrical row. The new trace must start with that same row; incompatible settings,
corrupt energy accounting or a time discontinuity are rejected. Checkpoint JSON
is data only and is bounded to 64 MiB.

Continuation tests compare a split trace with an uninterrupted trace, including
electrons in flight across the boundary. Images, linear power and energy ledgers
agree. This is **optical state only**: no electrical solver history, magnetic
state or thermal continuation is implied. Verified multirate full-monitor warm-up
and fault-family diagnosis are still unimplemented.

## Full-field firmware preparation (full-circuit rendering still blocked)

`capture.py` now defaults to 1,382,400 dot ticks (100 ms). It still captures native
VIDEO/BSYN/INTENS edges, not RGB pixels, and archives the input/executable hashes.
`--dot-ticks` remains available for an explicit length. Longer capture alone does
not extend the separate 2 ms `signal_path.py` electrical bench.

```sh
python3 verification/robotron-monitor/capture.py --rom ROM2048 --prom CAS256 \
  --disk DISK --output firmware.json
python3 verification/robotron-monitor/frames.py --capture firmware.json \
  --output build/monitor/firmware-fields
python3 verification/robotron-monitor/full_path.py --capture firmware.json \
  --profile k7222-11 --output build/monitor/firmware-preflight
```

The field selector recognizes groups of broad active-low BSYN pulses in the
1715W connector contract and requires ordinary line sync around each group.
Initial/final partial sync groups do not establish boundaries. Selection defaults
to one complete field after one complete pre-roll field; it retains the entire
input and integer timestamps, including video, intensity and blanking events.
Stopped raster, short captures, missing line sync and detected changes in field
period produce an incomplete selection. This is input analysis, not proof that
the monitor has locked. No frames are repeated or rescaled.

`full_path.py` is currently a **preflight entry point only**, not a working
full-monitor renderer. It archives the capture, selected window, circuit audit,
source hashes, requested transformer candidate and actionable blockers. An
optional `--candidate ID` must match the enumerated hypothesis set; it never picks
one by picture appearance. Successful preflight analysis still exits 2 with
`status: blocked`: the connected electrical/thermal solver is absent. It exports
no PNG or replay and cannot promote an optical trace into a firmware rendering.
Assembly completeness, numerical acceptance and specimen validation remain
separate false fields. Failures after output creation leave an incomplete run manifest; invalid profile or
candidate identifiers are rejected before creating the output directory.

### Connected vertical ramp

The `k7222-11-vertical-integrator` profile extends the connected sync/oscillator
bench with 16 source-addressed components from older.pdf p9, including A2, C22,
the height control, V12 and the PNP V13 reset path. The operating manual p14
(Fig. 10) independently explains charging, rapid reset and the height adjustment.
There are 34 components in this connected bench; the full-path inventory audit
now accounts for 171/260 entries across separate sheets, **not one complete monitor**.

A2 uses a provisional LM723-family equivalent with the metal-can pin contract
from TI SNVS765C p2. The reference, differential amplifier, external compensation,
series pass transistor and current-limit transistor are connected; driver source
current comes from V+ and sink current returns to V-. The 7.15 V reference and
1.7 mA quiescent current are family values, not Tesla measurements. Transconductance,
internal pole, gain, output-transistor characteristics and reference resistance
are explicit engineering assumptions in the model. It has no calibrated startup,
thermal, SOA or fault-protection qualification.

C15's original capacitance is still unreadable: the inventory remains unresolved.
The profile exposes an assumed 10–1000 pF range (100 pF nominal), not a claimed
factory value. R35 defaults to 11 kohm within its 22 kohm rheostat range. The bench
still supplies ideal 12 V, synthetic sync and a 100 kohm downstream ramp load.
Tests check a rising ramp, short reset, lock to the imposed field period, height
adjustment, timestep refinement and compensation sensitivity. These checks do
not establish yoke current, screen height or a pale-image diagnosis.

Remaining implementation: converter and horizontal/flyback circuitry, assembly
deflection/yoke coupling, bounded numerical transformer candidates in that
assembly, solved tube supplies/loading, continuous electrical state, settled
operating-point iteration, and full-frame electrical/optical verification. No new
complete-circuit museum screenshot is published by this increment.


### Connected vertical current amplifier

`k7222-11-vertical-output` joins the 34-part timing/ramp bench to 42 additional
source-addressed parts from older.pdf pp9–10. It replaces the dummy ramp load
with A3, compensation C26/C27/R54, the bias diodes, complementary output pairs,
current-sense R27, yoke shunt R29, and nonlinear feedback. Manufacturer operating
manual p15 Fig.12 resolves the chained V23/V24/V25 thresholds and reference
capacitor C23; the other lower-rail decoupler is C21. C26 is **220 pF** per BOM,
not 200 pF from a generic amplifier application circuit. R58 remains a single
source-identified potentiometer with two internal resistances.

A3 uses the LM709 manufacturer internal transistor circuit (SNOS659A PDF p4)
with its external compensation pins, **not a verified P09A model**. Its resistor
values and connections are transcribed; semiconductor gain, capacitance, transit
time and Early voltage are explicitly assumed. Standalone checks cover follower
polarity, settling, load current from the supply pins, compensation sensitivity
and timestep refinement. This does not establish P09A bandwidth or thermal drift.
`additional_models` files are confined to the laboratory, snapshotted and hashed
individually, then concatenated for simulation; no working-directory includes
are needed to reproduce a run.

```
python3 verification/robotron-monitor/reference.py \
  --profile verification/robotron-monitor/profiles/k7222-11-vertical-output.json \
  --output build/monitor/vertical-output --stop .16 --step .00001
```

The external winding defaults to **assumed** 10 ohm / 20 mH, bounded to 2–40 ohm /
2–80 mH. V27/V28 use generic complementary transistor models; the handwritten
replacement types are not promoted to factory identities. The bench still has
ideal +12/+22/-16 V supplies and synthetic sync. Tests check reversing current,
current-loop tracking, the winding differential equation, height/centering
controls and halved timestep. These currents must not be interpreted as measured
raster size, and this stage cannot diagnose the museum monitor by itself.

The audit now covers 171/260 source entries across nine sheets, while the
full-path entry point remains blocked. Converter/horizontal assembly, numerical
T1/T3 candidates, loaded tube rails, settled thermal/electrical iteration and
firmware-frame rendering are still outstanding. No full-path PNG is published.


### Input filter and switching converter

The converter profile connects 38 source-addressed parts on 012-6931, plus
F1/L3/C11 on a separate three-part input sheet. Older.pdf pp9–10 and the operating
manual pp9–10 distinguish raw 12P (controller and R17 supply) from the L3/C11
filtered rail feeding T1 and C10. V2 supplies synchronization, C9/R15 set the
free-running timing, R18/R12/C8 provide soft-start, and R7/R5/R6 close the 41P
feedback loop. V10/V22, snubber, rectifiers and output filters are connected.
The external bench still uses resistive loads and leaves horizontal sync inactive.

T1 is explicitly hypothetical: its four section connections and relative signs
are inferred from the drawing and forward/flyback descriptions, with no original
winding measurements. `devices/t1-bound.json` records assumed bounds for turns,
resistance, leakage, capacitance, geometry, core loss and B(H) scales. The
`converter_magnetics.py` generator produces `devices/t1-bound.cir`; the runner
rejects a stale generated model and archives/hashes its parameters and generator.
This is independent of the unresolved T3 candidates; the two transformers must
not be conflated.

The native shared-flux backend integrates Faraday's law and uses Ampère's law
for magnetizing current. Native E/F sources reflect secondary voltage/current;
all sections share saturation. Synthetic tests compare the unsaturated result
with the existing XSPICE backend, reverse polarity, change load, add a shorted
turn, check terminal power, and refine timestep and saturation-knee smoothing.
The XSPICE backend aborts in the strongly saturated comparison fixture, so it
is not treated as an independent saturated reference. Neither model implements
hysteresis or measured winding resonances.

The converter's automated acceptance currently covers **early startup only**:
source identities/pin order, input filtering, reference startup, nonnegative CX,
output voltage limits in that interval, archive provenance and refinement.
It does not establish settled 41P/22P/16N regulation or synchronization. Long
switching startup remains a numerical/performance gate; aborted or timed-out
runs publish no replay. Logs are preserved incrementally, including on timeout.

```
python3 verification/robotron-monitor/reference.py \
  --profile verification/robotron-monitor/profiles/k7222-11-converter.json \
  --output build/monitor/converter-early-startup --stop .002 --step .000002
```

The full audit counts **171/260 entries across nine sheets**, not a joined
monitor. The first full-path milestone uses thermal-equilibrium iteration followed
by one continuous electrical settle/replay run. Persisted state checkpoints and
fault warm-up sequences are deferred; this does not waive settled initialization,
horizontal/T3/tube assembly, load accounting or full-frame acceptance. The
full-path entry point remains blocked and no new full-monitor PNG is claimed.

### Sustained warmed-up rendering infrastructure

`full_path.py --sustained` requests **16 unchanged native firmware fields**, after
at least eight complete pre-roll fields and seven configured phosphor decay
constants. It fingerprints original VIDEO/BSYN/INTENS transitions; no repeated
or synthesized fields are inserted. `capture.py` now defaults to one second.
The retained one-second native capture selects 16 fields from ticks 36914004 to
91493204 (about 304 ms), after ten pre-roll fields. This establishes source
availability, **not monitor lock or a rendered image**.

```
python3 verification/robotron-monitor/full_path.py \
  --capture build/monitor/firmware-sustained-one-second.json \
  --output build/monitor/sustained-preflight --sustained
```

This still exits 2 with explicit blockers. `sustained.assess` separately checks
24 continuous field summaries (eight settling, sixteen output), positive rail,
EHT, raster and brightness metrics, <1% variation, phase error, unchanged source
content and sufficient phosphor pre-roll. It cannot certify provenance or replace
numerical refinement and image comparison.

`electrothermal.equilibrate` couples settled electrical trial callbacks to the
existing passive two-node thermal network. It records every trial, requires
<0.1% power residual and <1% thermal/electrical changes, and returns temperature
rises without inventing elapsed warm-up time. The model accepts explicit initial
temperatures and a thermal hold mode for trial solves. Tests compare equilibrium
against an independent long transient and release warm initial conditions into
350 ms of continuous thermal dynamics. The **assembled monitor callback is still
missing**; the synthetic heater trial is not a monitor qualification.

`Renderer.render_stream` consumes samples once and delivers frames through a
callback without retaining them. It preserves interpolation, pending electron
arrivals, phosphor excitation and energy accounting; EOF must match the requested
endpoint before a completed optical state can be exported. Explicit resource
budgets remain enforced. `stream_render.py` archives the CSV, writes PNG and
little-endian float32 W/m² frames immediately, spools the replay payload to disk,
and bounds the viewer-only trace preview. Failed/truncated runs leave an
incomplete manifest and never publish `replay.mcrt`.

```
python3 verification/robotron-monitor/stream_render.py \
  --trace electrical.csv --frame-times field-times.json \
  --output build/monitor/streamed-optics --backend compiled
```

`field-times.json` is an ordered JSON array of absolute seconds spanning the
entire electrical trace; the replay window is at most one second. This entry
point remains **experimental-optical-bench**. It does not supply electrical
signals, infer equilibrium, or promote an imported trace to a full-path result.

The optional compiled backend implements the same double-precision RK4 equations,
nine-ray launches, clipping and curved-screen intersection as `trajectory.py`.
It builds with `c++`, without fast-math or floating-point contraction, into ignored
`build/monitor/trajectory-native/`, keyed by source/compiler/flags. Replay reports
include the source and executable hashes. Python remains the independent oracle;
comparisons cover acceleration, reversal, deflection, interception, two spatial
steps, flight time, images and energy. A representative bundle took 190 ms in
Python versus 3.6 ms compiled on this machine; this is not a sustained-render
throughput guarantee.

### Converter performance findings and remaining work

`solver_profile.py` streams native binary raw files and reports accepted-step
density, minimum timesteps, last values, endpoint completeness and available
resource counters. Truncated files remain diagnostic-only; rejected-step counts
are explicitly unknown without instrumented solver counters.

```
python3 verification/robotron-monitor/solver_profile.py \
  --raw build/monitor/converter-sustained-profile/trace.raw \
  --log build/monitor/converter-sustained-profile/solver.log --end .05 \
  --output build/monitor/converter-sustained-profile/inspection.json
```

`reference/k7222-11/converter-performance.json` records the experiment hashes and
results. Original Gear integration reached only 40.067 ms in a 90-second budget;
its 38 ms bin contains 186,336 accepted steps, with a minimum around 1.87 ps.
State probes associate the smallest steps with reset transitions. Trapezoidal
integration and a native-switch substitution did not fix the bottleneck. A
smooth-hysteresis substitute ran faster **by stalling the oscillator**, and was
rejected. No experimental controller replacement is retained in the device model.

Still required before the first sustained full-path image: a performant,
validated switching converter; connected horizontal/T3/yoke circuitry and actual
electrode supplies; coupled thermal trials and interception-current feedback;
continuous electrical/optical settling; and full-run refinement/energy/image
acceptance. Source coverage remains 171/260 across nine separate sheets.


### Pinned monitor solver and controller experiment

`monitor_runtime.py` builds ngspice 47 into an isolated workspace directory. It
requires the exact source archive SHA-256, applies a zero-fuzz instrumentation
patch, and records the compiler, flags, source inputs, binary, startup file and
code-model hashes. `reference.py --runtime DIRECTORY` verifies the receipt before
running a stage and copies it into the stage archive. Builds cannot be moved:
the ngspice startup file contains absolute code-model paths. The installed system
solver and the default TDA1060 device model are unchanged.

```
curl -L --fail https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/47/ngspice-47.tar.gz -o /tmp/ngspice-47.tar.gz
python3 verification/robotron-monitor/monitor_runtime.py \
  --archive /tmp/ngspice-47.tar.gz --output build/monitor/runtime-new --jobs 4
python3 verification/robotron-monitor/reference.py \
  --profile verification/robotron-monitor/profiles/k7222-11-neck.json \
  --runtime build/monitor/runtime-new --output build/monitor/pinned-neck
MONITOR_RUNTIME=build/monitor/runtime-new python3 -m unittest discover \
  -s verification/robotron-monitor/tests -p test_monitor_runtime.py -v
```

Set `CRT_AUDIT_FROM` and `CRT_AUDIT_TO` to log a bounded time window. The patch
records accepted points, Newton/LTE/breakpoint rejection and CAP/BJT/IND timestep
reductions. It does not change those devices' equations or the solver's acceptance
rules. `solver_profile.audit_profile` distinguishes truncation proposals from
rejections, reports the last instrumented limiting device for LTE rejection,
and retains the window and log hash. Counts do not cover time outside that window
or uninstrumented device classes. An accepted point's `next_dt` is a proposed
future step; accepted durations still come from successive raw timestamps.

```
CRT_AUDIT_FROM=.03835 CRT_AUDIT_TO=.03836 \
  build/monitor/runtime-new/install/bin/ngspice -n -b -r trace.raw run.cir
python3 verification/robotron-monitor/solver_profile.py \
  --raw trace.raw --log solver.log --end .039 --audit-start .03835 \
  --audit-end .03836 --output inspection.json
```

Redirect the solver's stdout and stderr to `solver.log` when collecting an audit.
The binary raw writer also supports non-seekable output; a truncated stream still
cannot pass the endpoint gate.

`controller_history.experimental_model` is an opt-in reset-comparator experiment.
It uses analog timestep history for all state, interpolates threshold crossings,
and has a finite 20 ns transition. A crossing tolerance of 0.01% of that transition
prevents repeated backtracking to the same floating-point crossing; both scale
with `tda_regularization`. The tolerance and transition are numerical assumptions,
not measured B260D delays. The initial experiment failed at 8.07373 ms because of
repeated crossing backtracking; the corrected version must still pass connected
converter regulation, load, energy and refinement checks before adoption. Its
presence in the runtime does not qualify it for full-monitor use.


The ngspice-47 37–39 ms diagnostic run reaches its endpoint. Its minimum
accepted interval is 3.035 ps. In the 38.19970–38.19973 ms window there are 54
accepted points, 3 Newton rejections and 29 LTE rejections; the reset-delay
capacitor is the last instrumented limiter for 27 of those LTE rejections.
A separate 38.41525–38.41528 ms window has three LTE rejections limited by T1
leakage/capacitance elements. These are local observations, not whole-run shares.
Both runs produce identical raw electrical payload hashes despite different
logging windows. The step-audit evidence preserves the runtime, deck, raw and
log hashes. Neither run reaches settled converter regulation.

The self-contained decks in `reference/k7222-11/converter-step-audit-decks/`
are immutable experiment snapshots, not replacement source schematics. Their
hashes are checked against `converter-step-audit.json`. They make the rejected
hypotheses reproducible without keeping multi-million-row raw files in Git.
The ten-minute trials ended at 50.229 ms (original) and 41.024 ms (history reset),
both short of the requested 120 ms. Added 10 ohm winding-capacitance loss was
screened separately and together with the history reset, but neither 120-second
screen reached the requested endpoint. These runs establish no regulation or
performance acceptance; no magnetic-loss change is adopted.

### Linear-image acceptance

`stream_render.py` now archives each linear frame's filename, absolute time and
SHA-256, together with the complete phosphor surface parameters and exporter
source. `image_acceptance.py` consumes these archives directly. Old archives
without this metadata must be regenerated; PNGs cannot substitute for linear
irradiance.

```
python3 verification/robotron-monitor/image_acceptance.py \
  --render build/monitor/render-base --refined build/monitor/render-fine \
  --first-frame 10 --output build/monitor/image-acceptance.json
```

Select the first of the sixteen output frames explicitly, after pre-roll. The
gate checks all 120 field pairs in both runs, so gradual drift cannot pass merely
because neighboring fields look similar. Its error is the spherical-cell-area
weighted L2 difference divided by the smaller image norm, with a strict 2% limit.
There is no translation, cropping, brightness fitting or display-space comparison.
Zero, negative and nonfinite images, truncated files, altered input/model/frame
hashes, missing frames and irregular times fail closed. Processing retains only a
bounded number of images, rather than loading a whole recording.

The finer run must use the identical archived electrical trace, optical model,
physical screen, phosphor parameters and frame times, with a uniform integer
resolution multiplier of at least two. Fine cells are aggregated onto coarse
cells by conserved emitted optical power using their curved surface areas. Every
corresponding frame must meet the same 2% error limit. Both temporal and spatial
checks must pass; omitting the finer run leaves acceptance false.

This is an optical-image gate only. It cannot establish original firmware
provenance, electrical or trajectory timestep refinement, thermal equilibrium,
eight stable settling fields, sufficient original pre-roll, or a connected
monitor. Those remain separate requirements. `full_monitor_qualified` and
`specimen_validated` stay false even when image checks pass. Tests exercise an
actual renderer export with accumulating phosphor energy and confirm rejection,
as well as brightness drift, constant-average image motion and refinement errors.

The steady-state initialization implementation is still outstanding. Inspection
of the pinned ngspice-47 `dcpss.c` shows convergence tests on node/branch solution
differences and period adjustment; that is not evidence of complete physical
state restart or the proposed Newton–Krylov solve. `CKTstates`, integration and
solution histories, time/source phase, breakpoints, device-private state and
XSPICE state need an explicit coverage audit and uninterrupted-versus-restored
tests before an accelerated initialization can be accepted. No PSS or node-only
restart is enabled by these image changes.

An additional bounded converter experiment starts the supply at DC and seeds
reservoir, soft-start and controller voltages near an assumed operating point,
then releases them into the unchanged transient equations. It times out after
60 seconds at 0.741358 ms of a requested 5 ms, with 294,331 accepted samples.
`reference/k7222-11/converter-initial-guess-audit.json` records the deck, pinned
runtime, log and raw hashes and endpoint profile; the self-contained deck is in
`converter-step-audit-decks/initial-guess-release.cir`. This is a failed bounded
initial-guess trial, not a state restart, regulation result or comparative
performance benchmark. It does not establish that precharging guessed rails
solves the converter bottleneck. No default circuit/model parameters change.
Repeating the same guess with only the experimental history reset substituted
also times out at 60 seconds, reaching 0.370313 ms with 310,408 accepted samples.
That trial and its separate deck are included in the same evidence record.
Neither controller reaches the requested endpoint or establishes regulation.
