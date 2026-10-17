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

The matrix tools, `firmware_io_cosim.py` and `boot_cosim.py` accept
`--latch-load source-limit` and `--latch-load sink-limit`
(default: `ideal`, 1 GΩ and 10 pF). These stress fixtures add 12 pF and either
inject 200 µA into each sense input or sink 50 µA from it. Values come from the
[Intel 8282 DC characteristics](https://tvsat.com.pl/PDF/8/8282_intel.pdf),
pinned with their test conditions in `latch_limits.json`. The constant currents
are applied across the whole voltage swing as sensitivity stimuli; the sheet
specifies them only at particular input voltages. They are not calibrated input
I/V curves, guaranteed operating corners, or an IC supply-current model.
Passing DC/HDL and transient feedback reports are retained in
`reports/latch-loading/`. The full-board harness requires
`--electrical-matrix` when selecting a stress load. Firmware and full-board
qualification must be run separately; the retained fixture reports do not
qualify those broader scopes.

```sh
python3 verification/robotron-keyboard/analog/matrix_probe.py --latch-load source-limit --out /tmp/matrix-source-limit
python3 verification/robotron-keyboard/analog/matrix_cosim.py --latch-load sink-limit --out /tmp/matrix-feedback-sink-limit
```

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

Select `--npn-profile sc236-dc` in `device_probe.py`, `reset_probe.py` or
`boot_cosim.py` to use the exploratory current-dependent NPN candidate in
`sc236_dc.cir`. It meets the selected DC gain ranges; the device report also
shows deviations from typical base-emitter voltages without inventing acceptance
bands for typical values. The parameters describe a candidate, not a unique fit
or a manufacturer model. PNP and diode models remain generic. The original
profile remains the default for comparisons; CI checks the candidate's DC limits
and reset integration separately. Reports retain the selected profile and source
hashes. Full-board transient qualification is still required for this profile.

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
firmware scenarios with coupled clock/reset remain required.

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

`make qualify-keyboard-firmware-io S600_ROM=/path/to/s600.bin` exercises the
electrical matrix and cable receiver with TV80/S600 and the resolved CPU/ROM/latch
bus. Its service fixture opens BR1/BR2 and supplies clock/reset at the CPU sides;
it excludes the oscillator and board reset generator. A fixture contact closes
after reset. This isolates firmware-driven I/O from the longer power-on run.
`--scenario` selects a JSON recipe from `scenarios/`: contact transitions,
service reset pulses and observable acceptance windows share one cycle timeline.
The generator emits both SPICE sources and the C reference header. Modifier
windows must differ from ordinary-key windows; repeat needs repeated traffic
and silence after release. These checks run against the C reference before
starting SPICE, then against the cable receiver. They prevent an ineffective
stimulus from qualifying a named case. C reset reinitializes its keyboard model
and restores held contacts; this is a reference stimulus, not peripheral-pin
reset equivalence.

Use `--prepare-only` to compile and inspect a recipe without running SPICE; its
report remains unpassed. For the Make target, set `KEYBOARD_IO_SCENARIO` and
`KEYBOARD_IO_OUT` to keep each scenario's results separate. Long repeat runs can
set `KEYBOARD_IO_TIMEOUT_SECONDS=14400`. Each scenario still needs completed
electrical runs, timestep comparison and receiver-margin checks; a prepared
recipe or a passing C precheck is not electrical qualification.
`scenario_coverage.py /path/to/run --scenario /path/to/recipe.json --out /path/to/coverage.json`
can apply observation windows to a completed run without overwriting its report.
It verifies the retained stimulus/header and refuses contact, reset or duration
changes. Timestep comparison likewise requires matching executed decks; observation
requirements are evaluated separately from the physical stimulus.
The clock/reset stimuli originate in SPICE so the HDL does not advance time past
an analog solver retry. Initial reset observation likewise samples an external
clock edge rather than scheduling an HDL startup timer.
The service harness exposes `--bridge-delay-ns` and defaults to 10 ns. The 1 ns
setting produces expired-output scheduling warnings during startup in the longer
service transient; warnings fail qualification even when received bits match.
This is a numerical interface allowance, not a historical gate delay. Check its
sensitivity separately from analog timestep refinement.

`serial_observation.py` compares transmitted intent with independently thresholded
cable-receiver events. It rejects unknown bits, missing/extra edges, changed bits
and invalid temporal ordering. The service test requires activity; an idle boot
does not. It also compares the received bit sequence with the production C
emulator under the same contact fixture, allowing CPU cycle offsets. Matching
intent alone establishes bit transport, not S600 frame semantics,
key identity, receiver setup/hold margins or full-board qualification. Refine the
service timestep with `firmware_io_cosim.py --rom /path/to/s600.bin --step-ns 25 --out /tmp/firmware-io-fine`.
The run retains source/library hashes, logs and receiver waveforms, including on
failure. It requires the bridge below and remains outside fast CI.
Failure reports identify the differing serial signal, bit ordinal and available
timestamps. C cycles and receiver picoseconds remain separate clock domains.
For unequal edge counts, the first unpaired ordinal is reported without claiming
it identifies where an edge was lost; complete logs and waveforms remain available.

Check refinement with
`compare_firmware_io.py /path/to/coarse /path/to/fine --out /path/to/comparison.json`.
It verifies retained artifact hashes, matching electrical/HDL inputs and a halved
timestep before comparing bit sequences, transmit/receive edge times and cable
transport delays. Its declared numerical tolerance is not a historical timing
specification. A run that receives the right bits can still fail convergence;
keep that distinction when reporting qualification.
The Make qualification target runs the 50 ns / 25 ns pair and this comparison.
Archived `reports/firmware-io-*.json` retain the qualified service fixture's input,
observation and comparison provenance; this does not qualify full-board startup
or other contact/reset scenarios.

`qualify_io_pair.py /path/to/coarse /path/to/fine --scenario /path/to/recipe.json --out /path/to/qualification`
applies convergence, scenario coverage and receiver margins to an existing pair.
It marks the combined result passed only after every check passes, pins the input/check
reports and preserves failure logs. The Make target uses this same final gate.
Service coverage also checks CPU RESET_N transitions and a restart at ROM address
0000 after every reset release. Matching later serial traffic alone cannot satisfy
the reset check.

`reports/release-repress/`, `reports/modifier/`, `reports/control/` and
`reports/service-reset/`
retain qualified scenario pairs;
`coarse-run.json` and `fine-run.json` are the input reports referenced by each
qualification's hashes.
This extends the BR service evidence, not full-board startup or calibration.

`receiver_margins.py /path/to/run --out /path/to/margins.json` separately checks
data stability around the receiver edges using the retained voltage trace. It
rejects missing samples, wrong/indeterminate levels and insufficient sampled
setup/hold. The default 100 ns budget is an explicit fixture assumption, not a
historical receiver specification. Reports retain conservative sample-bounded
intervals and identify intervals cut off by the trace boundaries. The Make target
requires this margin check at both timesteps. Passing it does not establish a
physical receiver's voltage thresholds or timing limits.

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

## Firmware-driven indicators

`firmware_io_cosim.py --led-trace` retains `led-trace.txt` with SI/SO and Caps
intent voltages and diode currents. It checks nominal on/off current after a
100 ns settling allowance, starting at service-reset release so the supply ramp
is not treated as a failed firmware response. Unknown intent levels fail once
settled. `--require-led-activity` additionally requires both indicators to show
on and off samples; matching serial traffic cannot satisfy that requirement.

```sh
make qualify-keyboard-firmware-io S600_ROM=/path/to/s600.bin KEYBOARD_IO_SCENARIO=verification/robotron-keyboard/analog/scenarios/indicators.json KEYBOARD_IO_LEDS=1 KEYBOARD_IO_TIMEOUT_SECONDS=7200
```

The paired qualifier verifies the LED trace hash and recomputes these checks.
It also replays the retained scenario/ROM through a C driver with LED observation
and compares ordinal LED intent states. Emulation source hashes and the original
serial transcript must match; failures identify the first differing LED state
with C-cycle and electrical-time coordinates kept separate.

```sh
python3 verification/robotron-keyboard/analog/compare_led_reference.py /path/to/run --out /tmp/led-comparison.json
```

This covers nominal load response and ordinal C LED-state agreement, not exact
CPU-cycle timing, LED waveform convergence or calibrated brightness.
`reports/indicators/` retains the qualified pair, including both C LED comparisons
and their replay logs.

## NAND static characterization

```sh
python3 verification/robotron-keyboard/analog/gate_probe.py
python3 verification/robotron-keyboard/analog/gate_probe.py --model verification/robotron-keyboard/analog/ls_nand_dc.cir --require-qualified
```

`gate_limits.json` pins the manufacturer source and selected DL000 static limits.
The original nominal model exceeds the short-circuit output-current maximum.
The separate `ls_nand_dc.cir` candidate uses different high/low output impedances
and meets the selected loaded-output, input-current and short-current constraints.
Reports are retained in `reports/gate-dc-*.json`. These are static checks at 25 °C;
they do not qualify temperature, switching, supply current or oscillator timing.
The running board simulations retain the original nominal model. The candidate
passes the standalone oscillator transport, BR1 isolation, capacitor sensitivity
and timestep checks (`oscillator_probe.py --gate-profile dl000-dc`), retained in
`reports/oscillator-dl000-dc.json`. Coupled firmware qualification remains required
before it becomes a board default. Select it in `boot_cosim.py` with
`--gate-profile dl000-dc`, or use `KEYBOARD_BOARD_GATE_PROFILE=dl000-dc` with the
paired board target. Reports pin the selected model, and the qualifier verifies
the actual include and retained file. Its frequency is not fitted to the emulator.

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
instead of ideal serial intents and compares any transmitted bits with the cable
receiver. Each mode includes a component model/boundary
inventory; an unknown schematic reference fails generation. This inventory is
coverage evidence, not a claim of device accuracy. CPU/peripheral buses, control
pullup loading, IC supply currents and brownout behavior remain unqualified.
The CPU receives clock/reset through an explicit nominal 1.4 V threshold, without
an X band that could create multiple Verilog clock edges during one voltage rise.

Timed contact recipes can also run with BR1/BR2 closed:

```sh
python3 verification/robotron-keyboard/analog/boot_cosim.py --rom /path/to/s600.bin --electrical-matrix --electrical-outputs --scenario verification/robotron-keyboard/analog/scenarios/single-press.json --step-ns 10 --out /tmp/board-single
```

Here recipe indices represent 1 us wall-time ticks starting at 125 ms, independent
of the electrical oscillator. The trace extends to the recipe end; receiver
traffic must satisfy its observation windows. This does not establish ordinal C
agreement or timestep convergence. Service reset recipes are rejected because they
would bypass the connected reset generator. Full-board scenario qualification is
still pending.

Run the paired full-board target with:

```sh
make qualify-keyboard-board-scenario S600_ROM=/path/to/s600.bin
```

It runs 10 ns and 5 ns timesteps, then checks electrical clock edge order and
absolute phase, reset/restart and serial edge agreement, and sampled cable-data
margins. Clock crossings retain their sample brackets; the first differing edge
is reported without phase realignment. Sampled clock extrema must agree within
0.05 V. Period statistics remain separate from accumulated phase drift. `KEYBOARD_BOARD_SCENARIO`,
`KEYBOARD_BOARD_OUT` and `KEYBOARD_BOARD_TIMEOUT_SECONDS` select the recipe,
output directory and per-run timeout. Existing runs can be checked without
repeating simulation:

```sh
python3 verification/robotron-keyboard/analog/qualify_board_pair.py /path/to/coarse /path/to/fine --out /tmp/board-qualification.json
```

The qualifier verifies retained input/trace hashes and reruns observation checks;
prepared-only or failed executions cannot qualify. Its default 15 ns edge and
100 ns margin budgets are explicit numerical/fixture limits, not historical
hardware specifications. It does not qualify the complete oscillator waveform shape, brownout
or semiconductor calibration.

`--bridge-delay-ns` controls numerical synchronization (default 10 ns). The retained
`reports/electrical-matrix-boot-1ns-failure.json` records solver/bridge diagnostics
with the old 1 ns setting. A larger delay passed service fixtures but remains to
be qualified with the electrical oscillator; warnings and time reversals still
fail the run. The setting is not calibrated device propagation.

The supply rises over 1 microsecond by default. The nominal reset model fails to
produce a useful pulse with a 10 ns supply ramp; this is reproducible with
`reset_probe.py --rise-us .01 --out /tmp/reset-fast-ramp`. Treat that as an open
model-qualification issue, not evidence about the specimen. Adding
`--source-ohms .1` to the reset probe restores the pulse with the `sc236-dc`
profile, showing sensitivity to the ideal zero-impedance source. This is an
exploratory external source resistance, not a board component or measured supply.
The reset trace includes source current; finite impedance alone does not establish
a realistic current limit or complete power-supply model. `boot_cosim.py` also
accepts `--rise-us` and `--step-ns` for investigation.

The full power-on delay is simulated, although only a tail window is saved to
limit waveform storage. The run is kept outside fast CI and can take much longer than the standalone
probes. Set its wall-clock limit with `--timeout-seconds`. Reports pin ROM, TV80, generated wiring, bridge libraries and analog sources;
solver logs and voltage traces are retained when validation fails. Firmware
scenarios and coupled timestep convergence remain separate qualification work.

The archived `reports/clock-reset-baseline.json` demonstrates S600 boot and idle
scanning from electrical clock/reset. It preserves the original failed report
alongside revalidation after correcting the idle-transmit assertion. This baseline
uses digital sensing, direct ROM input and WR-only CPU data drive; it does not
qualify the later resolved-bus, electrical-matrix or output-load integration.
Waveforms remain in the local build directory with hashes recorded in the report.

Next qualify device models, voltage-domain interfaces and firmware scenarios in
the assembled full-board feedback loop. Keep the original Icarus reference comparison as
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

## Retained waveform storage

Completed successful runs can be compacted without losing their original trace
hashes or requiring a simulation rerun:

```sh
python3 verification/robotron-keyboard/analog/compress_trace.py /path/to/completed-run
```

The tool verifies the report hash before compression and verifies decompressed
bytes before removing the raw copy. It preserves failed/unfinished runs and
refuses changed input. Qualification readers accept `trace.txt.gz` and
`led-trace.txt.gz` transparently; report hashes continue to identify the original
uncompressed content. Do not compact files belonging to an active simulation.
