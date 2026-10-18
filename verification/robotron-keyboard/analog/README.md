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
between the two halves of a qualification.

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

For candidate-model diagnosis, use fresh output directories and the probes' `--help`:

| Task | Entry point |
| --- | --- |
| Screen generic junction parameters against isolated device conditions | `ls00_parameter_screen.py --out /path/to/screen` |
| Test a standalone model in the oscillator | `oscillator_probe.py --gate-model /path/to/candidate.cir --require-phase --out /path/to/run` |
| Test every surviving candidate after verifying its receipts | `oscillator_family_probe.py --screen /path/to/screen --out /path/to/run` |
| Compare forward/reverse DC branches with schematic loading | `oscillator_transfer_probe.py --model /path/to/candidate.cir --out /path/to/run` |
| Check isolated-gate internal currents and numerical-conductance sensitivity | `ls00_branch_probe.py --model /path/to/candidate.cir --gmin 1e-15 --out /path/to/run` |
| Check finite input-disturbance recovery on both branches | `ls00_branch_transient.py --model /path/to/candidate.cir --out /path/to/run` |
| Check complete-oscillator recovery after finite current disturbances | `oscillator_disturbance.py --model /path/to/candidate.cir --out /path/to/run` |
| Check the photographed K555LA3 device’s selected DC passport conditions | `ls00_validation_probe.py --device k555la3 --model /path/to/candidate.cir --out /path/to/run` |
| Compare small-signal response at an observed transient plateau | `oscillator_ac_probe.py --model /path/to/candidate.cir --transient /path/to/disturbance-capture --out /path/to/run` |
| Inspect internal currents and transistor state at a retained AC plateau | `oscillator_internal_probe.py --ac /path/to/ac-capture --out /path/to/run` |
| Compare transfer branches under alternative 500-ohm fixtures | `ls00_transfer_fixture.py --model /path/to/candidate.cir --out /path/to/run` |
| Replay a completed transfer capture in Xyce | `xyce_transfer_fixture.py --source /path/to/transfer-capture --xyce /path/to/Xyce --out /path/to/run` |
| Capture forced-output I/V beyond the rated-load endpoints | `ls00_iv_probe.py --model /path/to/candidate.cir --out /path/to/run` |
| Screen high-current gain rolloff with DC and switching holdouts | `ls00_rolloff_screen.py --model /path/to/candidate.cir --out /path/to/run` |
| Screen sink base/collector/emitter resistance assumptions with the same holdouts | `ls00_rolloff_screen.py --parameter RB` (or `RC`, `RE`) with the model/output arguments above |

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

`ttl7406_output_probe.py --host-passives --out /tmp/host-input-review` includes
the motherboard input chokes, pull-ups and RC filters documented in
[host receiver evidence](host_receiver.json). It compares voltage at the D104
buffer inputs, retaining cable-terminal voltages separately. The SIO is downstream
of the buffers; its pin limits must not be applied directly to cable voltages.
Host winding values remain assumptions. Add `--host-buffer` to exercise the
experimental standard-7404 transistor topology with input reverse beta 0.01.
`ttl7404_probe.py --out /tmp/7404-dc` screens selected D104 DC conditions; it
does not calibrate input clamps or switching. Buffer outputs use illustrative SIO
loads. Both the output probe and service firmware runner accept explicit
`--sio-data-pf`, `--sio-clock-pf` and `--sio-leakage-ua` together with `--host-buffer`;
positive leakage draws current from the input to ground. The
[load screening](reports/host-loads/assessment.json) retains the tested cases;
the [loaded firmware observation](reports/firmware-host-load/assessment.json)
checks an explicit load through the service fixture.
The [U856 source review](u856_limits.json) constrains leakage and capacitance
without supplying exact I/V or Schmitt thresholds; clock-capacitance pin coverage
remains explicit. `firmware_io_cosim.py --host-buffer --serial-driver 7406-dc` includes
this experimental network in the service firmware fixture. The observer samples
the falling buffer-output clock and uses the output data without cable inversion;
`host-trace.txt` retains cable, buffer-input and buffer-output voltages separately.
Electrical-bus preparation supports the same option. `boot_cosim.py --host-buffer`
also includes this network with the onboard oscillator/reset and closed bridges;
it requires `--electrical-outputs` and accepts the same explicit SIO load arguments.
Both paired qualifiers reject experimental host-buffer runs pending device,
receiver-voltage and timing qualification. Service-only review commands do not
validate the closed-board capture window or startup. Use
`host_input_review.py --board --run /path/to/board-run --out /tmp/board-inputs.json`
for source-hashed input stress within the recorded board window. A completed
voltage review preserves any functional failure and makes no startup-voltage claim.
For numerical diagnosis only, run
`compare_firmware_io.py COARSE FINE --experimental-host --out /tmp/host-convergence.json`.
This checks matching model/runtime inputs and serial-edge refinement while retaining
`qualified: false`; it does not bypass the paired electrical qualification gate.
`host_waveform_comparison.py COARSE FINE --out /tmp/host-voltages.json` compares
all retained host-voltage sample knots at absolute time using linear interpolation.
It reports maximum differences without phase alignment or a physical-accuracy claim.
`host_transition_windows.py COMPARISON COARSE FINE --out /tmp/host-windows`
retains exact producer samples with bracketing points around the maximum differences.
The [transition review](reports/host-transition-windows/assessment.json) distinguishes
local edge shifts from whole-waveform or physical qualification.

Use `host_input_review.py --firmware --run /path/to/service-run --out /tmp/input-limits.json`
for a retained host-buffer firmware capture; it verifies artifact hashes, observed
nodes and full capture extent before reviewing input stress. For standalone fixtures,
`host_input_review.py --run /tmp/host-input-review --out /tmp/input-limits.json`
checks retained buffer-input waveforms against [RFT D104D conditions](d104_limits.json).
It distinguishes static bounds from the conditional negative-pulse allowance;
duty and unknown input currents cannot be inferred from a voltage minimum.
A completed review is not an electrical acceptance pass.

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
| Does the service configuration work? | [Service repeat qualification](reports/repeat/refined-strict-time/qualification/qualification.json); externally supplied clock/reset do not qualify closed-board startup. |
| Is startup numerically converged? | [Full-precision supply isolation](reports/clock-output/full-precision-supply-isolation/assessment.json) and [independent solver replay](reports/clock-output/xyce-recorded-supply/assessment.json); retain absolute phase and failing startup. |
| Does the gate model apply to the device? | [A7 identity and passport checks](reports/clock-output/k555la3-device-review/assessment.json), [candidate admission](reports/clock-output/device-admission/assessment.json) and [output I/V review](reports/clock-output/ls00-output-iv/assessment.json); selected DC/switching passes do not qualify oscillator dynamics or historical process parameters. |
| Why do admitted candidates settle? | [Complete-oscillator disturbance](reports/clock-output/oscillator-disturbance/assessment.json) and [matched-plateau AC response](reports/clock-output/oscillator-ac/assessment.json); the [internal-state capture](reports/clock-output/oscillator-internal/assessment.json) resolves candidate currents for the second gate's state and response investigation. Finite recovery and loaded ratios are not general stability proofs; the incomplete pole search is rejected. |
| Do transfer branches depend on the solver? | [Published fixture review](reports/clock-output/ls00-transfer500/assessment.json) and [Xyce replay](reports/clock-output/xyce-transfer500/assessment.json); fixture alternatives and explicit runtime temperatures remain part of the comparison. Solver agreement is not calibration. |
| Do device conditions or input-junction assumptions resolve startup? | [Device-condition and diode review](reports/clock-output/diode-role-review/assessment.json); selected TI/К555ЛА3 DC checks remain distinct from dynamic applicability. |
| Are CPU reads electrically valid? | [Electrical-bus assessment](reports/rom-read-envelope/electrical-bus/assessment.json) and [floating-read analysis](reports/floating-io/static-analysis.json); functional agreement does not qualify released input voltage. |
| Does firmware traverse the experimental host receiver? | [Service firmware observation](reports/firmware-host-buffer/assessment.json) and [paired numerical review](reports/firmware-host-buffer-fine/assessment.json); logical comparison, serial-edge refinement, sampled stability and input stress pass, but absolute-time voltage comparison exposes substantial transition differences. Full waveforms remain local; voltage convergence, device/loading and closed-board qualification remain open. |
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
