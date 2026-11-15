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

- Review the newly located .11/.21 parts lists and matching operating manual.
  Its 012-6921/012-6931/012-6891 boards must remain separate from the
  .13/.23 012-6922/012-6934/012-6952 boards and the unrelated MON 3 drawings.
  The .13 scans still omit most values; the two-page redraw is incomplete.
- Transcribe and independently review the full reference topology as KiCad sheets,
  retaining historical designators and explicitly unresolved values.
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
