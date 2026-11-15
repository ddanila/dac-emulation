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
the three board lists, but the other two boards are not yet connected or modeled.
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
read-only. Boot ticks are CPU ticks; capture ticks use the declared 13.824 MHz
dot clock. It serializes the emulated row-latched glyphs and intensity, without
using host RGB frames. Its active-low BSYN during modeled horizontal/vertical
retrace is an **unverified adapter assumption**. Rational character timing comes
from the existing core, not reconstructed M/W connector gates. Stopped scanout
fails rather than hanging or publishing a complete-looking capture.

The JSON format `dac-monitor-input-v1` contains integer `clock_hz` and ordered
`events`: `[dot_tick, VIDEO, BSYN, INTENS]`, starting at zero and ending with a
duration sentinel. The current fixture consumes VIDEO only. BSYN/INTENS are
retained for a future historical receiver model and must not be claimed as
electrically simulated. No emulator state layout or browser core ABI is changed.

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
- Qualify connector signals against the computer's display-board circuit before
  calling functional captures accurate monitor-pin captures.
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
