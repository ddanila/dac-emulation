# Reference analog simulation

Use the standard S600 ROM and published reference circuit independently of specimen
photographs, replacement firmware and measured timing. Those observations can
calibrate the model later; they are not prerequisites for circuit-model development.

`sense_probe.py` generates the sensing resistor networks and transistor connections
from the pinned KiCad netlist and runs an ngspice DC sweep. It is a backend
feasibility experiment, not a complete board model. The generic PNP parameters,
ideal supply, unloaded outputs and contact resistance are explicit in its report;
they are not claimed SC308 specifications or measured tolerances.

```sh
python3 verification/robotron-keyboard/analog/sense_probe.py
python3 verification/robotron-keyboard/analog/sense_probe.py --beta 50 --contact-ohms 1000 --out /tmp/sense-experiment
```

The output directory contains the generated deck, raw sweep, solver log and report
with input/tool provenance. Changing beta/contact resistance explores assumptions;
it does not qualify a production tolerance range.

## Matrix circuit and HDL interface

`matrix_probe.py` generates the sensing network and an external contact fixture
using X1's numbered row/column connections. Selected columns sink through an
explicit nominal driver; released columns have no invented active high drive.
The test scans individual and shared contacts with single, all and no columns
selected. A graph-connectivity oracle checks thresholded voltages independently
of the production emulator's OR approximation.

```sh
python3 verification/robotron-keyboard/analog/matrix_probe.py
python3 verification/robotron-keyboard/analog/matrix_probe.py --beta 50 --contact-ohms 1000 --out /tmp/matrix-sensitivity
```

The measured DC samples also pass through a generated `controller_analog` HDL
interface to check latch/data-bus mapping and column-drive intent. This interface
reuses the checked structural wiring, replacing only the contact/sense boundary.
The DC comparison checks mapping separately from transient feedback.

The fixture deliberately uses diode-free resistive contacts. Its three-corner
rectangle conducts to a phantom row; that result must not be transferred to the
museum specimen or production emulator without verifying the actual key wiring.
Contact, driver and latch-load values are assumptions retained in the report.

`matrix_cosim.py` closes the live HDL→column sink→contact/sense circuit→HDL latch
loop with a bus stimulus fixture. After building the bridge described below:

```sh
make test-keyboard-matrix-feedback
```

It checks bus reads, analog voltages and timing under timestep refinement, including
released columns and shared-contact paths. The stimulus is a bus fixture, not CPU
firmware. Source/library hashes and failure traces are retained with the report.

## Reset circuit

`make characterize-keyboard-devices` compares the generic NPN model with SC236D
DC gain limits at the data sheet's collector currents, voltage and temperature.
`device_limits.json` pins the archival source and distinguishes DC gain from
small-signal AC gain. The diagnostic records `completed` separately from
`qualified`; append `--require-qualified` when calling `device_probe.py` to reject
a model outside the selected limits. This is a device characterization check,
not full transistor qualification, and does not fit parameters automatically.

The nominal model fails the higher-current SC236D gain limits. A single constant
gain cannot capture the published current dependence. The archived
[SC307–SC309 manufacturer bulletin](https://hjs.lima-city.de/DDR/index.php?pdf=SC307)
also identifies its unqualified typical values as group D; they must not be
silently treated as SC308C specifications. Device fitting, dynamics and
temperature behavior remain open work.

`reset_probe.py` generates the reset passives, diodes and transistors from the same
pinned connectivity, with BR2 connected to the schematic CPU reset pin. It checks
cold start, a power interruption, BR2 isolation and timestep refinement. The
semiconductor models and CPU input load are explicit nominal assumptions; release
timing in the report is a model prediction, not a specimen measurement.

```sh
python3 verification/robotron-keyboard/analog/reset_probe.py
python3 verification/robotron-keyboard/analog/reset_probe.py --beta 300 --rise-us 10000 --out /tmp/reset-sensitivity
```

Generated decks, solver logs and internal-node traces remain available with the
report, including on failure. Sensitivity runs do not establish device tolerances.
The ordinary CI job runs the default reset experiment alongside the sensing check.

## Oscillator circuit

`oscillator_probe.py` wires A7, its RC feedback, clock pullup and BR1 from the pinned
schematic. The continuous NAND macromodel in `ls_nand_nominal.cir` has finite output
impedance, input capacitance, bias and clamps. It contains no clock stimulus or
Schmitt hysteresis. It is an exploratory LS-TTL approximation, not a calibrated
DL000 transistor model, and does not account for gate output supply current.

```sh
python3 verification/robotron-keyboard/analog/oscillator_probe.py
```

The test checks sustained oscillation, CPU-side clock transport, BR1 isolation,
timestep refinement and the frequency response to doubling C6. It reports frequency
without fitting it to the emulator's clock. Passing these checks establishes circuit
integration behavior, not historical oscillator accuracy. Internal-node traces and
model/source hashes remain in the output directory. Device-model qualification and
coupling clock/reset to the firmware simulation remain required.

## Output, cable and supply loads

`output_probe.py` generates serial pullups, LED series resistors, cable-filter
connections and board decoupling from the reference schematic. Its external LED
and receiver fixtures use explicit nominal models. Chokes are uncoupled series RL
surrogates: their inductance, resistance, mutual coupling and ferrite losses remain
uncharacterized. The shield is an open boundary, not an invented ground bond.

```sh
python3 verification/robotron-keyboard/analog/output_probe.py
```

The test checks serial drive/release at the cable receiver, LED current, cable-load
sensitivity and timestep refinement. Reports retain internal rail/return voltages,
receiver rise intervals and signal ranges. Driver intents are ideal test stimuli;
this does not qualify firmware-driven output timing or EMI behavior.

`serial_cosim.py` drives the schematic-mapped 7406 pins in HDL and returns the
loaded cable voltages through receiver models. After building the bridge:

```sh
make test-keyboard-serial-feedback
```

It checks raw bit ordering, receiver data stability around clock edges, cable-load
variation and timestep refinement. The fixture explicitly establishes data before
the write strobe; it does not qualify S600 framing or the CPU data-bus output-enable
timing. A passing transport test must not hide those remaining bus-timing questions.

## HDL boundary

Use ngspice 47/XSPICE and Icarus 13 with `--enable-libvvp`. The ordinary Icarus
executable is not enough. Obtain the [ngspice 47 source archive](https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/47/ngspice-47.tar.gz)
(SHA-256 `894e649651f1838a14095e5a5439e7d3aa63e87ede14d283173fda4fcdef675f`)
and [Icarus v13_0](https://github.com/steveicarus/iverilog/tree/v13_0)
(commit `dfeee909ed9f20b4870dd93423156c0170c0e1ff`). In the Icarus source directory,
with autoconf, a C/C++ compiler, flex and Bison 3 on PATH:

```sh
sh autoconf.sh
./configure --enable-libvvp
make -C vvp -j4 libvvp.so
```

On macOS put Homebrew Bison ahead of the system Bison. Build the bridge from the
unmodified sources, passing the resulting shared runtime explicitly:

```sh
python3 verification/robotron-keyboard/analog/build_bridge.py \
  --ngspice-source /path/to/ngspice-47 \
  --icarus-source /path/to/iverilog \
  --libvvp /path/to/iverilog/vvp/libvvp.so
python3 verification/robotron-keyboard/analog/bridge_probe.py
```

The builder preserves symbol visibility (the local Homebrew bridge hid VPI
registration symbols) and applies `icarus-startup.patch`. The patch samples initial
outputs because constant-folded signals may never produce a value-change callback.
It modifies ngspice's GPL-licensed VPI source in the build directory only.

The probe instantiates the existing 7406 HDL model and transports **sink enable**
to an analog conductance with a pullup and capacitive load. It checks initial
release, low drive, later release, X propagation and a known HDL delay at two
analog steps. Reports retain library/source hashes, solver logs and waveforms.
The electrical parameters are exploratory, not calibrated SN7406 characteristics;
the X conductance is a numerical surrogate, not a physical prediction.

`--direct-z --out /tmp/direct-z-diagnostic` reproduces an unresolved failure with
direct Z transport through `bidi_bridge` when refining the timestep. Do not use
that path for the board. A successful ngspice exit alone is insufficient: the
probe also rejects diagnostics, missing ports and incorrect waveforms. The encoded
interface is qualified only for this unidirectional open-collector probe, not for
shared buses or the full feedback loop. Full-board CPU/ROM qualification remains
separate from this test.

## CPU data-drive boundary

The mixed-signal adapter uses TV80's write-cycle intent, gated by reset and bus
ownership, to drive CPU data. Gating it with WR alone discards data setup and hold.
The [Z80 manual's memory-write timing](https://www.zilog.com/docs/z80/um0080.pdf#page=23)
specifies stable data during WR and retention after it deasserts. This is a sequence
check; it does not establish U880 pin delays or full CPU cycle equivalence.

```sh
make test-keyboard-data-drive
make qualify-keyboard-data-drive S600_ROM=/path/to/s600.bin
```

The fast synthetic test exercises memory and I/O writes and retains WR-only drive
as a failing setup-time control. The longer check reuses the existing S600 firmware
scenarios and compares serial/LED observations with the old boundary. It preserves
the digital matrix for this comparison; physical ROM/bus contention remains outside
its scope. `boot_cosim.py --wr-only-data` retains the old behavior for diagnostics.

The firmware harness also resolves CPU, ROM and latch outputs on the shared data
nets. ROM address/data/CS/OE wiring comes from A8's numbered pins. In particular,
ROM output enable follows the schematic's MREQ connection; it is not silently
suppressed during a memory write. Conflicting digital drivers resolve to X.

```sh
make test-keyboard-resolved-bus
make qualify-keyboard-resolved-bus S600_ROM=/path/to/s600.bin
```

These checks cover reads, address mirroring, release and deliberate contention,
then compare the existing S600 scenarios. They establish digital bus behavior,
not contention currents or calibrated pin timing. `--bypass-rom-bus` restores the
old direct-ROM CPU input for diagnostics. The CPU setup/hold fixture deliberately
uses that bypass to test CPU drive timing separately from board-level contention.

## Coupled firmware boot

After building the bridge, run the longer electrical-clock/reset integration test:

```sh
make test-keyboard-coupled-boot S600_ROM=/path/to/s600.bin
```

`boot_cosim.py` starts the electrical circuits at power-on with BR1/BR2 closed and
runs TV80 with the standard S600 image. It checks reset delivery, the first ROM
fetch, sustained execution and keyboard scanning. Idle S600 need not transmit
without a key stimulus; serial scenarios are qualified separately. The default retains the digital matrix
for comparison. To connect the electrical matrix and latch feedback instead:

```sh
python3 verification/robotron-keyboard/analog/boot_cosim.py --rom /path/to/s600.bin --electrical-matrix --out /tmp/electrical-matrix-boot
```

`--contacts 0,8,9` holds fixture contacts closed from power-on in electrical mode;
it does not identify specimen keys. `--prepare-only` generates inputs and explicitly
leaves the report unpassed. Append `--electrical-outputs` to include serial/LED loads, cable filters and
supply/return paths in the firmware run. The report then records receiver voltages
instead of ideal serial intents. Each mode includes a component model/boundary
inventory; an unknown schematic reference fails generation. This inventory is
coverage evidence, not a claim of device accuracy. CPU/peripheral buses, control
pullup loading, IC supply currents and brownout behavior remain unqualified.
The CPU receives clock/reset through an explicit nominal 1.4 V threshold, without
an X band that could create multiple Verilog clock edges during one voltage rise.

The supply rises over 1 microsecond by default. The nominal reset model fails to
produce a useful pulse with a 10 ns supply ramp; this is reproducible with
`reset_probe.py --rise-us .01 --out /tmp/reset-fast-ramp`. Treat that as an open
model-qualification issue, not evidence about the specimen. `boot_cosim.py` also
accepts `--rise-us` and `--step-ns` for investigation.

The full power-on delay is simulated, although only a tail window is saved to
limit waveform storage. The run is kept outside fast CI and can take much longer than the standalone
probes. Set its wall-clock limit with `--timeout-seconds`. Reports pin ROM, TV80, generated wiring, bridge libraries and analog sources;
solver logs and voltage traces are retained when validation fails. Firmware
scenarios and coupled timestep convergence remain separate qualification work.

Next qualify device models and voltage-domain interfaces, and couple the
electrical oscillator/reset into the feedback loop with TV80, ROM,
matrix contacts and cable load. Keep the original Icarus reference comparison as
an independent regression. CPU internals remain an HDL model unless a separately
qualified transistor-level CPU model is explicitly introduced.

For the oscillator, use the manufacturer's [DL000D data sheet](https://datenblatt.weithclan.de/Daten/DL000-030D-ME_ocr.pdf)
(printed pages 198–202): DL000D is LS-TTL, with SN74LS00 listed as the comparison
type. A standard 7400 analog gate model must not be silently substituted. The
published logic symbols and limits alone do not specify a transistor-level model.

For a completed older boot run rejected only by its incorrect idle-transmit
assertion, `recheck_boot.py /path/to/run` applies the corrected validator without
rerunning the electrical simulation. It checks the original deck/ROM provenance
and writes a separate `revalidation.json`, preserving the execution report and
source hashes. It refuses prepared-only, interrupted and unrelated failed runs.
