# Reference analog simulation

Use the standard S600 ROM and published reference circuit independently of specimen
photographs, replacement firmware and measured timing. Those observations can
calibrate the model later; they are not prerequisites for circuit-model development.

Automated ngspice probes use `--no-spiceinit` (`-n`) to ignore local and user
startup configuration. Solver options belong in the generated deck; system
installation and code-model versions still need to match the recorded tools.

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
qualify those broader scopes. `reports/latch-loading/firmware-source/` and
`firmware-sink/` retain the qualified S600 single-press service scenario under
each load stress,
including C serial agreement, refinement and sampled receiver margins. This
does not qualify electrical oscillator/reset or the internal latch I/V curve.

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

Use `--steps-ns COARSE FINE` to change the probe's timestep pair. Both the probe
and `boot_cosim.py` accept `--reltol`, `--vntol` and `--abstol`, emit them in the
SPICE deck and retain them in the report. The defaults are explicitly 0.001,
1e-6 V and 1e-12 A. Full-board pair qualification rejects differing solver settings.

```sh
python3 verification/robotron-keyboard/analog/oscillator_probe.py --steps-ns 1 .5 --reltol 1e-9 --vntol 1e-11 --abstol 1e-17 --out /tmp/oscillator-tolerance-check
```

`reports/oscillator-solver/` retains the default-tolerance coarse-step failure
and tighter-tolerance investigations. The probe's existing 1% frequency criterion
is a topology smoke check, not long-duration phase qualification. Agreement at one
step pair can hide changes exposed by smaller steps or tighter tolerances; compare
both. Short standalone agreement does not qualify accumulated full-board clock
phase, coupling to the HDL scheduler, or historical frequency.

The probe also records absolute edge order/phase and sampling-bracket uncertainty
from startup, using a 1.4 V threshold and 15 ns budget. `phaseQualified` reports
this separately from the topology smoke result; add `--require-phase` to make it
a required gate. This uses the same phase checker as full-board qualification,
without aligning edges or discarding startup. `reports/oscillator-phase/` retains
a default-tolerance rejection and a tighter-tolerance pass over the probe window.
The default frequency test alone can pass while this phase gate fails.

`coupled_clock_probe.py` prepares the full electrical matrix/output board with
TV80 and the same HDL bridge, then changes the transient/save window and adds non-loading node observations
to inspect early startup. It compares matched inputs and absolute clock phase;
it cannot qualify boot, key handling or phase accumulated through power-on reset.
Prepared full-board reports remain explicitly unqualified. Duration, timesteps
and the simulation timeout are configurable.
Its `cpuClockVoltage` diagnostic checks clock excursions only while the captured
supply is within the U880 reference range. Samples outside that range cannot
establish CPU clock compliance. Observing both voltage levels is not pulse-width,
slew-rate or device qualification.
Full-boot runs retain a separate `supply-trace.txt` stream and the same diagnostic;
both waveform streams are hashed and optionally compressed. Legacy boot traces
without supply samples remain readable but provide no supply-aware clock evidence.
The board-pair qualifier requires a valid supply throughout its saved observation
window and both U880 clock-level excursions on each complete sampled cycle.
It also rejects clock samples outside the documented input-voltage range.
Leading and trailing partial cycles are excluded. These are necessary checks;
they do not establish valid pulse widths or levels between samples.
`cpuClockTiming` separately brackets high/low valid-level durations, rise/fall
transitions and periods against the published U880D reference limits. Printed
timestamp precision and sample gaps contribute to the bounds; ambiguous results
remain indeterminate. This diagnostic does not identify the specimen's CPU speed
grade or prove tester-threshold equivalence or behavior between samples.

`--electrical-cpu-pullups` enables schematic R6.4/R6.5 in boot, coupled-clock
and S600 service runs. Each attached U880 control input receives the published maximum input
capacitance; voltage receivers feed INT/NMI/WAIT and BUSRQ into TV80 instead of
constant highs. X1:A9 remains externally open. `CPU_CONTROL` records the received
logic levels, including unknowns. Leakage, clamps and CPU brownout behavior remain
unmodeled; this option is an exploratory circuit boundary, not device calibration.
`--electrical-logic-pullups` couples R6.3/R6.6/R9.9 and nominal open-collector
sinks to the generated latch/flip-flop pins in boot, coupled-clock and S600
service (`firmware_io_cosim.py`) runs.
`--logic-load-pf` adds explicit per-net fixture capacitance; it is not a measured
device load. I/O-active uses a nominal 1.4 V clock crossing; the other control
receivers retain their 0.8/2 V unknown band. `logic_control_probe.py` checks the
passive fixture; `logic_cosim.py` exercises live driver/voltage/receiver feedback,
latch hold/transparency, output release and LED state at paired timesteps.
That bus fixture does not qualify firmware or device propagation.
The S600 service harness also accepts `--minimum-breakpoint-fs`; an explicit
value uses deck `.tran`/`run` so ngspice retains the breakpoint setting. Paired
qualification checks the setting against each executed deck.

```sh
python3 verification/robotron-keyboard/analog/coupled_clock_probe.py --rom /path/to/s600.bin --steps-ns 1 .5 --duration-us 1000 --out /tmp/coupled-clock
```

The separate `diagnostic-trace.txt` records board supply, oscillator internal
nodes, cable return and host-source current. `--rise-us` varies the host ramp
without bypassing cable/filter charging. Inspect the rail trajectory before
interpreting a short startup window: threshold crossings can occur before valid
logic-high levels are reached.

Coupled clock convergence remains unqualified. Retained traces show both startup
offset and accumulated phase drift; finer steps can also abort around the first
HDL clock and column-output transition. `reports/coupled-clock-startup/` pins the
execution evidence, event captures and rejected model/initialization experiments.
The phase checker retains signed offsets separately for rising and falling edges
without realignment. Solver diagnostics reject a run even if ngspice exits zero;
a named failing node alone does not establish the root cause.

Full-precision captured-output replay reproduces the abort without the HDL bridge;
rounding stimulus timestamps can hide it. This does not isolate a bridge defect
or justify rounding as a fix. Retain events from time zero with `set numdgt=17`
and `eprint`: a late transient save window discards initialization events.

`--column-load-pf` adds assumed column-to-ground capacitance in the boot,
coupled-clock and firmware-I/O harnesses; zero retains the unloaded baseline.
The load is an explicit fixture assumption, and differing loads cannot be paired
for timestep refinement. Loading, integration-method and unknown-output power-up
fixtures have not resolved live startup. Their scope, decks and failure evidence
remain in `reports/coupled-clock-startup/`; none establishes specimen parasitics
or historical power-up states. Fixed-control analog isolation completes the early
window with ADC observers and constant-input DACs as well as without bridges.
Captured digital-event replay through the zero-unknown DACs still aborts without
CPU execution. The no-bridge clock has not reached the checked high level
(`reports/coupled-clock-startup/analog-isolation/`). This narrows the reproducer
without qualifying startup or establishing a simulator defect.

`dac_event_probe.py` reproduces this CPU-free failure with retained inputs. Its
`--case replay` run aborts while all observed DAC controls remain at zero volts;
`omit-release` and `isolated-breakpoint` complete the same early window. The latter
adds an electrically isolated PWL breakpoint, so a generic analog breakpoint
alone does not reproduce the failure. `isolated-dac-event` moves the release to
an electrically isolated DAC and still fails; `isolated-dac-quiet` holds that
DAC state unchanged and completes. This isolates the reproducer from column-drive
loading. Results and provenance are retained in
`reports/coupled-clock-startup/analog-isolation/observed-events/`. Reproduce with
`python3 verification/robotron-keyboard/analog/dac_event_probe.py --case replay
--ngspice /path/to/ngspice --out /fresh/output/directory`; use the recorded runtime
for comparison. These experiments do not qualify the oscillator or firmware.

`engine-patches/ngspice-47-equivalent-dac-diagnostic.patch` suppresses breakpoints
for equivalent unknown/rail DAC targets. It completes the captured zero-unknown
replay, but live TV80/S600 startup still aborts. It is not adopted; retained runtime
and results are in `reports/coupled-clock-startup/equivalent-dac-diagnostic/`.

The logging-only breakpoint audit records attosecond event cuts followed by steps
too small to advance the stored time. Do not infer that deck `minbreak` options
were applied by control-command `tran`: ngspice 47 omits that option when copying
the analysis task. The snapshot probe in `reports/coupled-clock-startup/minbreak/`
verifies that deck `.tran` followed by `run` retains it. Earlier control-`tran`
spacing runs are invalid as sensitivity evidence; their original failures remain
retained. See `reports/coupled-clock-startup/breakpoint-audit/` for exact times.
With deck `.tran`/`run`, both 1 fs and 0.1 fs settings complete the 150 us live
S600 window using the installed engine and baseline DAC mapping
(`reports/coupled-clock-startup/minbreak/effective/`). Longer execution and paired
phase refinement remain required; these runs do not qualify full-board timing.
`coupled_clock_probe.py --minimum-breakpoint-fs 1 --compress-traces` exposes this
numerical setting through deck `.tran`/`run`, retains it in each run report and
rejects pairs with different settings. Compression preserves waveform bytes and
requires fresh run directories. The default invocation and phase budget remain
unchanged.

`engine-patches/ngspice-47-zero-hysteresis.patch` is an experimental switch-state
boundary correction, not the default engine. It passes the isolated plateau and
captured-output replay checks but does not resolve live startup. Use
`switch_boundary_probe.py` for its independent regression; engine provenance and
results live in `reports/switch-boundary/` and `reports/coupled-clock-startup/`.

```sh
python3 verification/robotron-keyboard/analog/switch_boundary_probe.py --ngspice /path/to/candidate/ngspice --out /tmp/switch-boundary
```

`reports/supply-startup-isolation/` contains a reduced linear supply/cable
reproducer for the tight-tolerance startup failure. Copy it to a scratch location
and run `ngspice -n -b linear.cir`. These deliberately reduced circuits are
numerical diagnostics, not alternative board models.

`linear_startup_reference.py` independently evaluates that frozen symmetric
fixture with a Decimal matrix exponential. It rejects changed inputs and checks
precision refinement. `reports/linear-startup-reference/` retains the comparison
with SPICE using a known source delay; this does not authorize shifting measured
clock phase or adopting that initialization on the complete board.

```sh
python3 verification/robotron-keyboard/analog/linear_startup_reference.py
python3 verification/robotron-keyboard/analog/linear_startup_reference.py --trace /path/to/delayed-ramp-trace.txt --source-start-ns 1
```

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
Serial comparisons identify the first sequence or out-of-budget timing event
with both timestamps; the detailed repeat diagnostic is retained with its reports.

`reports/repeat/` retains successful individual repeat-scenario executions with
C serial-bit agreement, but their paired receiver timing exceeds the refinement
budget. Independent coverage reports verify the press, repeat and release
observations and reset/ROM restart. These checks do not override the failed
refinement gate: repeat remains unqualified. Independent receiver-margin reports
also pass, accounting conservatively for printed timestamp uncertainty; the
paired timing refinement and unresolved solver time-order messages remain rejections.
Service coverage also checks CPU RESET_N transitions and a restart at ROM address
0000 after every reset release. Matching later serial traffic alone cannot satisfy
the reset check.

The qualification reports in `reports/release-repress/`, `reports/modifier/`,
`reports/control/`, `reports/service-reset/` and `reports/indicators/` point to
complete qualified rechecks under the diagnostic-only strict-time correction.
Their original functional event sequences and timestamps are preserved; this does
not qualify full-board startup.

`reports/solver-diagnostic-audit.json` preserves the earlier reassessment of
previously ignored time-order messages and pins the affected logs; equal printed timestamps do not establish backward
execution. The harnesses and retained-run loader now reject unresolved messages,
including when ngspice exits zero. Original reports remain available alongside
reassessed qualification results.
`reports/service-time-audit/` records exact binary-time equality at the first
release event. The experimental `ngspice-47-strict-time-diagnostic.patch` changes
only the diagnostic comparison, retaining warnings for actual backward time.
It does not restore qualification without a complete scenario recheck.

The firmware-I/O, boot and coupled-clock harnesses accept `--ngspice /path/to/engine` and an optional
`--ngspice-spinit /path/to/spinit`. It fingerprints the executable, selected
initialization and literal XSPICE code-model paths, forces that initialization
for the child process and re-resolves code-model load paths after execution to
reject redirected symlinks as well as changed files. Paired runs
must retain identical backend identities; a matching version string is insufficient.

`firmware_io_cosim.py --compress-traces` streams waveform output through POSIX
FIFOs directly to lossless XZ in a fresh output directory. Producer-byte hashes
are checked against decompressed data before the run passes. Failed captures
retain partial streams as failure evidence; they cannot qualify. This avoids
allocating the raw waveform for long scenarios. `reports/compressed-output/`
retains a byte-for-byte ngspice storage comparison.

`receiver_margins.py /path/to/run --out /path/to/margins.json` separately checks
data stability around the receiver edges using the retained voltage trace. It
rejects missing samples, wrong/indeterminate levels and insufficient sampled
setup/hold. The default 100 ns budget is an explicit fixture assumption, not a
historical receiver specification. Reports retain conservative sample-bounded
intervals and identify intervals cut off by the trace boundaries. Gap checks use
the precision of each printed timestamp; the same uncertainty contracts measured
setup/hold intervals, so formatting cannot create an artificial margin pass. The Make target
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
with C-cycle and electrical-time coordinates kept separate. `compare_led_pair.py`
also requires LED intent midpoint transitions to converge within the paired 15 ns
budget, using sampling brackets and printed timestamp uncertainty without phase
realignment. Matching ordinal states alone cannot satisfy this check.

```sh
python3 verification/robotron-keyboard/analog/compare_led_reference.py /path/to/run --out /tmp/led-comparison.json
```

The checks cover nominal load response, ordinal C LED-state agreement and paired
intent-edge timing. Exact CPU-cycle timing, full LED-current waveform convergence
and calibrated brightness remain unqualified.
`reports/indicators/qualification.json` points to the qualified service recheck,
including C LED-state agreement, paired intent-edge timing and retained replay logs.

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
`electrical_bus_interface.generate()` exposes independent CPU, ROM and latch
low/high drive enables, packed into bits 7:0, 15:8 and 23:16 respectively. Both
enables low means release; unknown drive remains unknown. `bus_sense` supplies
receiver logic to the CPU read path and serial-data gate, without digital pullups
or driver resolution. The HDL regression exercises release, opposing drivers,
latch pin order and unknown feedback. `bus_cosim.py` closes the interface through
SPICE pin loads, linear driver impedances and TTL receivers. It checks CPU/ROM/latch
reads, release, opposing drivers and supply current at paired timesteps. Driver
resistances come from published DC load-test endpoints, not extracted I/V curves;
the fixture omits input bias, leakage, clamps and IC power behavior. It is not yet
calibrated. Run with `--bridge` and `--ngspice` as for the other live fixtures;
results are retained in `reports/bus-feedback`.

Both electrical-bus harnesses also accept `--latch-timing-envelope`. The optional
`i8282_timing.v` model uses the [Intel I8282 timing table](https://tvsat.com.pl/PDF/8/8282_intel.pdf)
(printed pages 9-92/93): a short strobe invalidates storage, and data changes inside
the hold interval invalidate the affected bits until a valid capture. Output
access/release windows propagate X. The model conservatively waits the strobe
propagation maximum after either edge, rather than predicting an actual waveform.
It assumes the published supply, temperature and test load; it does not model
power-up, slew or physical metastability. Reports pin the model and option.
Executed CPU tests cover ROM instruction fetch, latch input and output with both
timing models enabled. The [live startup check](reports/latch-timing-envelope/startup/assessment.json)
retains early I/O reads and bus voltages with both envelopes enabled. Full
mixed-signal latch timing remains unqualified.

Both electrical-bus firmware harnesses accept `--rom-read-envelope` to replace
instantaneous ROM output with the conservative read envelope in `eprom2716.v`.
The [Intel 2716 table](https://www.theoddys.com/acorn/semiconductor_datasheets/2716%20Intel.pdf)
(printed page 2-5, standard 450 ns grade) supplies address/CE access, OE access and
output-float deadlines. Unspecified intervals propagate X; a later address glitch
restarts access even when it returns to the same address. CE/OE and address pins
come from the schematic. This is an optional reference timing model, not U556
calibration: it assumes the published supply, temperature and test load, and does
not predict an analog transition or programming behavior. The bridge's numerical
voltage for X is not a qualified pin voltage. Reports retain the option and model
hash. Executed HDL tests cover timing windows and CPU instruction execution;
live mixed-signal timing remains unqualified. The retained
[startup experiment](reports/rom-read-envelope/startup/assessment.json) exercises
the timers through ngspice and preserves its voltage trace. Its sampled-read pass
is specific to this envelope and unknown-drive surrogate; it does not resolve
the baseline driver-model failures or qualify a complete firmware scenario.
The manual `keyboard-bus-diagnostic.yml` workflow accepts `rom_read_envelope`,
`latch_timing_envelope`, `cpu_profile` and `electrical_wr` independently and retains paired traces.
For the full digital C/HDL workload, use `../run.py --rom PATH --rom-read-envelope`
with the selected `--cpu-profile`, or the manual `keyboard-cpu-phase.yml` workflow.
Add `--latch-timing-envelope` (workflow input `latch_timing_envelope`) to replace
the generated board's A4 model while preserving its numbered pin connections.
The [combined firmware result](reports/latch-timing-envelope/firmware/assessment.json)
retains the full workload and comparison with the ROM-only baseline. The
[combined CPU-profile comparison](reports/latch-timing-envelope/cpu-profiles/assessment.json)
checks the same workload across all available CPU sampling profiles.
Either timing option sets a 1 MHz fixture clock so nanosecond ROM limits have physical units while
preserving the cycle-indexed contact recipe. The retained
[CPU-profile comparison](reports/rom-read-envelope/cpu-profiles/assessment.json)
checks the complete digital workload against C and the untimed HDL baseline.
That fixture retains direct memory
input and therefore does not test electrical bus contention or output release.

The service harness accepts `--electrical-bus --bus-latch-pf 12 --bus-7406-pf 3`
to route S600/TV80 bus reads through this experimental model. The capacitances in
this example are explicit fixture assumptions. This mode retains `bus-trace.txt`
and source provenance; it does not change the default bus path. `bus_observation.py`
checks sampled voltages, mapped ROM bytes and TV80 input-register confirmations.
The bus trace also retains the board supply; read windows must satisfy the U880
reference supply and input-voltage ranges. The checker rejects unknown data,
missing observations and waveform gaps. TV80's sampling
edge is not a substitute for the U880's distinct M1 and M2–M5 pin timing.
Electrical and data mismatches retain the first failing read's time, address,
signal and expected/observed values in `busFailure`, alongside the failure traces.
Four-state data is rejected in read order and retains its raw hexadecimal text;
an uncertain later read cannot hide an earlier voltage failure.
[Retained-trace revalidation](reports/electrical-bus-failure-review/read-ordered-revalidation.json)
distinguishes full-log rejection from the paired-prefix diagnosis of the older
transistor run, whose final latch confirmation is missing.
Firmware runs require the complete bus capture interval, including its beginning
and end, and retain high-precision waveform timestamps.
Physical bus timing checks remain unfinished, so the paired firmware qualifier
rejects this mode rather than treating serial agreement as bus qualification.

Adding `--serial-driver 7406-dc` connects the data gate's published transistor
topology directly to the electrical bus, so its input current and serial output
share one circuit. The clock gate still uses ideal HDL input intent. This option
retains `driver-trace.txt` for the modeled gates' supply current. Semiconductor
parameters and switching behavior remain uncalibrated; the short startup evidence
in `reports/bus-feedback/transistor-data-startup` is not a complete keyboard test.

The manually triggered `keyboard-bus-diagnostic.yml` workflow runs a complete
`single-press` or `reset` scenario at both timesteps on one CI runner. It builds
the pinned ngspice/Icarus runtime, checks the bridge first, and retains reports
and compressed traces even when a run fails. Artifacts expire after 90 days;
archive reviewed results before expiry. It is separate from the fast push checks,
and a green diagnostic run does not establish physical board qualification.

`bus_load.wiring()` generates pin capacitances from the inventory, using published
reference maxima and requiring explicit per-pin fixture values for undocumented
8282-output and 7406-input capacitances. The U880 bus limits use the manufacturer's
U880D table. The retained `reports/bus-capacitance` charge fixture checks generated
loads with timestep refinement; it does not qualify analog bus drivers or firmware
feedback. Zero fixture values are explicit omissions, not measured capacitances.

`bus_inventory.py` maps every physical data-bus attachment to source-pinned
electrical reference limits. It rejects unclassified attachments and keeps absent
output-capacitance data explicit. The schematic has no external data-bus pullups;
the digital released-bus value does not qualify electrical voltage or retention.
See `bus_limits.json` for test conditions and clone-applicability limits.

`ttl7406_probe.py` characterizes the nominal resistor/transistor topology published
in TI SDLS031A. Generic semiconductor parameters overstate high-input current;
`--input-reverse-beta .01 --require-dc-points` checks an explicit candidate against
selected DC limits at 25 C. Both remain unqualified for switching, temperature,
breakdown and specimen behavior, and neither is adopted in the board harness.
The model, source conditions and retained results are in `ttl7406_nominal.cir`,
`ttl7406_limits.json` and `reports/ttl7406/`.

`ttl7406_output_probe.py` compares the DC candidate with the ideal serial sinks
using the schematic-derived cable/filter network. It checks drive/release,
receiver rise convergence and cable-load sensitivity, and records driver supply
and input currents. Results live in `reports/ttl7406/outputs/`. These fixture
checks do not qualify transistor switching delays or firmware integration.

`write_control_probe.py --ngspice /path/to/ngspice --out /new/output/path`
checks CPU WR loading through the transistor clock gate and cable. The CPU
uses explicit low/high/release enables and published DC-endpoint impedances;
the gate contributes its modeled input bias. The input capacitance remains an
explicit fixture assumption. Retained waveforms are in `reports/write-control/`.
The service harness accepts `--electrical-wr` with `--electrical-bus` and
`--serial-driver 7406-dc` to connect that path to TV80 WR intent. RESET drives
WR inactive; BUSACK releases both driver branches, following U880D printed
pages 9–10. Unknown ownership remains unknown. `wr-trace.txt` retains pin
voltage, drive enables and branch currents. The retained service-startup capture
checks ROM reads and inactive WR; it does not demonstrate firmware WR pulses.
An extended capture failed storage and remains unqualified. Dispatch the
`keyboard-bus-diagnostic.yml` workflow with `electrical_wr=true` for remote
coarse/fine firmware runs. The WR observer requires both active and inactive
states, checks settled voltage and ownership, and rejects incomplete captures;
its settling window is a diagnostic allowance, not a propagation limit.
Unknown ownership intervals are rejected even between waveform samples.
Failures retain signal, time and expected/observed values in `wrFailure`.
These checks do not
qualify U880 control timing or transistor switching parameters.

The full-board `boot_cosim.py` also accepts `--electrical-bus`, `--bus-latch-pf 12`
and `--bus-7406-pf 3` with `--electrical-matrix`, resolved ROM and explicit CPU drive.
BR1/BR2 stay closed: the modeled oscillator and reset circuit drive the CPU.
With the transistor serial driver, D0 loads its physical input stage. Add
`--electrical-wr` to connect the finite CPU WR driver to the clock gate as well,
using the same RESET/BUSACK ownership rules as the service fixture. Idle boot
checks allow an inactive WR line; contact scenarios require firmware WR activity. Bus waveforms share the boot capture window.
Every logged read must have captured voltage, so reads before that window fail
validation rather than being omitted. A tail capture may begin at the first
accepted point within one maximum timestep after its requested start; read
windows still require bracketing samples and the end time stays strict.
The retained `reports/bus-feedback/closed-board-startup` checks live bridge
initialization while reset is asserted and supply is still rising;
`reports/write-control/closed-board-startup` retains the equivalent WR-enabled
check. Full-board firmware execution and paired electrical timing remain
unqualified.

The boot harness accepts `--electrical-outputs --serial-driver 7406-dc` to use
that candidate under live HDL control. Its inputs still come from ideal DAC
drivers; CPU output loading and the remaining package gates are not represented
electrically. The default serial model remains unchanged. The early coupled-clock
probe accepts the same driver selection and an explicit `--bridge` manifest.

`boot_cosim.py --minimum-breakpoint-fs 1` selects an explicit numerical breakpoint
spacing using deck `.tran` and control `run`. This invocation matters: ngspice 47
does not carry `minbreak` into the task created by a control `tran` command.
The option preserves the full boot interval and saved tail window; it is not a
device delay or a substitute for timestep refinement.

Use `boot_cosim.py --compress-traces` for long full-board runs. It streams the
saved boot/contact waveform to XZ, verifies its decompressed hash against the
producer bytes, and retains partial output on failure. It requires a fresh
waveform directory and does not change the simulation or validation window.

Boot and early-clock probes accept `--output-unknown-volts 0`, `2.5` (default), or
`5` to study the uniform DAC mapping of HDL unknown outputs. The setting is
recorded and must match within a refinement pair. These are startup sensitivity
fixtures, not measured power-on states or exhaustive coverage of mixed unknown
outputs. The default midpoint coincides with the ideal sinks' switching threshold;
changing it is a model assumption, not a timing correction.

The Make targets accept `KEYBOARD_BOARD_ARGS` (boot/full-board runs) and
`KEYBOARD_IO_ARGS` (BR service runs) for options such as the simulator path,
explicit bridge manifest and compressed capture. Each pair uses the same extra
arguments. Set `KEYBOARD_BOARD_COARSE_STEP_NS`/`KEYBOARD_BOARD_FINE_STEP_NS` or the
corresponding `KEYBOARD_IO_...` variables to choose the refinement steps. The
qualifiers still enforce matching inputs and their existing acceptance limits;
these controls do not select a qualified model or timestep automatically.

The CPU receives clock/reset through an explicit nominal 1.4 V threshold, without
an X band that could create multiple Verilog clock edges during one voltage rise.
That is a numerical crossing, not the U880's guaranteed clock-input level:
the manufacturer manual specifies clock high within 0.2 V of the supply and
clock low at or below 0.45 V. See `cpu_clock_limits.json` for the source and
conditions. The existing 10 pF boot clock load is nominal; the reference maximum
is 50 pF under the published capacitance test conditions.

`--gate-profile dl000-pullup` selects a candidate whose high-state driver sources
current without sinking current from an external pullup. This allows schematic
R10.3 to raise the CPU clock toward the supply. `clock_output_probe.py` checks
that path through BR1 with the reference maximum CPU capacitance; the older
resistive-output models fail its U880 high-level check. Selected DL000 DC checks
also pass, but neither test calibrates switching, package current or temperature
behavior. A [tight numerical refinement](reports/clock-output/tight-refinement/assessment.json)
passes the short isolated phase gate with unchanged device parameters, but its
clock period still violates the pinned U880 reference limit. This does not qualify
coupled startup or the full board. Applying those settings to
[coupled startup](reports/clock-output/coupled-tight-refinement/assessment.json)
still fails phase agreement during clock onset below the valid supply range;
the first-divergence waveform windows are retained. The 560-ohm pullup can demand more than the published 8 mA output test
current, so modeled clock levels do not establish guaranteed device corners.

Timed contact recipes can also run with BR1/BR2 closed:

```sh
python3 verification/robotron-keyboard/analog/boot_cosim.py --rom /path/to/s600.bin --electrical-matrix --electrical-outputs --scenario verification/robotron-keyboard/analog/scenarios/single-press.json --step-ns 10 --out /tmp/board-single
```

Here recipe indices represent 1 us wall-time ticks starting at 125 ms, independent
of the electrical oscillator. The trace extends to the recipe end; receiver
traffic must satisfy its observation windows. This does not establish ordinal C
agreement or timestep convergence. Service reset recipes are rejected because they
would bypass the connected reset generator. `reports/full-board-single-press/`
retains successful individual S600 executions with electrical clock/reset, matrix
and cable feedback. Their paired qualification rejects clock-phase convergence;
functional execution does not qualify timing or the remaining scenarios.

Run the paired full-board target with:

```sh
make qualify-keyboard-board-scenario S600_ROM=/path/to/s600.bin
```

It runs 10 ns and 5 ns timesteps, then checks electrical clock edge order and
absolute phase, reset/restart and serial edge agreement, and sampled cable-data
margins. Clock crossings retain sample brackets expanded by printed timestamp
uncertainty. Sample gaps and window alignment use that precision instead of a fixed
allowance; the first differing edge is reported without phase realignment.
Sampled clock extrema must agree within
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
solver logs and voltage traces are retained when validation fails. Failed runs
record available raw-output hashes and byte lengths in `failureArtifacts`, with
missing or unreadable outputs identified separately. This includes solver exits
and timeouts; fingerprints do not certify waveform validity. Older compressed
files are never substituted for missing outputs of a failed invocation. Firmware
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
hashes or requiring a simulation rerun. XZ is the default to reduce disk usage;
`--format gzip` selects faster compression. Existing gzip traces can be migrated
to XZ without materializing an uncompressed copy:

```sh
python3 verification/robotron-keyboard/analog/compress_trace.py /path/to/completed-run
```

For an individually completed early clock run, use `compress_trace.py --clock-probe /path/to/coarse-or-fine`. This verifies `clock-probe.json` and compacts both the
primary and diagnostic waveforms. A later paired phase rejection does not make
these completed traces invalid evidence; the separate phase result is preserved.

For large retained runs, `qualify_io_pair.py --timeout-seconds 1800` extends
the wall-clock limit of each validation phase, including decompression; it does
not change electrical acceptance budgets.

The tool verifies the report hash before compression and verifies decompressed
bytes before removing the raw copy. It preserves failed/unfinished runs and
refuses changed input. Qualification readers accept `.gz` and `.xz` waveforms transparently;
report hashes continue to identify the original
uncompressed content. Do not compact files belonging to an active simulation.

For long service or full-board captures, `--compress-traces --compression-preset 6`
selects stronger lossless XZ compression. The default remains preset 1. This changes
storage cost, CPU time and memory use; every producer byte and its hash are retained.

`cpu_read_phase_probe.py` demonstrates the remaining CPU sampling-phase gap:
TV80 executes `LD A,n; OUT (n),A` using the operand present at the rising edge,
even when a different value meets the U880D's documented non-M1 falling-edge
setup interval. The fixture preserves the vendor core unchanged. Its diagnostic
pass reproduces the discrepancy; it does not qualify U880 pin timing.

The probe's `--profile falling-candidate` generates an isolated input-latch
experiment; `--read-kind io` exercises input-port reads. `--wait` requires an
external WAIT interval that actually postpones the accepted read. The fixture
selects the final T3 iteration after TV80's automatic I/O waits. The
candidate consumes the later operand in these cases. It is not selected by the
board harness. The `indexed-opcode` fixture shows that the operand-only candidate
still takes the earlier DD-CB opcode through the core's direct instruction input.
`--profile falling-indexed-candidate` also moves that isolated path to the falling
edge; the fixture checks the resulting RAM write and output, including WAIT.
These behavioral dual-edge experiments do not establish synthesis suitability,
interrupt/reset/bus-grant correctness, full-firmware behavior or calibrated U880
timing. Vendored TV80 sources remain unchanged.

The read-phase probe's `--read-kind m1` changes the first opcode after the rising
edge and checks that all profiles retain the earlier instruction, including an
external WAIT. This checks edge selection, not a setup/hold-limit sweep.

Electrical-bus latch confirmations use Verilog's postponed observation region
at the sampling time, after the input register's nonblocking update. They do
not depend on a following falling edge beyond the capture stop. The validator
still requires a matching register confirmation for every read.

`reports/electrical-bus-failure-review/` retains the first failed voltage windows
from the paired S600 runs. With the transistor serial gate, D0 becomes uncertain
on A15-low I/O reads, where the schematic disables the latch outputs and releases
the bus. Serial values still match C; this does not establish valid CPU input
levels. The separate nominal-output run rejects a small D7 excursion above the
moving supply; reconstructed local charge balance is consistent with capacitor
lag in the linear driver fixture. Both electrical rejections remain open; neither is waived by the
digital floating-input sensitivity experiment.

Both `firmware_io_cosim.py` and `boot_cosim.py` accept
`--cpu-profile falling-indexed-candidate` with `--electrical-bus`. They generate
the reviewed CPU candidate separately from the vendor files, record its hashes,
and sample the electrical bus on the candidate's actual read edge. M1 stays on
the rising edge; ordinary reads use the following falling edge. The manual bus
workflow exposes the same selection. The default remains `tv80`.

`reports/cpu-read-phase/live-startup/` retains a short live-bridge check of that
selection and its latch observations. Its voltage checker still rejects a small
supply excursion. This proves neither full-scenario completion nor calibrated
U880 electrical timing; the existing paired electrical qualification gate remains
closed for both profiles.
