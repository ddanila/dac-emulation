# Reference analog simulation

This harness couples schematic-derived electrical circuits to the controller HDL.
It supports subcircuit probes, virtual BR service runs and closed-board firmware
execution. Models and qualification limits remain explicit assumptions; an
executable circuit is not a calibrated specimen. The [digital guide](../README.md)
covers connectivity synchronization and C/HDL comparisons. The museum's
[plan](https://github.com/ddanila/dac/blob/main/docs/robotron/keyboard-controller-plan.md)
owns reconstruction scope and remaining work.

Run commands below from the repository root. Use each entry point's `--help` and
[Makefile](../../../Makefile) for current options, defaults and qualification
budgets. Store experiments in separate output directories. Reports, source hashes
and traces are the result record; this guide is not an experiment log.

## Runtime setup

Use ngspice/XSPICE and Icarus built with `--enable-libvvp`; an ordinary `vvp`
executable alone is insufficient. The reproducible source pins, archive checksums,
engine patches and build commands live in the
[bus diagnostic workflow](../../../.github/workflows/keyboard-bus-diagnostic.yml).
Use that recipe when reproducing retained qualifications. For a local Icarus
source build, with autoconf, a C/C++ compiler, flex and Bison 3 available:

```sh
sh autoconf.sh
./configure --enable-libvvp
make -C vvp -j4 libvvp.so
```

On macOS put Homebrew Bison ahead of the system Bison. From this repository:

```sh
python3 verification/robotron-keyboard/analog/build_bridge.py \
  --ngspice-source /path/to/ngspice-47 \
  --icarus-source /path/to/iverilog \
  --libvvp /path/to/iverilog/vvp/libvvp.so
python3 verification/robotron-keyboard/analog/bridge_probe.py
```

The bridge builder applies [icarus-startup.patch](icarus-startup.patch) to its
build copy so constant-folded initial HDL outputs are sampled even without a
value-change callback. It preserves required VPI symbol visibility. Open-collector
transport uses sink-enable signals and analog conductance; direct Z transport is
an unresolved diagnostic path, not the board interface. X conductance and bridge
scheduling delays are numerical devices, not measured semiconductor behavior.

Use `--ngspice` and `--ngspice-spinit` to select a runtime where supported. Runtime
receipts fingerprint the executable, initialization and model libraries; a version
string alone is insufficient. Runs ignore user initialization. Experimental engine
patches require their own checks; the strict-time diagnostic correction does not
license ignoring actual backward-time warnings. Do not mix runtime provenance
between the two halves of a qualification. Removing XSPICE devices also changes
implicit truncation control; analog-only replays must preserve the effective
setting recorded by the source run.

## Firmware workflows

Virtual BR service runs supply CPU clock/reset externally and exercise the
selected electrical interfaces:

```sh
make qualify-keyboard-firmware-io S600_ROM=/path/to/s600.bin
```

Select a contact scenario with `KEYBOARD_IO_SCENARIO`; use the Makefile's arguments
for optional electrical loads and interfaces. A service pass does not qualify
the onboard oscillator or reset. Service scenarios use CPU-cycle scheduling;
closed-board scenarios map contacts to wall time through [board_scenario.py](board_scenario.py).
Service reset-injection recipes are rejected by the closed-board runner.

Inspect a closed-board deck before a potentially long simulation:

```sh
python3 verification/robotron-keyboard/analog/boot_cosim.py --rom /path/to/s600.bin --electrical-matrix --electrical-outputs --scenario verification/robotron-keyboard/analog/scenarios/single-press.json --prepare-only --out /tmp/board-prepared
make qualify-keyboard-board-scenario S600_ROM=/path/to/s600.bin
```

`boot_cosim.py` uses the onboard oscillator/reset with closed BRs. Matrix and
output electrical options are explicit; defaults do not imply every interface
is electrical. `--prepare-only` validates preparation, not simulation or behavior.
The paired target runs coarse/fine captures and applies qualification checks.
Retained pairs can be checked separately:

```sh
python3 verification/robotron-keyboard/analog/qualify_board_pair.py /path/to/coarse /path/to/fine --out /tmp/board-qualification.json
```

Use [qualify_io_pair.py](qualify_io_pair.py) for service pairs. Matching serial bits
is only one gate: phase, voltage, bus timing, coverage and solver diagnostics
remain independent. Missing events, unfinished runs and timeouts cannot pass.

## Isolating a failure

| Question | Entry points and evidence |
| --- | --- |
| Matrix sensing and loading | [sense_probe.py](sense_probe.py), [matrix_probe.py](matrix_probe.py), [matrix_cosim.py](matrix_cosim.py) |
| Reset and supply response | [reset_probe.py](reset_probe.py), [cpu_control.py](cpu_control.py), [cpu_clock_limits.json](cpu_clock_limits.json) |
| Gate DC and switching applicability | [gate_probe.py](gate_probe.py), [gate_switching_probe.py](gate_switching_probe.py) |
| Oscillator convergence and coupling | [oscillator_probe.py](oscillator_probe.py), [coupled_clock_probe.py](coupled_clock_probe.py) |
| Independent solver and supply replay | [xyce_oscillator_probe.py](xyce_oscillator_probe.py), [oscillator_supply_replay.py](oscillator_supply_replay.py) |
| Cable/output/indicator behavior | [output_probe.py](output_probe.py), [firmware_io_cosim.py](firmware_io_cosim.py) |
| Failed driver transition | [driver_boundary_replay.py](driver_boundary_replay.py), [analog_driver_replay.py](analog_driver_replay.py); the latter replaces HDL feedback with sampled PWL stimulus and an explicit diagnostic continuation |
| CPU read phase and firmware dependence | [cpu_read_phase_probe.py](cpu_read_phase_probe.py), [released_read_analysis.py](released_read_analysis.py) |

Use these probes to constrain a model before expensive coupled runs. DC and
switching limits must retain manufacturer test conditions, logic family and
selection group. DC gain is not AC gain. Model fitting against independently
published limits is valid desk work; tuning to the emulator's clock is not.
Validate against independent conditions where available and report sensitivity
across supported parameter ranges. Whole-package current consumption and device
behavior during undervoltage are not implied by nominal signal-level models.

`source-limit` and `sink-limit` loading profiles stress documented DC endpoints;
they are not complete input I/V curves. Gate profiles and transistor substitutions
remain exploratory unless their applicability is qualified. Vendor models require
pin-role and load-condition review; restricted model files stay local. A passing
switching fixture with generic diodes does not establish equivalence to the
manufacturer's fixture or historical DL000 behavior.

For candidate-model diagnosis, use fresh output directories. Entry points expose
arguments and defaults through `--help`; retained assessments identify the exact
fixtures and commands used.

| Question | Entry points |
| --- | --- |
| Does a candidate meet independent device conditions? | [ls00_validation_probe.py](ls00_validation_probe.py), [ls00_parameter_screen.py](ls00_parameter_screen.py), [ls00_rolloff_screen.py](ls00_rolloff_screen.py) |
| Do admitted models start and recover in the oscillator? | [oscillator_family_probe.py](oscillator_family_probe.py), [oscillator_disturbance.py](oscillator_disturbance.py) |
| Which transfer branches and output currents occur? | [oscillator_transfer_probe.py](oscillator_transfer_probe.py), [ls00_transfer_fixture.py](ls00_transfer_fixture.py), [ls00_iv_probe.py](ls00_iv_probe.py) |
| What explains a candidate's operating state? | [ls00_branch_probe.py](ls00_branch_probe.py), [ls00_branch_transient.py](ls00_branch_transient.py), [oscillator_ac_probe.py](oscillator_ac_probe.py), [oscillator_internal_probe.py](oscillator_internal_probe.py) |
| Does an independent solver reproduce a transfer capture? | [xyce_transfer_fixture.py](xyce_transfer_fixture.py) |

`oscillator_family_probe.py --validate-screen-only` checks candidate admission
without running oscillators. Admission requires explicit DC and switching passes,
complete hash-matched reports and matching model identities. The retained
[admission audit](reports/clock-output/device-admission/assessment.json) links
those checks to the previously screened oscillator families.

`oscillator_ac_probe.py --seed-transient-op` uses observed voltages as initial
guesses when the default DC solve selects another state. It still rejects a
mismatched observed plateau. Loaded response ratios do not establish loop gain,
stability or identical internal junction states.

Preserve sweep direction and step refinement when comparing transfer curves;
coarse agreement can miss branches. Keep device condition sets separate: a failure
under one device's limits does not automatically reject another device. Retained
fixture interpretations and comparisons are indexed below.

These probes never select a board default. A parameter grid is not a measured
process range or a continuous robustness proof. DC source-current sign changes
identify candidate equilibria; interpolation across a branch jump does not prove
an operating point. Loaded slopes describe that branch, not AC gain or stability.

## Bus and CPU boundaries

Electrical-bus options require declared capacitance and loading assumptions.
Conservative ROM/latch timing envelopes are not measured clone waveforms. The
default CPU remains TV80; explicit read-phase candidates are generated separately
from vendored sources. Their functional success does not establish calibrated
U880 pin timing, reset/bus-grant behavior or synthesis suitability.

At each read, distinguish digital drive intent from analog pin voltage and verify
the CPU's actual latch observation. A released input can fall in the receiver's
unknown band while firmware output still agrees with C. Digital substitutions
and static dependency analysis do not waive that electrical failure. Receiver
limits and their source conditions live in [cpu_clock_limits.json](cpu_clock_limits.json),
not in duplicated documentation tables. Likewise, a linear DC-endpoint driver
is not a complete output I/V or protection model.

## Supply recovery

`boot_cosim.py` and `reset_probe.py` accept `--supply-stimulus` with a JSON waveform
such as [supply-stimuli/brownout.json](supply-stimuli/brownout.json). Pass its path
relative to the working directory or an absolute path. The waveform must span the
simulation interval from zero time/voltage; it is mutually exclusive with
`--rise-us`. Set the reset probe's `--stop-seconds` to the waveform endpoint.
The normalized stimulus and its hash remain with the run.

With electrical outputs enabled, the waveform drives the host side of the cable
and filter; otherwise it drives board supply directly. The sample dip is
illustrative. Custom-supply runs are diagnostic: normal-boot checks do not qualify
brownout restart, and paired board qualification rejects them. Each valid-supply
interval needs its own reset evidence; startup reset cannot prove recovery after
a later dip. Sampled low-reset cycles do not establish between-sample behavior or
CPU state retention.

`--reset-load reference-capacitance` uses the sourced U880 maximum input
capacitance with its stated conditions; the default `illustrative` profile remains
an assumption. Neither includes complete leakage, protection or retention behavior.

## Cable filter hypotheses

`output_probe.py --coupling 0.8 --dot-pins 1 2 1 1 --out /tmp/filter-review`
exercises a uniform mutual-inductance hypothesis. Dot terminals are listed in
L1.1 through L1.4 order; they are not identified specimen winding polarities.
The default remains uncoupled. The shared circuit generator accepts the same
options; firmware runners currently retain the default.

The model uses positive coupling below unity and explicit winding reversal,
following the [ngspice mutual-inductor convention](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).
Analytical common/differential-mode checks verify the generated linear network.
These checks do not identify inductance, coupling, ferrite losses, saturation or
parasitics. Fixture passes cover steady levels and release behavior, not absolute
receiver limits; inspect retained transient extrema as well.

## Host receiver

[Host receiver evidence](host_receiver.json) identifies the motherboard passives
and buffers between the cable and SIO. Review voltages at the appropriate node:
SIO limits do not apply directly to the cable. Host winding values and generic
buffer dynamics remain assumptions. [D104 conditions](d104_limits.json) and
[U856 conditions](u856_limits.json) own the sourced limits and their applicability.

The output probe, service firmware runner and closed-board runner support
`--host-buffer`. The closed-board runner also requires `--electrical-outputs`
and retains onboard oscillator/reset and closed bridges. Explicit SIO capacitance and leakage
must be supplied together; use the runners' `--help` for arguments. Positive
leakage draws current to ground. Source-informed loads are stress assumptions,
not calibrated I/V curves or identified Schmitt thresholds.

Host sampling follows rising RxC, paired with falling keyboard cable clock;
see the [receive-edge review](reports/host-receive-edge/assessment.json).
Earlier falling-edge comparisons do not qualify that sampling point. Retained
waveform hashes identify which voltage reviews remain applicable. The evidence
index below owns links to current coverage and convergence results.

`host-trace.txt` separates cable, buffer-input and buffer-output voltages. Service
reviews require the complete service interval. Board input reviews cover only the
recorded window, preserve producer failures and make no startup-voltage claim.
Both paired electrical qualifiers reject experimental host-buffer runs pending
device, voltage and timing qualification.

| Review | Command (scripts in this directory) |
| --- | --- |
| Passive or active standalone fixture | `ttl7406_output_probe.py --host-passives --out RUN`; add `--host-buffer` for the active candidate |
| Selected buffer DC conditions | `ttl7404_probe.py --out RUN` |
| Buffer-input stress | `host_input_review.py --run RUN --out REPORT`; add `--firmware` for service or `--board` for closed-board captures |
| Service serial-edge refinement | `compare_firmware_io.py COARSE FINE --experimental-host --out REPORT` |
| Absolute-time host-voltage differences | `host_waveform_comparison.py COARSE FINE --out REPORT` |
| Exact samples around maximum differences | `host_transition_windows.py COMPARISON COARSE FINE --out DIRECTORY` |
| Clock-width screen | `host_clock_widths.py RUN --out REPORT`; add `--board` for the recorded closed-board window |

The host capture reviews retain `qualified: false`. Input stress review distinguishes
static bounds from conditional pulse allowances; a voltage minimum cannot
establish duty or unknown input current. Voltage comparisons use retained sample
knots without phase alignment; local transition windows do not prove whole-waveform
convergence. Clock-width screens use an explicit nominal threshold, not measured
Schmitt switching. Board clock reviews preserve producer failures and censored
window ends; they cannot establish pulse widths before the capture starts. The
evidence index below links results and remaining limits.

## Qualification and retained evidence

Keep numerical convergence, model applicability, firmware behavior and specimen
calibration separate. Paired runs must preserve inputs, models, runtime and
assumptions apart from the refinement under test. Preserve full source precision;
rounded supply captures can hide startup sensitivity. Do not align away phase
errors, discard startup or ease budgets to pass. If startup uncertainty needs a
different analysis, make it explicit and independently justified. Numerical
threshold crossings do not replace guaranteed receiver levels.

Use this question-based index to find retained evidence. Assessments own exact
settings, results and rejected alternatives; related captures remain in
[reports](reports/). Use git history for the sequence of investigations.

| Qualification question | Evidence and boundary |
| --- | --- |
| Does the host-loaded closed board complete? | [Closed-board execution review](reports/board-host-load/assessment.json); the bounded full run timed out, while an unchanged-circuit startup diagnostic completed. Neither establishes full-board acceptance. |
| Does corrected host sampling cover service scenarios? | [Single press](reports/firmware-host-rising-load-fine/assessment.json), fixed-spacing [reset](reports/firmware-host-rising-reset-minbreak-fine/assessment.json) and [modifier](reports/firmware-host-rising-modifier-minbreak-fine/assessment.json) pairs pass packet coverage, sampled stability and serial-edge refinement. Remaining scenarios and device qualification are open. |
| Do loaded voltage waveforms converge? | [Further refinement](reports/firmware-host-rising-load-refined/assessment.json) does not consistently reduce absolute-time differences; the [spacing control](reports/firmware-host-rising-load-minbreak-25ns/assessment.json) leaves those waveforms unchanged. |
| What constrains the strict-tolerance failure? | [Transition audit](reports/firmware-host-rising-load-transition-audit/assessment.json) and [matched-control replay](reports/host-analog-driver-replay-matched-trtol/assessment.json) narrow the transition investigation. Preserving effective XSPICE truncation control also fails without HDL feedback; trajectory identity and the original cause remain unresolved. |
| Does the independent solver resolve the loaded-driver transition? | [Mapped ngspice control](reports/host-driver-mapped-ngspice/assessment.json) changes transition voltages; [Xyce replay](reports/host-driver-mapped-xyce/assessment.json) aborts during startup before the target transition. Neither establishes waveform equivalence or a shared failure mechanism. |
| Does the service configuration work? | [Service repeat qualification](reports/repeat/refined-strict-time/qualification/qualification.json); externally supplied clock/reset do not qualify closed-board startup. |
| Is startup numerically converged? | [Full-precision supply isolation](reports/clock-output/full-precision-supply-isolation/assessment.json) and [independent solver replay](reports/clock-output/xyce-recorded-supply/assessment.json); retain absolute phase and failing startup. |
| Does the gate model apply to the device? | [A7 identity and passport checks](reports/clock-output/k555la3-device-review/assessment.json), [candidate admission](reports/clock-output/device-admission/assessment.json) and [output I/V review](reports/clock-output/ls00-output-iv/assessment.json); selected DC/switching passes do not qualify oscillator dynamics or historical process parameters. |
| Why do admitted candidates settle? | [Complete-oscillator disturbance](reports/clock-output/oscillator-disturbance/assessment.json) and [matched-plateau AC response](reports/clock-output/oscillator-ac/assessment.json); the [internal-state capture](reports/clock-output/oscillator-internal/assessment.json) resolves candidate currents for the second gate's state and response investigation. Finite recovery and loaded ratios are not general stability proofs; the incomplete pole search is rejected. |
| Do transfer branches depend on the solver? | [Published fixture review](reports/clock-output/ls00-transfer500/assessment.json) and [Xyce replay](reports/clock-output/xyce-transfer500/assessment.json); fixture alternatives and explicit runtime temperatures remain part of the comparison. Solver agreement is not calibration. |
| Do device conditions or input-junction assumptions resolve startup? | [Device-condition and diode review](reports/clock-output/diode-role-review/assessment.json); selected TI/К555ЛА3 DC checks remain distinct from dynamic applicability. |
| Are CPU reads electrically valid? | [Electrical-bus assessment](reports/rom-read-envelope/electrical-bus/assessment.json) and [floating-read analysis](reports/floating-io/static-analysis.json); functional agreement does not qualify released input voltage. |
| Are receive-clock pulses wide enough at the assumed threshold? | [Loaded service assessment](reports/firmware-host-load/assessment.json) and [clock widths](reports/firmware-host-load/clock-widths.json); complete sample-bracket intervals pass the reference screen. Schmitt thresholds, supply applicability and censored intervals remain unqualified. |
| Is the host buffer switching model qualified? | [D104 switching fixture review](reports/host-buffer-switching/assessment.json); threshold timing converges under explicit generator assumptions, but incomplete fixture parameters and uncalibrated device dynamics prevent qualification. |
| Does an active host buffer change the rejected input pulses? | [Buffer candidate review](reports/host-buffer/assessment.json); selected DC and nominal fixture checks pass for the explicit candidate, while clamp dynamics, device applicability and SIO loading remain unqualified. |
| Where does the cable terminate electrically? | [Host input review](reports/host-receiver/assessment.json); factory and redrawn schematics place passive filters before D104 buffers. The passive boundary changes loading and undershoot but does not qualify the active receiver. |
| How does cable coupling affect the nominal output fixture? | [Filter hypotheses](reports/filter-coupling/assessment.json); similar release intervals can coexist with materially different transient undershoot. No historical winding parameters or receiver clamp behavior are qualified. |
| Does reset recover after a supply dip? | [Reset dip response](reports/reset-brownout/report.json); startup reset and sampled recovery do not establish reliable firmware restart. |

## Review and store captures

Use `review_firmware_run.py --run /path/to/failed-run --rom /path/to/s600.bin
--out /tmp/firmware-review` to recheck an archived failure without rerunning SPICE.
It verifies input hashes and independently reviews bus, cable and reference-bit
behavior while leaving the original report unchanged. A labelled confirmed-prefix
review is diagnostic only; it cannot qualify an incomplete run. Narrow historical
recheck tools are not general waivers for failing assertions.

For large new runs, `--compress-traces` retains lossless traces and producer hashes.
Completed captures can be compacted afterward:

```sh
python3 verification/robotron-keyboard/analog/compress_trace.py /path/to/completed-run
```

The tool verifies report hashes and decompressed bytes before removing raw copies.
Readers accept compressed traces while hashes still identify original bytes.
Use `--clock-probe` for an individually completed early clock run, even when its
later paired phase check failed. Never compact an active capture. Partial or
failed runs must retain their evidence; storage changes cannot turn them into
passes. Validator timeouts can be extended independently of electrical budgets
when decompression or review takes longer.
