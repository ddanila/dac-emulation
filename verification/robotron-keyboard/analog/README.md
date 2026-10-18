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
| Capture forced-output I/V beyond the rated-load endpoints | `ls00_iv_probe.py --model /path/to/candidate.cir --out /path/to/run` |

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

## Qualification and retained evidence

Keep numerical convergence, model applicability, firmware behavior and specimen
calibration separate. Paired runs must preserve inputs, models, runtime and
assumptions apart from the refinement under test. Preserve full source precision;
rounded supply captures can hide startup sensitivity. Do not align away phase
errors, discard startup or ease budgets to pass. If startup uncertainty needs a
different analysis, make it explicit and independently justified. Numerical
threshold crossings do not replace guaranteed receiver levels.

The following retained evidence anchors the unresolved questions; reports contain
exact settings and results. Older experiments remain in [reports](reports/) and
git history without a second chronological narrative here.

| Evidence | Interpretation boundary |
| --- | --- |
| [Service repeat qualification](reports/repeat/refined-strict-time/qualification/qualification.json) | Pass applies to its recorded service configuration, not closed-board startup |
| [Full-precision supply isolation](reports/clock-output/full-precision-supply-isolation/assessment.json), [Xyce replay](reports/clock-output/xyce-recorded-supply/assessment.json) | Startup phase sensitivity remains a qualification problem across solvers |
| [Vendor reference review](reports/clock-output/ti-reference-review/assessment.json), [transistor candidate](reports/clock-output/ti-transistor-candidate/assessment.json) | Available model files do not by themselves satisfy device limits |
| [Device parameter screen](reports/clock-output/ls00-parameter-validation/assessment.json), [oscillator family](reports/clock-output/ls00-family-oscillator/assessment.json) | Passing isolated device checks does not establish sustained oscillation or DL000 applicability |
| [Loaded transfer comparison](reports/clock-output/ls00-transfer/assessment.json), [bidirectional branches](reports/clock-output/ls00-branches/assessment.json) | Branch-dependent solutions require circuit and solver diagnosis; they are not measured device hysteresis |
| [Isolated-gate current balance](reports/clock-output/ls00-internal-kcl/assessment.json) | Both branches persist with reduced numerical conductance and pass reported-current KCL; this does not prove stability or physical hysteresis |
| [Branch perturbation recovery](reports/clock-output/ls00-branch-perturbation/assessment.json) | Both branches recover after the tested input disturbances; plateau refinement is not full transient convergence or a general stability proof |
| [Output I/V and topology review](reports/clock-output/ls00-output-iv/assessment.json) | Large forced-output current discrepancy from TI typical curves; unspecified graph conditions preclude an exact fitting target |
| [Electrical-bus assessment](reports/rom-read-envelope/electrical-bus/assessment.json), [floating-read analysis](reports/floating-io/static-analysis.json) | Functional agreement does not qualify the released input voltage |
| [Reset dip response](reports/reset-brownout/report.json) | No sampled low CPU reset at valid supply during recovery in this fixture; reliable restart remains unproved |

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
