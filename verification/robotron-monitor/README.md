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
exporter without silently dropping pins. It is not yet used in a historical
converter profile or published as a diagnostic prediction.

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
a final replay. Every run starts with an empty phosphor surface: an absolute
300 s timestamp does **not** establish a 300 s warm-up simulation or continuation.

The audit exits 2 while blocked. It currently exports four KiCad sheets and
counts **65 of 260** historical entries connected. This is coverage, not
qualification. See `reference/k7222-11/full-path-requirements.json` for the
remaining power, horizontal, vertical-output, tube-loading, continuation and
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
The renderer is single-use; electrical/thermal/phosphor continuation remains
unfinished. No synthetic v3 recording is installed as the museum default.

### Additional transformer search, 2026-11-17

The [annotated K7222 horizontal-stage drawing](https://www.robotrontechnik.de/ablage/forum/K7222_HK.jpg)
corroborates external X1/X2 connections in the existing .11/.21 scan. Its colored
annotations obscure details and do not establish every internal winding section
or relative polarity. The [combi-vision 310 scan](https://www.tiffe.de/Robotron/misc/combivision-310.pdf)
was inspected and rejected as a replacement winding map: page 8 identifies
**ÜHA75**, not ÜHA78. Both downloads are hash-indexed in `sources.json`.
The original T3 winding/polarity specification remains unresolved; repair-coil
turns and modified cold-end wiring are not silently substituted for it.
