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

The optional [input-boundary patch](engine-patches/cosim-input-barrier.patch)
settles the analog circuit at queued input boundaries before irreversible HDL
consumption. Apply it when building ngspice 47, or use
`build_cosim_input_barrier.py --help` to rebuild the digital code-model library
from a fingerprinted existing build. Select its `spinit` explicitly; do not mix
patched and control runtimes within a refinement pair. The bus diagnostic workflow
exposes the patch and qualified digital CPU as explicit options.

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
Use `--capture-startup` to retain waveforms from time zero when reviewing reset
and startup; a tail capture cannot prove events before its saved window. Allow
for both simulation and trace output when setting the execution timeout.
The paired target runs coarse/fine captures and applies qualification checks.
Retained pairs can be checked separately:

```sh
python3 verification/robotron-keyboard/analog/qualify_board_pair.py /path/to/coarse /path/to/fine --out /tmp/board-qualification.json
```

`coupled_acceptance.py --help` provides paired service scenarios with the qualified
CPU and explicit reference loads. It stops subsequent scenarios when an earlier
service prerequisite fails and records them as untested. Its service result does
not accept onboard startup or supply recovery. `startup_boundary_screen.py` checks
a bounded initial interval from a prepared closed-board deck; no rated-supply
samples means that clock acceptance is unproven, not that it passes.

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
| Output-driver DC and switching | [ttl7406_probe.py](ttl7406_probe.py), [ttl7406_switching.py](ttl7406_switching.py) |
| Cable/output/indicator behavior | [output_probe.py](output_probe.py), [firmware_io_cosim.py](firmware_io_cosim.py) |
| Failed driver transition | [driver_boundary_replay.py](driver_boundary_replay.py), [analog_driver_replay.py](analog_driver_replay.py); the latter replaces HDL feedback with sampled PWL stimulus and an explicit diagnostic continuation |
| Reference-node sensitivity | [reference_node_replay.py](reference_node_replay.py) runs an explicit-reference control; `--shift-reference` moves numerical ground to the host while preserving branch sources, old-ground substrates and voltage observations. Only the matched analog-only fixture is admitted. |
| Saved trajectory versus internal solver trials | [state_trajectory_review.py](state_trajectory_review.py) matches exact sample times and logged voltages; [retained reviews](reports/host-state-trajectory/assessment.json) distinguish saved excursions from unsaved trials. |
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

Candidate probes expose their arguments through `--help`; assessments retain
fixture settings and commands. Start with [ls00_validation_probe.py](ls00_validation_probe.py)
for independent device conditions and [oscillator_family_probe.py](oscillator_family_probe.py)
for admitted-model startup. Transfer, internal-state and independent-solver
investigations are linked in the evidence index below.

`oscillator_family_probe.py --validate-screen-only` checks candidate admission
without running oscillators. Admission requires explicit DC and switching passes,
complete hash-matched reports and matching model identities. The retained
[admission audit](reports/clock-output/device-admission/assessment.json) links
those checks to the previously screened oscillator families.

`oscillator_ac_probe.py --seed-transient-op` uses observed voltages as initial
guesses when the default DC solve selects another state. It still rejects a
mismatched observed plateau. Loaded response ratios do not establish loop gain,
stability or identical internal junction states.

Preserve sweep direction and step refinement when comparing transfer branches.
Interpolation across a branch jump does not prove an operating point, and loaded
slopes do not establish AC gain or stability. Candidate probes do not select a
board default; a parameter grid is not a measured process range.

## Bus and CPU boundaries

Electrical-bus options require declared capacitance and loading assumptions.
Conservative ROM/latch timing envelopes are not measured clone waveforms. The
default CPU remains legacy TV80 for reproducibility. Select
`--cpu-profile qualified-digital --electrical-bus` to use the accepted reference
CPU boundary and production C service reference; specify the bus capacitance
fixtures explicitly. This profile enables refresh and observes the actual input
latch at the selected edge. Explicit read-phase candidates remain available. Their functional success does not establish calibrated
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
The default remains uncoupled. Service and closed-board firmware runners accept
`--filter-coupling` and `--filter-dot-pins` for the same hypothesis; closed-board
runs require electrical outputs. Reports retain the filter assumptions, and
refinement pairs must use identical values. The [photo review](reports/filter-coupling/photo-review.json)
supports investigating a common core without identifying its parameters or terminals.

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
declared capture window and preserve producer failures. Startup review requires
a capture beginning at time zero; a tail capture supplies no earlier voltage evidence.
Both paired electrical qualifiers reject experimental host-buffer runs pending
device, voltage and timing qualification.

| Review | Command (scripts in this directory) |
| --- | --- |
| Passive or active standalone fixture | `ttl7406_output_probe.py --host-passives --out RUN`; add `--host-buffer` for the active candidate |
| Selected buffer DC conditions | `ttl7404_probe.py --out RUN` |
| Buffer-input stress | `host_input_review.py --run RUN --out REPORT`; add `--firmware` for service or `--board` for closed-board captures |
| LED sequence and timing | `compare_led_reference.py RUN --out REPORT`; `compare_led_pair.py COARSE FINE --out REPORT` (add `--experimental-host` for unqualified host-loaded timing review) |
| Service serial-edge refinement | `compare_firmware_io.py COARSE FINE --experimental-host --out REPORT` |
| Absolute-time host-voltage differences | `host_waveform_comparison.py COARSE FINE --out REPORT` |
| Exact samples around maximum differences | `host_transition_windows.py COMPARISON COARSE FINE --out DIRECTORY` |
| Sampled receiver setup/hold | `receiver_margins.py RUN --required-ns 140 --out REPORT`; add `--board` for a closed-board host capture (diagnostic only) |
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
| Does live reset-release converge? | The [transient-error refinements](reports/transient-error-refinement/assessment.json) pass the unchanged full-window voltage gate with identical observed bus events. The explicit-default control reproduces all baseline waveforms. This qualifies the bounded reset-release comparison with ideal external clock/reset; full-repeat traffic, coupled rollback and physical device/load admission remain open. [Filter diagnostics](reports/filter-truncation/assessment.json) and [history sensitivity](reports/filter-charge-history/assessment.json) retain the numerical investigation and its limits. |
| Which reset-capacitor orientation does the reference support? | [Signed-voltage diagnostic](reports/reset-capacitor-polarity/assessment.json) and [proposed polarity](reports/reset-capacitor-polarity/proposed-polarity.json). Reproduce with `reset_capacitor_polarity.py --out <directory>`; complete compressed traces are local outputs. Does not identify installed polarity or admit real capacitor behavior. |
| Does the C4 source disagreement change reset release? | [Source variants](reset-capacitance-sources.json), [generic comparison](reports/reset-capacitance/generic/assessment.json) and [SC236 DC-profile comparison](reports/reset-capacitance/sc236-dc/assessment.json). Isolated startup/recovery timing with fixed loads; no installed-value or full-board qualification. Reproduce with `reset_capacitance_review.py --out <directory>` and optionally `--npn-profile sc236-dc`; complete compressed traces are local outputs, while decks, logs and hash receipts are retained. |
| Does the host-loaded closed board qualify? | [Startup-inclusive capture](reports/board-host-rising-full-startup/assessment.json) passes reset, bit transport and scenario-window checks with rising RxC. Host voltage, nominal-threshold width and sampled-stability screens complete, but CPU clock high-level and timing screens fail. Refinement, supply recovery and device qualification remain open. |
| Does corrected sampling cover service scenarios? | [Single press](reports/firmware-host-rising-load-fine/assessment.json), [reset](reports/firmware-host-rising-reset-minbreak-fine/assessment.json), [modifier](reports/firmware-host-rising-modifier-minbreak-fine/assessment.json), [release/repress](reports/firmware-host-rising-release-repress-minbreak-fine/assessment.json) and [control](reports/firmware-host-rising-control-minbreak-fine/assessment.json) pairs support logical and serial-edge agreement. The [independent timing screen](reports/host-receiver-timing-review/assessment.json) supports sampled stability, not U856 device applicability. [Indicator refinement](reports/firmware-host-rising-indicators-minbreak-fine/assessment.json) also supports serial and LED intent timing, with ordinal LED agreement against C. Other scenarios and device qualification remain separate. |
| Does the held-key/repeat/release capture pass review? | [Repeat capture](reports/firmware-host-rising-repeat-minbreak/assessment.json) passes sampled voltage-envelope, receiver-stability and nominal clock-width screens. A matched refinement pair and device applicability remain open. |
| Do loaded voltages converge? | [Single-press refinement](reports/firmware-host-rising-load-refined/assessment.json), [release/repress](reports/firmware-host-rising-release-repress-minbreak-fine/assessment.json), [control](reports/firmware-host-rising-control-minbreak-fine/assessment.json) and [indicator comparison](reports/firmware-host-rising-indicators-minbreak-fine/assessment.json) retain material absolute-time voltage differences despite serial-edge agreement. |
| What constrains the strict-tolerance failure? | [Numerical assessment](reports/host-mpfr-transient/assessment.json), [assembly correction](reports/host-postcap-additions/assessment.json) and [history sensitivity](reports/host-history-sensitivity/assessment.json) retain the diagnostic lineage. Higher precision or a corrected frozen system alone has not established a convergent transient remedy. |
| Which alternative solver controls were checked? | [Tighter truncation](reports/firmware-host-strict-trtol-point1/assessment.json) and [KLU](reports/firmware-host-klu-strict/assessment.json) still fail. The [mapped ngspice control](reports/host-driver-mapped-ngspice/assessment.json) and [Xyce replay](reports/host-driver-mapped-xyce/assessment.json) do not establish equivalent trajectories. |
| Does service qualification cover onboard startup? | [Service repeat qualification](reports/repeat/refined-strict-time/qualification/qualification.json) uses external clock/reset. [Supply isolation](reports/clock-output/full-precision-supply-isolation/assessment.json) and [independent startup replay](reports/clock-output/xyce-recorded-supply/assessment.json) retain the separate oscillator convergence question. |
| Are oscillator device models applicable? | [Device-condition review](reports/clock-output/diode-role-review/assessment.json), [candidate admission](reports/clock-output/device-admission/assessment.json) and [output I/V review](reports/clock-output/ls00-output-iv/assessment.json) constrain candidates. [Internal-state analysis](reports/clock-output/oscillator-internal/assessment.json) and [independent transfer replay](reports/clock-output/xyce-transfer500/assessment.json) do not establish calibrated dynamics or general stability. |
| Are CPU reads electrically valid? | [Electrical-bus assessment](reports/rom-read-envelope/electrical-bus/assessment.json) and [floating-read analysis](reports/floating-io/static-analysis.json) separate functional output from released-input voltage and pin timing. |
| Are the host and cable models qualified? | [Host circuit evidence](reports/host-receiver/assessment.json), [filter hypotheses](reports/filter-coupling/assessment.json) and [buffer switching](reports/host-buffer-switching/assessment.json) retain uncalibrated winding, clamp and device assumptions. [Reference 7406 switching](reports/host-driver-switching/assessment.json) leaves driver dynamics unqualified; the [vendor candidate](reports/host-driver-vendor-review/assessment.json) fails SN7406 DC admission. The [matched filter comparison](reports/firmware-filter-strict/assessment.json) finds no convergence remedy in the tested coupling hypothesis. |
| Does reset recover after a supply dip? | [Reset dip response](reports/reset-brownout/report.json) and [recovery screen](reports/supply-recovery-screen/assessment.json) show no sampled reset assertion after supply returns with BR2 closed. Undervoltage state retention is unmodeled; firmware continuation cannot establish a defined restart. [CPU reset timing](cpu_reset_limits.json), qualified clocks, subsequent firmware execution and full-board convergence remain required. |

## Electrical evidence index

[`electrical-status.json`](reports/electrical-status.json) owns the scoped results
consumed by DAC; `electrical_status.py --check` verifies its source hashes.
Use retained assessments for experiment settings, failed alternatives and build
provenance. The table below locates evidence that constrains future work.

| Area | Evidence and development consequence |
| --- | --- |
| HDL input scheduling | [Input-boundary regression](reports/input-barrier/assessment.json), [dispatch regression](test_cosim_dispatch_rollback.py) and [registration regression](test_cosim_registration.py). A sole priority-1 irreversible client must run last. Multiple such clients are not qualified merely because registration permits them. |
| Live dispatch and retry | [Post-reset dispatch](reports/postreset-dispatch/assessment.json), [bridge timing](reports/postreset-bridge/assessment.json) and [Newton retry](reports/postreset-newton-retry/assessment.json). These are reusable complete controls; ordering and monotonic time alone do not prove general internal rollback. |
| Internal state | [Controlled probe](reports/internal-state/assessment.json), [live observer](reports/live-cosim-state/assessment.json), [history](reports/history-state/assessment.json) and [controller event queues](reports/event-state/assessment.json). Bounded state and corruption controls; private HDL and other-model queues are outside their inventory. |
| Scoped non-execution | [Input-barrier source argument](reports/barrier-state-source/assessment.json). Under its pinned pthread assumptions, the successful early return does not resume HDL. Do not demand private queue traversal for that branch or generalize the argument to other callbacks. |
| Private HDL state | [Queue controls](reports/private-hdl-board/assessment.json), [combined callback controls](reports/wrapper-board/assessment.json), [initialized ports](reports/port-board/assessment.json) and [output callback relationships](reports/output-callback-board/assessment.json) preserve bounded board waveform/firmware behaviour and detect restored faults. [Paused startup callback controls](reports/startup-callback-board/assessment.json) cover active lifetime and destruction with restored early faults. Other event payloads/referents, freed storage, startup/recovery and longer-window coverage remain open. Use the scoped [continuation argument](reports/callback-continuation/assessment.json), not raw stack-byte equality. |
| Startup fixes | [History initializer](reports/output-history-init/assessment.json), [repeated-output fix](reports/staged-output/assessment.json) and [combined controls](reports/startup-fixes/assessment.json). [Output-queue](reports/circuit-output-state/assessment.json) and [instance-queue](reports/instance-queue-state/assessment.json) controls cover external scheduling state and detect immediate/delayed faults in the bounded fixture. [Long post-reset controls](reports/postreset-startup-fixes/assessment.json) preserve firmware under forced retry but change electrical waveforms. Keep both fixes opt-in pending their three-level convergence and broader scenarios. Staging repairs lost initial LED events and changes electrical waveforms; initialization seeds are fault controls, not observed specimen behavior. |
| CPU/bus validity | [Bus-device admission](reports/bus-device-admission/assessment.json) and [contract](bus_device_contract.json). Nominal linear drivers fail a minimum-supply high-level guarantee; [DC-only alternatives](reports/bus-endpoint-candidates/assessment.json) satisfy the tested endpoints, but both I8282 candidates fail the independent [loaded rise-time test](reports/bus-switching-candidates/assessment.json). [Enabled-output replacements](reports/i8282-enabled-candidates/assessment.json) satisfy both DC and loaded edge constraints; [joint capacitance checks](reports/i8282-capacitance-candidates/assessment.json) reject combining the weaker candidate with the existing bus fixture capacitance. [Propagation budgets](reports/i8282-propagation-candidates/assessment.json) account for loaded output-stage delay before assigning internal delay; do not reuse the HDL pin-delay maxima as internal drive delays. [Disable-load budgets](reports/i8282-release-candidates/assessment.json) similarly constrain internal disconnect time. [Enable thresholds](i8282_enable_comparison.json) need a source-specific interpretation; NEC comparison limits cannot qualify Intel. Internal dynamics and nonlinear I/V remain unqualified; capacitance bounds apply only within the assumed driver family. CPU/ROM supply laws remain unresolved. Maximum ratings cannot replace operating guarantees; endpoint agreement does not establish I/V or switching behavior. |
| Bus failure isolation | [Bus-read replay](reports/bus-read-replay/assessment.json) and [transition isolation](reports/bus-transition/assessment.json). Independent solver agreement is conditional on recorded boundaries. A replay's completion cannot prove equivalence to live feedback or identify a specimen fault. |
| Live numerical diagnosis | [Live-state review](reports/live-state/assessment.json), [inductor-chain provenance](reports/inductor-chain/provenance.json) and [boundary refinement](reports/boundary-refinement/assessment.json). Preserve the demonstrated arithmetic and scheduling distinctions; completed refinements and lower RMS error do not waive absolute-time voltage peaks. |
| Direct serial driver | [Dynamic candidate](reports/7406-dynamic/report.json), [saved-network review](reports/direct-repeat/assessment.json) and [serial-path admission](reports/serial-path/assessment.json). Typical-delay fitting and selected DC passes leave recovery, reverse operation and load dependence uncertain. CPU drivers remain endpoint fixtures. |
| Evaluator cache | [Runtime recipe](reports/eval-cache/runtime.json) and [post-reset equivalence](reports/postreset-cache/assessment.json). Keep caching opt-in; exact bounded equivalence neither proves full-repeat behavior nor establishes a speedup. |

Use `postreset_startup_capture.py` to reproduce the combined-fix controls on the retained
1.16-ms post-reset fixture without moving reset or shortening the window:

```sh
python3 verification/robotron-keyboard/analog/postreset_startup_capture.py \
  --source build/keyboard-controller-analog/postreset-newton-retry/off \
  --models /private/tmp/k7658-startup-fixes-v1 \
  --runtime /private/tmp/k7658-selectable-retry-runtime \
  --out build/keyboard-controller-analog/postreset-startup-off --mode off
```

Run `combined` and `retry` into separate fresh output directories. The runner
checks pinned inputs/dependencies, caps the log, and retains lossless waveforms.
A completed producer still needs whole-waveform, firmware-continuation and
internal-state review; it is not numerical or full-board qualification.

After both producers complete, run `postreset_startup_review.py` with `--source`
pointing to the same baseline, `--off` and `--combined` to the capture directories,
and `--out` to a fresh assessment JSON. Add `--retry` when that control completes.
The review requires exact disabled-baseline waveforms, compares every saved node
on the absolute-time grids, and reports exact firmware-record agreement. Fix
impact and forced-retry differences remain separate from timestep convergence.

For combined-fix timestep refinement, use `postreset_refinement_capture.py` with
the same `--source`, `--models` and `--runtime`, plus `--coarse` pointing to the
completed combined capture. Run `--step-ns 12.5` and `--step-ns 6.25` into separate
fresh `--out` directories. The runner changes only the transient step, preserves
the complete window and observations, and retains compressed waveforms and logs.
Review both successive waveform differences under the unchanged numerical gate;
producer completion alone does not establish convergence.
Use `postreset_refinement_review.py` with `--source`, the completed `--off`,
`--coarse` (combined) and `--retry` controls, the two refinements as `--fine` and
`--finest`, and a fresh `--out` assessment. It rechecks control evidence, capture
provenance, every voltage's refinement errors and exact firmware records.
The [complete comparison](reports/postreset-combined-refinement/assessment.json)
preserves firmware records and meets the voltage ceiling, but errors grow under
refinement. Its peak-localization excerpts support diagnosis; they do not replace
the full-window gate or justify time alignment.
The [clock-crossing control](reports/clock-crossing-control/waveform-review.json)
checks the existing opt-in ADC localization against analytic fixture timing and
every output sample. Apply it to matched combined-fix board controls before
claiming a convergence correction.
The [bounded board screen](reports/board-adc-crossing-control/assessment.json)
retains complete pre-reset waveforms: both variants complete without simulator
diagnostics, but both retain per-node error-growth failures below one microvolt.
This screen cannot establish post-reset firmware behavior or convergence.
`postreset_adc_capture.py` accepts the same source, coarse control, model and
runtime arguments, plus `--adc-crossings off|on` and `--step-ns 25|12.5|6.25`.
It preserves the full post-reset window; capture completion alone does not pass
the numerical or rollback gates.
Review the three enabled captures with `postreset_adc_review.py --coarse BASELINE
--enabled RUN25 --fine RUN12_5 --finest RUN6_25 --out REPORT`. The review preserves
the numerical gate and checks firmware agreement with the original baseline;
ADC-enabled retry and internal-state coverage remain separate requirements.
The [full post-reset comparison](reports/postreset-adc/assessment.json) fails
non-growing voltage error. Enabled refinements preserve identical firmware
records, but the disabled comparison has one-picosecond bus timestamp differences;
these are retained in [complete selected records](reports/postreset-adc/firmware-differences.json)
and are not waived. Full numerical replay requires the local captures listed in
[retention metadata](reports/postreset-adc/retention.json).
[Timing localization](reports/postreset-adc/timing-localization.json) corroborates
the changed bus times with VPI callback timestamps and locates a middle-step
`data_sink` event one tick late before the largest voltage residual. The [direct bridge controls](reports/input-tick/assessment.json) independently
reproduce history-dependent early input application without an analog circuit.
`numericalGatePassed` is scoped to this window; `qualified` remains false because
startup, supply recovery and device admission need independent evidence.

For longer internal-state controls, use `postreset_state_capture.py` with the
circuit-output observer build and a fresh output directory for each mode. It
streams lossless compressed logs with explicit byte/time budgets and a free-space
reserve. The [immediate fault control](reports/postreset-state-immediate/assessment.json)
validates this capture path.
Group those captures under `root/{off,check,immediate,delayed}` and use
`postreset_state_review.py` with that root, the original `--source` control and
the completed combined-fix `--baseline`. Positive captures must cover the whole
1.16-ms window; expected negative exits cannot satisfy that requirement.
The [complete post-reset output-state controls](reports/postreset-output-state/assessment.json)
preserve all observed samples and firmware continuation, with immediate/delayed
external-output faults detected. Full compressed logs are retained in parts;
[retention metadata](reports/postreset-output-state/retention.json) locates complete
local waveforms and the review command. This closes that control window, not
startup, supply recovery, instance queues or private HDL events.
For standalone inventory review, `cached_circuit_output_review.py <log> --out <json>`
uses bounded caching of repeated port records while checking every snapshot and
event. Its [equivalence evidence](reports/cached-output-inventory/full-assessment.json)
covers the full post-reset inventory. This command replaces only the inventory
pass; it does not perform waveform, firmware or rollback qualification.
For instance-queue coverage, use the same capture runner with the
`build_instance_queue_audit.py` model build and a separate capture root. Review
with `postreset_instance_review.py`, passing the same `--root`, `--source`,
`--baseline` and `--out` arguments. It retains the complete output-queue,
waveform and firmware checks and additionally verifies instance worklists,
rollback anchors and immediate/delayed external-instance corruption.
Add `--cached-output-inventory` to use the validated port cache in an isolated
reviewer instance. Full waveform, firmware, history and instance checks remain
required; the result records both reviewer sources.
The [complete post-reset instance controls](reports/postreset-instance-state/assessment.json)
preserve all observed waveform samples and firmware records and detect immediate
and delayed external instance-queue mutations. This closes the prescribed
post-reset window for instance queues, worklists and rollback anchors; private HDL
events, freed storage, startup, supply recovery and repeat remain separate.

Use `cpu_reset_setup_review.py --root <completed-boot-capture> --out <assessment.json>`
to check sampled RESET stability against complete CPU-clock voltage rises. It
verifies full clock/supply traces and their time alignment, preserves endpoint and
sample-gap checks, and reports unestablished margins without interpolation. This
is a reset setup screen, not clock, reset-duration or firmware-restart qualification.
The [full startup review](reports/board-host-rising-full-startup/reset-setup-review.json)
finds no qualifying clock voltage rises; it cannot establish RESET setup timing.

Use `build_output_breakpoint_probe.py` and `output_breakpoint_capture.py` for
matched disabled, observed and forced-failure controls after HDL advancement.
`output_breakpoint_review.py --root <capture> --source <baseline> --out <assessment>`
checks complete streams and distinguishes branch activity from equivalence.
The [bounded board fixture](reports/output-breakpoint-controls/assessment.json)
does not exercise output-driven truncation. The
[sampled autonomous fixture](reports/output-breakpoint-sampled/assessment.json)
exercises truncation and recovery while preserving HDL transitions and the
absolute-time waveform comparison. The [sparse control](reports/output-breakpoint-target/assessment.json)
demonstrates sampling error without a demonstrated state defect.
Use `output_breakpoint_fixture.py --sample-grid` for the targeted stimulus and
`--out <report> --verify` to check retained evidence. Keyboard input perturbations
and general rollback remain outside this diagnostic's scope.

### Scheduling and state controls

Apply `ngspice-47-rollback-audit.patch` for accepted/rejected-step and dispatch
logging. `live_raw_output.py --rollback-audit` captures matched disabled/enabled
controls; `rollback_dispatch_review.py` requires identical samples, firmware events
and complete audit coverage before interpreting scheduling. Build a separate bridge
logger with `build_bridge_time_audit.py`, capture with `live_bridge_time_capture.py`
and review with `live_bridge_time_review.py`. Only the identified VPI-library
substitution is permitted. `bridge_rollback_log.py` checks the existing one-tick
time-order guard and distinguishes callbacks from actual advances and outputs.

For forced Newton rejection, apply `ngspice-47-rollback-fault.patch` after the audit
patch and copy `rollback_fault.h` beside `dctran.c`. Use
`live_newton_retry.py --fault-start SECONDS` with that separately pinned runtime
and a complete bridge control. `newton_retry_review.py` checks disabled-control
identity, injection coverage, absolute-time waveforms and firmware continuation.
`retain_newton_retry.py` retains the checked evidence; `--check` verifies it.
Forced rejection tests scheduling, not natural device convergence.

`build_live_state_audit.py`, `live_cosim_state_capture.py` and
`live_cosim_state_review.py` implement the live state controls. History and
controller-output queues use `history_state_capture.py`, `history_state_review.py`
and `event_state_review.py`. `build_startup_fixes.py` composes the independent
opt-in fixes; `startup_fixes_capture.py` and `startup_fixes_review.py` check their
bounded interaction. Do not extend a fixture's coverage claim beyond its declared
reset and endpoint. Firmware and state streams are compared separately because
merged stdout/stderr buffering changes their interleaving. CI checks retained
manifests and damaged-trace controls rather than repeatedly expanding large logs.

### Numerical and device diagnosis

`bus_read_capture.py` and `bus_read_replay.py` reproduce the recorded-boundary bus
comparison. `bus_transition_probe.py` provides tolerance sweeps and output isolation.
Keep input-voltage limits unchanged when investigating driver dynamics.

`build_live_transition_models.py` builds fingerprinted code models;
`live_transition_probe.py` takes explicit runtime inputs. Diagnostic options require
their corresponding patches and provenance: `--state-audit` needs the supplemental
live-state patch; `--mpfr-transition` needs the MPFR linear and live-window patches;
`--filter-trunc-audit` needs the filter patch on the startup-instrumented runtime.
The filter audit is restricted to its coded observation window. Require complete
logging-disabled/enabled waveform equivalence before interpreting records.
`live_state_review.py LOG --out REPORT` replays frozen equations; it does not
establish a corrected transient trajectory.

`--truncation-tolerance` controls transient error separately from Newton tolerances.
Keep it at or below the effective XSPICE default; the explicit-default control must
reproduce the implicit baseline. Retain matched refinements with
`fixture_grid_review.py --experiment transient-error`. Use
`network_refinement_review.py` for the retained network correction and
`saved_network_review.py` for complete-window saved-vector comparisons. A frozen
high-precision solve, successful reduced fixture or short-window comparison cannot
qualify the complete live circuit.

`ttl7406_dynamic.py --out DIRECTORY` fits the exploratory driver and checks withheld
edges/DC conditions; `ttl7406_dynamic_validation.py --device-report REPORT --out
DIRECTORY` checks temperature, loading and intermediate-input settling.
`prepare_dynamic_driver.py` connects the candidate directly to electrical D0/WR;
use `--bus-7406-pf 0` to avoid double-counting its gate capacitance. Observe with
`live_transition_probe.py --network-trace --physical-driver-trace`.
`cpu_serial_drive.py --device-report REPORT --out DIRECTORY` checks the separate
CPU endpoint hypothesis. None of these operations establishes physical admission.

`serial_device_trace.observe` adds internal probes without changing components;
`serial_device_review.py` checks their live control and current balance.
`serial_path_probe.py --live TRACE.xz --device-report REPORT --ngspice RUNTIME
--out DIRECTORY`, `serial_recovery_review.py` and `retain_serial_recovery.py`
reproduce and retain recovery hypotheses. Forced-input replays do not establish
feedback behavior or initialization independence.

### Cache controls

The evaluator cache defaults off. `ROBOTRON_EVAL_CACHE=exact` enables reuse only
within a single value/gradient evaluation. Build from the pinned runtime recipe;
do not use fast-math. `eval_cache_benchmark.py` takes a prepared startup directory
or a `fixture.json` selecting a deck, inputs and traces. Library changes invalidate
paired captures. `live_cache_review.py` permits only the cache-mode change against
a complete bridge control and requires every sample, firmware event and timing
record to match. Full-repeat validation remains deferred.

## Review and store captures

Use `live_transition_probe.py --raw-output --compressed-output
--network-trace --all-saved-network` with the `ngspice-47-raw-pipe.patch` runtime.
Direct raw output bypasses plot accumulation; compressing ordinary output alone
does not reduce ngspice vector memory. The raw mode rejects diagnostic halts. Preserve
the complete scenario endpoint when preparing full-repeat runs; this capture
option does not itself establish scenario coverage or numerical convergence.
Add `--full-scenario` to pin the prepared `scenario.json` and require the complete
endpoint derived from its cycle count and reset interval. The circuit's contact,
reset and fixture-clock sources must implement that scenario. Conflicting stop-time
overrides and diagnostic halts are rejected before running. Completion and
serial observation windows must still pass review after capture.
`full_scenario_review.py --run DIR --out REPORT` streams every saved raw sample,
checks the declared endpoint and signal set, and verifies transmitted/received
serial windows. Its coverage result does not replace firmware-reference, bus,
numerical-refinement or physical-model acceptance.
`full_scenario_refinement.py COARSE MIDDLE FINE --out REPORT` requires complete
captures with two timestep halvings and otherwise identical settings. It compares
every saved voltage at absolute time, requires unchanged firmware/serial records,
and applies the 10 mV and per-node nonincreasing-error gate. It does not replace
the separate disabled control or electrical-model admission.
`retain_full_scenario.py COARSE MIDDLE FINE --out DIR` runs that review before
archiving receipts, decks, scenarios, frozen generators and compressed logs.
Raw waveforms stay local with recorded hashes. `--check --out DIR` verifies the
retained manifest and event consistency; it does not repeat the raw comparison.
`retain_live_raw.py` retains checked receipts while keeping full compressed captures
locally; `--check --out reports/live-raw-output` verifies the retained manifest.
`--all-saved-network` selects every saved observation; `complete_network_review.py --end-seconds` requires the
explicit complete interval. Retention preserves every available sample, including
failed controls. Longer runs need a concrete board/receiver decision, not merely
an improved private fixture waveform.

Retry and cache reviews stream audit records and firmware events; dispatch summaries
do not retain accepted-point histories. The [complete-capture comparison](reports/streaming-audit/assessment.json)
preserves the previous post-reset assessments. Bridge, retry, raw-output and
`live_cache_capture.py` producers compress audit stdout alongside waveforms, retaining
logical hashes and publishing outputs only after compression completes. Failed captures
remain partial and cannot satisfy completion checks. The transport replay establishes
lossless storage, not a new numerical run or full-repeat storage feasibility.
`raw_stream_review.py` can compare raw pipes before final producer counts are
available, then requires independent completion counts before returning success.
The [complete replay](reports/online-stream-replay/assessment.json) matches the
retained retry comparison and input hashes without a raw spool.
`stream_refinement_capture.py` runs three matched live producers, drains compressed
logs independently and compares both adjacent pairs with bounded raw pipes.
`--max-log-bytes`, `--max-compressed-log-bytes` and `--max-log-line-bytes`
bound total logical logs, total retained compressed logs and individual diagnostic
lines. Exceeding a budget stops the producers and retains a failure receipt and
partial logs, never a successful comparison. Choose budgets before launching;
these limits do not bound total process memory or establish full-repeat capacity.
The runner pins inputs and runtime, checks completion, applies the unchanged voltage gate and,
with `--scenario`, checks firmware events and serial windows. The
[live RC control](reports/live-stream-transport/assessment.json) matches stored-waveform
comparisons exactly. Raw bytes are hashed but not retained for later replay; compressed
logs still require disk space. The [bounded keyboard benchmark](reports/keyboard-stream-benchmark/assessment.json)
measures the complete observer fixture with three refinements and sampled process-tree
RSS. It retains compressed logs, comparison receipts and runtime/input identities.
The strict non-growing-error gate fails despite differences below the voltage limit.
Its resource measurements do not bound full-repeat costs, and raw hashes cannot
replace replayable waveforms when a different numerical review is needed.
`retained_stream_refinement.py` provides a separate retention revision for future
campaigns. It keeps the existing online comparison and scenario checks, while
requiring `--max-raw-bytes` and `--max-compressed-raw-bytes` in addition to the log
caps. These are aggregate budgets across all three producers. Raw streams are
compressed while being forwarded through bounded pipes; complete archives are
published only after producer completion and byte/hash agreement with the
comparators. A budget failure terminates producers and leaves partial evidence.
`retained_stream_review.py CAPTURE` replays every retained sample, checks completion
logs and recomputes storage accounting. It refuses changed waveforms, logs or
receipts. Existing pinned campaigns keep their original transport.
The [live RC retention control](reports/retained-stream-control/assessment.json)
preserves both comparisons exactly against the unretained transport and reproduces
them from compressed archives. Run `retained_stream_control.py --out NEW_REPORT`,
or use `--check` with the retained report. This control does not qualify keyboard
resource budgets or authorize the deferred full-repeat runs.

The [keyboard retention benchmark](reports/keyboard-retained-stream/review.json)
qualifies full waveform retention and replay on the existing complete 20-us
fixture at three timestep levels. Its comparisons exactly match the prior
benchmark, including the failing non-growing-error gate. It compared 21,382,931
raw bytes, retained 10,126,448 compressed raw bytes plus 1,292,740 compressed log
bytes, and completed capture plus replay in 188.33 seconds. The sampled capture
process-tree maximum was 163,024 KiB across 350 samples; this excludes later
replay memory and is not an exact peak. These measurements do not predict
full-repeat cost. `keyboard_retained_benchmark.py` runs the bounded experiment;
`keyboard_retained_review.py --root REPORT --baseline reports/keyboard-stream-benchmark
--out NEW_REVIEW` independently recomputes comparisons, the gate, storage usage
and resource statistics. The retained report also replays with the benchmark's
`--check` option. No full-repeat execution was resumed.

The [post-reset memory observation](reports/postreset-memory-observation/assessment.json)
records live process-tree footprints and per-process kernel peaks on macOS, checked
with an allocation/release control. It excludes exited descendants and future
allocations; it is not a completed-run memory bound.

For evidence larger than the Git hosting file limit, use
`evidence_parts.py pack <completed-file> <archive-directory>`. It preserves the
original bytes in bounded parts with a hash manifest. Before running existing
reviewers, use `evidence_parts.py restore <archive-directory> <original-file>`.
Restoration verifies every part and the whole file before publishing it, and
refuses to overwrite a destination. Keep the original capture until restoration
has been checked; splitting changes storage only, not qualification or replay scope.

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

## Reference CPU clock acceptance

`clock_acceptance.py --out BUILD --retain REPORTS` screens startup from zero
with the reference oscillator wiring and closed BR1 against the published U880
levels and valid-level timing. The [retained screen](reports/clock-acceptance/assessment.json)
keeps supply/load assumptions, model identities, source hashes and complete
lossless captures. Replay their acceptance checks with
`python3 verification/robotron-keyboard/analog/verify_clock_acceptance.py verification/robotron-keyboard/analog/reports/clock-acceptance`.
It is an isolated oscillator screen, not closed-board or
independent device qualification. The reference behavioral models fail; raising
the high level alone does not repair pulse width or slew. Independent intended-family
data around the switching region and under the reference pullup are needed before
admitting a replacement model. Published data may suffice; bench measurements
are a fallback for consequential ambiguities.

## Private callback observation

Use `build_private_sync_family.py --archive PINNED_TARBALL --out FRESH_DIRECTORY
--bison BISON`, then `private_sync_family_probe.py --candidate BUILD_DIRECTORY
--baseline ORIGINAL_LIBVVP --modules VPI_DIRECTORY --out FRESH_REPORT`.
The [family controls](reports/private-sync-family/assessment.json) identify the
loaded display callback by module hash and symbol offset and leave its optional
fields unexamined. Registry bookkeeping is covered by the original-library
baseline. The [bounded board controls](reports/private-sync-family-board/assessment.json)
preserve waveform and firmware output, identify bridge/display callbacks and
detect a restored synchronization-mode fault. Executing wrappers and long-window
qualification remain open.

The [failed board observer](reports/private-sync-discovery/assessment.json) reads
an unset display-callback index. Its legacy API is deliberately rejected by the
new runtime. Use `build_private_sync_family_bridge.py --source NGSPICE_SOURCE
--vpi TIMING_AUDITED_VPI_SOURCE --vpi-header VPI_HEADER --out FRESH_DIRECTORY`
for the paired bridge/VPI with explicit stop-function handoff. Review matched
captures with `private_sync_family_board_review.py --root CAPTURES --producer
CAPTURE_SCRIPT --out REPORT`; a reused original-runtime baseline must retain its
original producer and receipt. Module identification does not establish display
payload coverage. A reason code alone cannot identify a callback's data layout.

The [continuation argument](reports/callback-continuation/assessment.json)
identifies overwritten scalar temporaries at the pinned pthread yield. Preserve
and test the surviving context, live stop-handle relationship and executing
callback/event objects; raw stack-byte equality includes irrelevant temporaries
and padding.

Build the combined runtime/modules with `build_display_association.py --archive
PINNED_TARBALL --out FRESH_DIRECTORY --bison BISON`. Run
`display_association_probe.py --build BUILD --runtime BUILD --modules VPI_DIRECTORY
--out FRESH_REPORT` for vendor, rebuilt, disabled, observed and pointer-swap controls.
[Typed payload evidence](reports/display-payload/assessment.json) covers strobe
metadata, format, supported arguments and registry cleanup. The
[association controls](reports/display-association/assessment.json) link live
callback handles/functions/user data to those payloads and reject swapped user-data
pointers even when payload values stay identical. For board controls, use
`build_display_board_runtime.py` with the same archive/build arguments and
`build_display_board_bridge.py` with the paired bridge/VPI arguments above.
`display_board_capture.py --bridge BRIDGE --icarus RUNTIME --out FRESH_DIRECTORY`
uses the pinned local combined-fix runtime and bounded service fixture. Review with
`display_board_review.py --root CAPTURES --producer display_board_capture.py
--out REPORT`, retaining both build receipts as `bridge-build.json` and
`icarus-build.json` in the capture directory. It requires exact waveform and
firmware agreement across original, rebuilt, observer-disabled and observed
controls, plus rejection/restoration of a single callback's NULL data pointer.
The [bounded board evidence](reports/display-board/assessment.json) passes these
controls and covers typed display associations at paused boundaries. Descriptor
internals, other VPI objects, executing wrappers and longer windows remain separate.

`build_display_stop_bridge.py` accepts the same bridge/VPI build arguments and
adds the saved `stop_cb` relationship to that observer. It uses the live runtime
registry to check the handle, known callback function and context without
reading through a supplied handle. `display_stop_review.py` checks that a saved
handle names the executing delayed stop; a null handle permits startup or an
immediate output-triggered stop. The `stop-corrupt` mode substitutes an invalid
handle and restores it before HDL continuation. Use
`stop_board_capture.py --source DISPLAY_CAPTURES --assessment DISPLAY_ASSESSMENT
--bridge STOP_BRIDGE --out FRESH_DIRECTORY` after the display controls pass;
it reuses their disabled baseline and keeps the same runtime/module. Review with
`stop_board_review.py --root CAPTURES --producer stop_board_capture.py --out REPORT`.
Pass the recorded `SPICE_SCRIPTS` initialization explicitly; a copied runtime
receipt alone does not select its code models ([rejected control](reports/stop-runtime-selection/assessment.json)).
The [bounded stop controls](reports/stop-board/assessment.json) pass exact waveform
and firmware comparisons and reject a restored invalid handle. Longer windows
and freed-storage equivalence remain open.

Build the executing-wrapper candidate with `build_executing_wrapper_runtime.py`
using the same pinned archive arguments. Run `executing_wrapper_probe.py
--candidate BUILD --baseline ORIGINAL_LIBVVP --modules VPI_DIRECTORY --out REPORT`.
The [standalone controls](reports/executing-wrapper/assessment.json) link the live
generic event to its executing synchronization callback and check deletion
ownership across delayed, read/write and read-only callbacks. A changed deletion
flag is restored before callback return. Unknown generic objects fail closed;
other event families and scheduler continuation remain open.

For combined board controls, build `build_executing_wrapper_bridge.py` with the
paired bridge/VPI arguments above. Run `wrapper_board_capture.py --source
REVIEWED_BOARD_CAPTURES --assessment REVIEWED_ASSESSMENT --bridge BRIDGE --icarus
RUNTIME --out FRESH_DIRECTORY`, then `wrapper_board_review.py --root CAPTURES
--producer wrapper_board_capture.py --out REPORT`. The capture reuses the reviewed
disabled baseline, selects its XSPICE initialization explicitly and exercises
separate display-pointer, stop-handle and wrapper-deletion faults. Board
[Retained board evidence](reports/wrapper-board/assessment.json) passes all three
restored faults and exact positive-control outputs over the bounded fixture.


For bridge-port coverage, use `build_port_identity_bridge.py` with the same
paired build arguments, then `port_board_capture.py --source WRAPPER_CAPTURES
--assessment WRAPPER_ASSESSMENT --bridge PORT_BRIDGE --out FRESH_DIRECTORY` and
`port_board_review.py --root CAPTURES --producer port_board_capture.py --out REPORT`.
Canonical handles, context back-references and layout are registered before the
first yield; the review checks layout against the compiled HDL interface.
Handle, context and initialized-value faults are restored before continuation.
The [initialization contract](reports/port-state-contract/assessment.json) excludes
unused input-only `new` words, which the legacy observer read before initialization.
The [bounded port controls](reports/port-board/assessment.json) pass exact waveform
and firmware comparisons, the compiled port contract and all restored faults.
Output value-change callback relationships and longer-window coverage remain open.


For the opt-in tick-conversion candidate, build `build_absolute_tick_vpi.py
--source NGSPICE_SOURCE --vpi TIMING_AUDITED_VPI_SOURCE --vpi-header VPI_HEADER
--out FRESH_DIRECTORY`. `ROBOTRON_ABSOLUTE_TICKS=1` computes the exact floor of the
binary64 absolute target/tick ratio before subtracting the integer current tick;
it does not add a timing tolerance or move inputs onto a rounded-up clock grid.
`input_tick_probe.py --source NGSPICE_SOURCE --candidate BUILD --board-receipt
BOARD_RUN_JSON --out FRESH_DIRECTORY` exercises the real shim with original,
disabled and enabled libraries. Its isolated controls pass, including an
independent rational oracle; board convergence and rollback remain separate.
Use `absolute_tick_board_capture.py --source ORIGINAL_BOARD_BASELINE --candidate
BUILD --out FRESH_DIRECTORY`, then `absolute_tick_board_review.py --root CAPTURES
--producer absolute_tick_board_capture.py --out REPORT` for bounded board and
forced-retry controls. Preserve the original disabled baseline and explicit
XSPICE initialization. Full post-reset refinements must pass the existing gate
before the candidate can be qualified.


After those bounded controls, `postreset_tick_capture.py --source ADC_COARSE
--candidate BUILD --bounded-root BOUNDED_CAPTURES --bounded-assessment ASSESSMENT
--mode MODE --step-ns STEP --out FRESH_DIRECTORY` retains the complete post-reset
window. Run `off` at 25 ns first and require exact original-baseline agreement;
then use `on` at 25, 12.5 and 6.25 ns and `retry` at 25 ns. Review all five with
`postreset_tick_review.py --source ADC_COARSE --off OFF --coarse ON_25 --fine ON_12_5
--finest ON_6_25 --retry RETRY --out REPORT`. The reviewer checks the unchanged
voltage/non-growth gate and firmware across refinements, while reporting the
candidate's original-baseline timing changes and forced-retry effects separately.
The [bounded board controls](reports/absolute-tick-board/assessment.json) preserve
enabled voltages and firmware, including firmware under a forced rejection.
Passing refinement alone does not accept changed baseline behavior or establish
private-HDL rollback. These are post-reset captures, not the deferred full-repeat
campaign.

The [full exact-tick review](reports/postreset-tick/assessment.json) passes the
disabled control but still fails non-growing voltage differences. Its
[firmware comparison](reports/postreset-tick/firmware-comparison.json) separates
changed baseline edge times from preserved payloads and refinement/retry records.
[Peak excerpts](reports/postreset-tick/peak-localization/assessment.json) and
[output events](reports/postreset-tick/event-localization/assessment.json) point to
fractional output-time shifts consistent with the VPI entry-time clamp.
[Native output-time controls](reports/output-drain/assessment.json) reproduce
autonomous events left pending when a timed callback returns to SPICE. The
opt-in same-tick drain defers that return to read/write synchronization, preserving
the entry-time clamp for input-driven events. These native controls do not
establish board convergence or full scheduler quiescence.
Re-extract with `postreset_tick_peaks.py` or `postreset_tick_events.py` using
`--assessment REPORT --coarse ON_25 --fine ON_12_5 --finest ON_6_25 --out FRESH`;
both support `--check` on their retained excerpt directories. Full replay still
requires the local waveforms/logs listed in `reports/postreset-tick/retention.json`.
Build the candidate with `build_output_drain_vpi.py --source NGSPICE_SOURCE
--candidate ABSOLUTE_TICK_BUILD --vpi-header VPI_HEADER --out FRESH`.
`output_time_probe.py` uses the same arguments as `input_tick_probe.py`; replay
with `--check reports/output-drain`. Use `output_drain_board_capture.py` and
`output_drain_board_review.py` with the bounded-board arguments above; they
isolate exact-tick-only behavior from `ROBOTRON_DRAIN_TICK=1` and forced retry.

`build_value_callback_runtime.py` accepts the pinned archive/build arguments above.
Run `value_callback_probe.py --candidate BUILD --baseline ORIGINAL_LIBVVP --modules
VPI_DIRECTORY --out FRESH_DIRECTORY` for the [value-change callback controls](reports/value-callback/assessment.json).
They validate known callback/function/signal/user-data identities and actual list
membership, including shared signals and head/non-head cancellation. Context,
object, function and link faults are restored before callback execution; complete
timestamped output agrees with the original runtime.
The [initialization contract](reports/value-callback/source-contract.json) requires
board integration to store watch-registration identities before port metadata is
initialized, then validate them after initialization. Temporary value buffers are
refreshed before callback use and must not be treated as persistent bridge state.
For board integration, [build the paired bridge](build_output_callback_bridge.py)
with the same pinned ngspice/VPI inputs as the port observer.
[Capture matched controls](output_callback_board_capture.py) from the reviewed
port baseline using that pair and the value-callback runtime;
[review the complete captures](output_callback_board_review.py) for exact disabled
and observed waveform/firmware agreement, stable per-port callback lifetimes and
restored user-data, signal, function and list-link faults. The [retained board controls](reports/output-callback-board/assessment.json) pass these checks. Other callback families,
longer windows and general rollback remain open.

The [startup continuation contract](reports/startup-callback/source-contract.json)
identifies a separate observer requirement: `start_cb` yields through a direct
`next_advance_cb` call while its simulator callback is already removed from the
pending startup list but not yet destroyed. Track that active lifetime separately
from timed wrappers, validate the registered startup function/context, and avoid
reading unspecified suppressed-time words. Empty timed-wrapper inventories do
not prove startup state coverage.

Build this startup observer with `build_startup_callback_runtime.py` using the same
pinned archive/build arguments. `startup_callback_probe.py --candidate BUILD
--baseline ORIGINAL_LIBVVP --modules VPI_DIRECTORY --out FRESH_DIRECTORY` runs the
[standalone controls](reports/startup-callback/assessment.json): pending/active
lifetimes, cancellation, destruction and restored context/function/time/link
faults with exact callback continuation. These controls do not suspend the bridge
coroutine; integration must verify its actual paused startup callback before
startup/recovery rejection checks can establish board coverage.

For paused startup integration, build `build_startup_callback_bridge.py` with the
pinned ngspice/VPI inputs. `startup_callback_board_capture.py` accepts the reviewed
output-callback board baseline and the paired startup runtime/bridge;
`startup_callback_board_review.py` checks unchanged normal waveform/firmware
continuation, active-to-destroyed startup lifetime and restored early faults.
The [retained startup board controls](reports/startup-callback-board/assessment.json) pass this review.
Those fault runs terminate while startup is paused and need not reach a firmware
fetch; the normal controls must cover subsequent firmware execution and all
existing board observers. Passing the standalone probe does not satisfy this
board review.

`build_assignment_runtime.py` adds typed pending vector4/vector8 payload observation
to the combined runtime. Run `assignment_probe.py --candidate BUILD --baseline
ORIGINAL_LIBVVP --modules VPI_DIRECTORY --out FRESH_DIRECTORY` for the
[standalone assignment controls](reports/assignment-payload/assessment.json).
They preserve every fixture output transition under restored value, destination
port, slice-width and strength faults. The [source contract](reports/assignment-payload/source-contract.json)
limits reads to initialized logical vector contents and meaningful slice fields;
destination pointers remain opaque. Target referents and other event families
require their own controls.

For board integration, `build_assignment_bridge.py` takes the pinned bridge/VPI
arguments above. Run `assignment_board_capture.py` against the reviewed startup
board baseline with the paired assignment runtime, then use
`assignment_board_review.py` on the complete captures. It requires both assignment
families, consumption without lifetime reuse, matching native callback/assignment
times, unchanged normal waveform/firmware behaviour and all restored time-zero
faults. The [retained board controls](reports/assignment-board/assessment.json) pass this review.
It keeps unsupported event counts explicit; typed assignment coverage does
not establish the contents of destination nets or other event families.

`build_primitive_runtime.py` adds explicit constructor/destructor registration for
queued inverter and static part-select objects. Run `primitive_probe.py --candidate
BUILD --baseline ORIGINAL_LIBVVP --modules VPI_DIRECTORY --out FRESH_DIRECTORY`
for the [standalone primitive controls](reports/primitive-payload/assessment.json).
They check initialized cached vectors, destinations and slice bounds, stable
primitive identities across requeue, fresh wrapper identities and unchanged output
transitions under restored faults. The [source contract](reports/primitive-payload/source-contract.json)
explains initialization and protected-base identity handoff. Transmission-gate
mesh/port state, thread state and destination referents remain open.

The combined primitive observer uses `build_primitive_bridge.py`,
`primitive_board_capture.py` and `primitive_board_review.py`. Supply a reviewed
assignment-board capture as the baseline and the runtime built by
`build_primitive_runtime.py`. The review includes all preceding observer layers,
allows cached inputs to coalesce while queued, and checks stable primitive
metadata and wrapper lifetimes. The [retained board controls](reports/primitive-board/assessment.json)
pass exact waveform and firmware comparison and restored cached-value, destination
and slice-base faults. Island and thread state remain separate. The
[island source contract](reports/island-source-contract/assessment.json) identifies
persistent idle-island state, enable-only ports and force/filter dependencies for
the next observer; it does not establish runtime coverage.

`build_island_runtime.py` extends the primitive runtime with live transmission-gate
islands, including idle port caches and enable-only imports. `island_probe.py`
uses the same runtime arguments as the primitive probe; its
[retained controls](reports/island-payload/assessment.json) check cache values
against known stimulus/resolution, stable topology and restored cache, strength,
flag, branch-state and mesh faults. Replay with `island_probe.py --check
verification/robotron-keyboard/analog/reports/island-payload`. Queued wrapper
association and filter coverage use the board layers below; idle-island controls
alone do not establish general rollback.

For combined board checks, build `build_island_queue_runtime.py` and
`build_island_bridge.py`, then run `island_board_capture.py` against reviewed
primitive-board controls. `island_board_review.py` requires matching pending flags
and queued island identities, consumption without wrapper reuse, stable topology,
exact normal waveforms/firmware and restored faults. The output-cache fault runs
after initialization; the other faults target paused startup. These controls
pass in the [retained island board evidence](reports/island-board/assessment.json).

`build_island_filter_runtime.py` adds island vec8 wire-filter state.
`island_filter_probe.py` uses the same runtime arguments and checks whole-net,
partial-bit and variable-linked force/release. Its [retained controls](reports/island-filter/assessment.json)
cover driven/forced vectors, masks, initialization/propagation flags and initialized
force-link endpoints. Replay with `island_filter_probe.py --check
verification/robotron-keyboard/analog/reports/island-filter`. The
[source contract](reports/island-filter/source-contract.json) bounds meaningful
field reads; callback lists, force-link functors and net fanout remain separate.
Combined board controls are linked below.

`build_island_filter_bridge.py` and `island_filter_board_capture.py` layer the
filter runtime over reviewed island-board controls. Use
`island_filter_board_review.py` for exact waveform/firmware comparison, complete
island-port/filter association and restored initialization, drive, propagation
and strength faults. The [retained filter board controls](reports/island-filter-board/assessment.json)
pass these checks. Active force masks and links are exercised by the separate
force/release fixture; normal board stimulus does not establish that coverage.

Before extending to threads, follow the [initialization contract](reports/thread-source-contract/assessment.json):
track meaningful writes before reading unspecified flags or word registers, and
include suspended/event-waiting threads rather than only queued thread events.

`build_thread_runtime.py` adds initialized flag/register tracking and live-thread
observation. `thread_probe.py` uses the same runtime arguments; replay the
[retained controls](reports/thread-payload/assessment.json) with `thread_probe.py
--check verification/robotron-keyboard/analog/reports/thread-payload`. Controls
cover event waiting, fork/join, automatic functions and vector/real/string stacks.
The observer emits markers for untouched registers; it does not initialize them.
Board integration, queued/wait-event binding, reachable detached/deferred-deletion
paths and code/context/object referents remain open.

`build_thread_queue_runtime.py` adds typed scheduler-to-thread bindings and a
compact flag encoding. Replay [compact controls](reports/thread-compact/assessment.json)
with `thread_compact_probe.py --check verification/robotron-keyboard/analog/reports/thread-compact`.
Absent flag indices remain uninitialized; dense native snapshots at the same
paused points must match exactly.

`build_thread_bridge.py`, `thread_board_capture.py` and `thread_board_review.py`
combine live-thread observations with the preceding board layers. The capture
uses the reviewed filter-board controls as `--source` and `--assessment`, plus
`--bridge`, `--icarus` and a fresh `--out`. Review with `--root`, the capture
script as `--producer`, and a fresh assessment `--out`. The [retained board controls](reports/thread-board/assessment.json) preserve exact waveforms and firmware under the bounded fixture. A capture alone does not
establish qualification. Wait-event and deeper object referents, additional
lifecycle paths and broader operating windows remain separate requirements.

The [wait-event source contract](reports/wait-event-source-contract/assessment.json)
binds the next observer to the pinned event implementation and compiled board.
`thread.event` belongs to event-controlled assignments; ordinary wait lists live
on event functors. Include idle edge-history caches and per-context wait heads,
and keep observer reads separate from helpers that allocate missing caches.

`build_wait_runtime.py` adds typed wait-event heads and initialized edge/anyedge
history. Use `wait_probe.py` with the standard runtime arguments; replay the
[retained controls](reports/wait-event/assessment.json) with `wait_probe.py --check
verification/robotron-keyboard/analog/reports/wait-event`. Static and automatic
contexts are observed alongside live threads; nonempty event-controlled
assignment lists fail closed, as exercised by the [native refusal control](reports/wait-unsupported/assessment.json). Replay it with `wait_unsupported_probe.py --check verification/robotron-keyboard/analog/reports/wait-unsupported`. Board integration, context reuse, deep referents
and general rollback require separate evidence.

`build_wait_bridge.py`, `wait_board_capture.py` and `wait_board_review.py` add
wait-event ownership and history to the combined board controls. Supply reviewed
thread-board controls as `--source` and `--assessment`, the built `--bridge` and
`--icarus`, and a fresh capture `--out`. Review with `--root`, the capture script
as `--producer`, and a fresh assessment `--out`. The reviewer checks the event
inventory against compiled declarations and preserves all preceding state and
waveform checks; capture completion alone does not qualify the board.

`build_thread_lifecycle_runtime.py` adds targeted detached, wait-fork and
pending-deletion flag faults. Replay the [native lifecycle controls](reports/thread-lifecycle/assessment.json)
with `thread_lifecycle_probe.py --check verification/robotron-keyboard/analog/reports/thread-lifecycle`.
The fixture covers cancellation, deferred deletion and fresh identities after
storage reuse. This does not establish freed-storage equivalence; board
reachability and integration remain separate checks.

Scope board lifecycle controls using the [compiled reachability inventory](reports/thread-board-reachability/assessment.json).
Regenerate it with `thread_board_reachability.py --vvp <compiled-board> --archive
<pinned-icarus-archive> --out <fresh-assessment>`. Labelled opcodes and VPI calls
are included; absent detach opcodes do not exclude callback-driven deferred
deletion. Recheck this inventory when the compiled board changes.

`fast_audit_log.py` preserves the original scan checks while prefiltering diagnostic
candidates under pinned source identities. Non-ASCII text and changed diagnostic
sources use the original parser. [Full retained-log equivalence and host timing](reports/audit-scan/assessment.json)
are recorded separately from numerical qualification. Reproduce with
`audit_scan_benchmark.py --root <retained-controls> --mode observe --out <fresh-assessment>`;
the benchmark verifies the retained manifest and compares the full scan with its
original receipt. Keep native captures and large replays out of CI.

`build_code_binding_runtime.py` adds PC lookup against registered allocated code
slots before reading the opcode. Replay [native binding controls](reports/code-binding/assessment.json)
with `code_binding_probe.py --check verification/robotron-keyboard/analog/reports/code-binding`.
Null, foreign and misaligned pointers have no code identity; unused capacity is
not treated as an instruction. Board integration, full instruction operands and
their referenced objects remain separate from this binding check.

`build_code_binding_bridge.py`, `code_binding_board_capture.py` and
`code_binding_board_review.py` combine PC bindings with all preceding board
checks. Use reviewed wait-event board controls as `--source` and `--assessment`,
then supply `--bridge`, `--icarus` and a fresh capture `--out`. Review with
`--root`, the capture script as `--producer`, and a fresh assessment `--out`.
Allocated-code identity is checked for every observed thread; this does not
replace validation of instruction operands or their mutable referents.

The [board thread contract](reports/board-thread-contract/assessment.json) combines
an explicit compiled opcode/VPI profile with empty context, object-stack and
event-control checks on every reviewed thread. PC-board capture/review enforce
this contract and reject new instruction families or unexpected referents.
Reproduce the retained audit with `board_thread_contract.py --root <retained-thread-board>
--out <fresh-assessment>`. This scopes out absent thread referents; it does not
cover mutable scope membership, net/array contents or other compiled profiles.

The [scope source contract](reports/scope-source-contract/assessment.json) defines
independent scope-membership observation: reaped threads may remain live after
leaving their scope set. Regenerate
with `scope_source_contract.py --archive PINNED_ARCHIVE --vvp COMPILED_BOARD --out REPORT`.

The [native scope controls](reports/scope-membership/assessment.json) cover static
hierarchy and membership through deferred deletion and disabled queued threads,
with restored faults and explicit automatic-scope refusal. Scope-owned net/array
contents remain separate obligations. Build with `build_scope_runtime.py`;
run `scope_probe.py --candidate RUNTIME --baseline ORIGINAL_LIB --modules MODULES --out NEW_DIR`
or replay with `scope_probe.py --check reports/scope-membership` from this directory.

The [combined scope-board controls](reports/scope-board/assessment.json) preserve
exact normal waveforms and firmware while detecting restored membership removals
at startup and after firmware execution. They retain complete hierarchy and empty
scopes alongside preceding observer layers. This bounded service fixture does not
qualify full startup, repeat, recovery or general rollback. Reproduce by building
`build_scope_bridge.py`, then running
`scope_board_capture.py --source REVIEWED_PC_BOARD --assessment PC_ASSESSMENT --bridge BRIDGE --icarus RUNTIME --out NEW_DIR`
and `scope_board_review.py --root NEW_DIR --producer scope_board_capture.py --out REPORT`.
The reviewer retains preceding state checks and requires exact waveform/firmware
agreement plus restored membership faults at startup and after 5 us. For retained
replay use `--root reports/scope-board --producer reports/scope-board/producer.py`
and a fresh `--out` path.

The [instruction operand schema](reports/code-operand-contract/assessment.json)
derives initialized fields from the pinned compiler, including VPI-call handles
and allocator-generated instructions. It does not establish operand stability or
referenced-object coverage. Regenerate with
`code_operand_contract.py --archive PINNED_ARCHIVE --vvp COMPILED_BOARD --out REPORT`.

The [combined wait-event board controls](reports/wait-board/assessment.json)
preserve exact normal waveforms and firmware while observing event heads and
initialized histories, with restored head/mask/history/cache faults. Replay with
`wait_board_review.py --root reports/wait-board --producer reports/wait-board/producer.py --out NEW_REPORT`.
This bounded service evidence does not qualify electrical startup or supply recovery.

The [native code-operand controls](reports/code-operands/assessment.json) compare
full allocated instruction images with exact fixed-reference differences,
including restored immediate/target/handle faults and unknown-family refusal.
Each observation scans all allocated slots; unchanged rows are omitted only from
the encoded output. Referenced objects and board cost/acceptance remain open.
Build with `build_code_operand_runtime.py`; run `code_operand_probe.py` with the
same runtime arguments as the scope probe, or replay with
`code_operand_probe.py --check reports/code-operands`. Retained stdout is compressed.

The [board operand budget](reports/code-operand-budget/assessment.json) checks the
actual compiled instruction families and full/delta image equivalence before HDL
execution, then measures scan cost. Its campaign projection assumes unchanged
code and excludes later scope/PC overhead and review time; it is not a timing guarantee.
Run `code_operand_budget.py --source REVIEWED_BOARD --candidate RUNTIME --out NEW_DIR`
or replay with `code_operand_budget.py --check reports/code-operand-budget`.

For combined operand validation, build `build_code_operand_bridge.py`, capture with
`code_operand_board_capture.py --source REVIEWED_SCOPE_BOARD --assessment SCOPE_ASSESSMENT --bridge BRIDGE --icarus RUNTIME --out NEW_DIR`,
then review with `code_operand_board_review.py --root NEW_DIR --producer code_operand_board_capture.py --out REPORT`.
The capture uses the measured producer budget and bounded logs. A single complete
reference precedes the first boundary; every snapshot carries exact deltas.
The reviewer checks allocated-slot/schema coverage, rejects normal code changes,
and preserves all preceding board checks. Referenced object contents remain separate.

The [array source contract](reports/array-source-contract/assessment.json) identifies
compiled memories and read ports, and distinguishes word storage from cached
addresses, port links, callbacks and lazily allocated VPI word handles. Observation
must not allocate those handles or propagate a fault through the normal setter.
Regenerate the source contract with
`array_source_contract.py --archive PINNED_ARCHIVE --vvp COMPILED_BOARD --out REPORT`.

The [native array controls](reports/array-state/assessment.json) cover static
four-state words, cached read addresses, port links and existing word-handle
ownership, with restored faults and unchanged continuation. Automatic contexts,
two-state arrays and registered array callbacks are refused. Scope type determines
automatic allocation; the compiled cell flag does not. Board integration/budgets and destination net/fanout contents remain open.
Build with `build_array_runtime.py`; run
`array_probe.py --candidate RUNTIME --baseline ORIGINAL_LIB --modules MODULES --out NEW_DIR`
or replay with `array_probe.py --check reports/array-state`.

The [board array budget](reports/array-budget/assessment.json) measures complete
pre-execution memory/read-port scans. Dense output exceeds the current campaign
log cap even before later word-handle allocation. Integrate the [validated compact snapshots](reports/array-compact/assessment.json)
with full-image equivalence checks before a combined campaign; keep scanning
every word and port. This probe does not measure loaded firmware,
compression or operational review cost. Run
`array_budget.py --source REVIEWED_BOARD --candidate RUNTIME --out NEW_DIR`
or replay with `array_budget.py --check reports/array-budget`.

The compact array format packs logical four-state values in pairs and run-length
encodes existing word-handle pointers. It still reads every word and cache entry;
normal and corrupted images reconstruct the dense representation exactly, including
odd-width padding and cache-link faults. The [compact board budget](reports/array-compact-budget/assessment.json)
measures the reduction before HDL execution; combined operational validation remains
required. Build with `build_array_compact_runtime.py`, then use
`array_compact_probe.py` and `array_compact_budget.py` with the corresponding dense
probe arguments. Their `--check` modes replay the retained `array-compact` and
`array-compact-budget` reports without native builds.

For combined array validation, build `build_array_bridge.py`, capture with
`array_board_capture.py --source REVIEWED_OPERAND_BOARD --assessment OPERAND_ASSESSMENT --bridge BRIDGE --icarus RUNTIME --out NEW_DIR`,
then review with `array_board_review.py --root NEW_DIR --producer array_board_capture.py --out REPORT`.
The reviewer binds arrays to the observed scopes, checks compiled array/read-port
coverage and stable identities, and requires loaded words, materialized handles
and changing read addresses. Word/address/cache faults run after initialization;
port-link faults run at paused startup. Every fault must restore exactly without
changing earlier observer layers. Capture limits remain explicit; native compact
controls and pre-execution budgets alone do not qualify this combined campaign.

The [storage-family refusal controls](reports/array-families/assessment.json) verify
that both array formats reject shared-storage aliases, net arrays, real arrays
and string arrays before emitting any inventory. The alias fixture inserts the
pinned compiler's alias declaration and proves shared writes/readback; it does
not claim the HDL frontend emits that declaration for every alias construct.
Original and observer-disabled continuation agree. These controls establish
refusal, not support for those families. Reproduce with `array_family_probe.py`
using the native array-probe arguments, or replay with
`array_family_probe.py --check reports/array-families`.

The [net allocation/fanout contract](reports/net-source-contract/assessment.json)
separates compiled labels, handed-out native nodes and unused pool capacity.
Net handles may share drivers, intermediate nodes may lack labels, and force-link
helper ports have distinct back-reference semantics. Register allocations rather
than constructor calls, preserve all initialized links/bindings, and keep payload
coverage separate. Regenerate the source contract with
`net_source_contract.py --archive PINNED_ARCHIVE --vvp COMPILED_BOARD --out REPORT`.

The [native graph controls](reports/net-state/assessment.json) enumerate handed-out
nodes independently of fanout traversal, preserve tagged links and functor/filter
bindings, and restore head/link/tag/binding/foreign-target faults before execution.
Force-helper creation, reuse and release preserve exact continuation. These are
graph and binding checks; payload contents, board integration and capture/review
budgets remain open. Build with `build_net_runtime.py`, run
`net_probe.py --candidate RUNTIME --baseline ORIGINAL_LIB --modules MODULES --out NEW_DIR`,
or replay with `net_probe.py --check reports/net-state`.

The [compiled-board graph budget](reports/net-budget/assessment.json) binds all
observed array destinations and typed code net operands to handed-out allocations.
Dense graph output exceeds the campaign log cap; the [native graph deltas](reports/net-delta/assessment.json)
reconstruct complete images while scanning every node. The pre-execution measurement
does not establish operational event/bridge bindings, future graph changes or
combined capture/review cost. Run
`net_budget.py --source REVIEWED_BOARD --candidate RUNTIME --out NEW_DIR`, or replay
with `net_budget.py --check reports/net-budget`.

Graph deltas use one immutable reference and emit full rows for changed or newly
allocated nodes. Restoration compares against that same reference; no incremental
baseline can conceal a lost fault. Native controls reconstruct normal, corrupted
and restored images through force-helper allocation/reuse/release. The
[board delta budget](reports/net-delta-budget/assessment.json) assumes an unchanged
graph for its output projection; operational integration still needs explicit caps
and event/bridge target checks. Build with `build_net_delta_runtime.py`, then use
`net_delta_probe.py` and `net_delta_budget.py` with the corresponding dense-probe
arguments. Their `--check` modes replay `net-delta` and `net-delta-budget`.

For combined graph validation, build `build_net_bridge.py`, capture with
`net_board_capture.py --source REVIEWED_ARRAY_BOARD --assessment ARRAY_ASSESSMENT --bridge BRIDGE --icarus RUNTIME --out NEW_DIR`,
then review with `net_board_review.py --root NEW_DIR --producer net_board_capture.py --out REPORT`.
The reviewer reconstructs complete graphs and binds code operands, array ports and
queued assignment/primitive destinations to allocated nodes. A cached decoded image
is reused only when the complete native delta is identical; native scans still cover
every node. Head/foreign-target faults run at startup and link/tag/binding faults
after initialization, restoring before execution. The capture timeout adds a
rounded allowance for twice the measured graph scan cost; actual cost and bridge
handle/payload coverage remain separate obligations.

The [native class controls](reports/net-types/assessment.json) bind RTTI class names
to allocated node/functor/filter identities through graph faults and force-helper
lifecycles. The [compiled-board inventory](reports/net-types-board/assessment.json)
identifies the payload families that need coverage; existing island-filter controls
do not cover every ordinary wire filter. Class identity establishes reachability,
not initialized field contents or callback equivalence. Build with
`build_net_types_runtime.py`, then run `net_types_probe.py` with the native-probe
arguments or `net_types_board.py` with the board-budget arguments. Replay with
`--check reports/net-types` or `--check reports/net-types-board`, respectively.

The [all-node wire controls](reports/wire-state/assessment.json) enumerate allocated
four-state and strength-aware filters beyond island ports. They observe initialized
drive/force vectors, force masks/flags/links and callback/array-word list heads;
actual payload faults restore before continuation. Wide vectors and linked
force/release are exercised. List contents, other filter families and signal-functor
payloads are separate obligations; unsupported filter families are rejected.
Build with `build_wire_runtime.py`, run `wire_probe.py` with the native-probe
arguments, or replay with `wire_probe.py --check reports/wire-state`.

The [raw wire controls](reports/wire-raw-state/assessment.json) preserve native
scalar bytes: legacy logical-value/strength triplets merge distinct states.
The [raw board budget](reports/wire-raw-board-budget/assessment.json) binds these
cache bytes to allocated filters, graph identities and legacy views. It measures
full raw scans before execution; compact encoding and operational integration
remain open. Build with `build_wire_raw_runtime.py`, then run `wire_raw_board.py`
with the reviewed `reports/code-binding-board` source and raw runtime. Replay with
`wire_raw_board.py --check reports/wire-raw-board-budget`.
The [raw filter admission controls](reports/wire-raw-families/assessment.json)
reject real filters and vec4/vec8 subclasses before partial output, including
allocations after a valid observation. Continuation after refusal matches the
original runtime. Reproduce with `wire_raw_family_probe.py` using the native-probe
arguments, or replay with `--check reports/wire-raw-families`.
The [raw byte differences](reports/wire-raw-delta/assessment.json) reconstruct
native cache snapshots and collision faults from an immutable reference while
scanning every native field. [Board preflight](reports/wire-raw-delta-budget/assessment.json)
measures full-scan encoding cost; changing-state output can exceed dense logs.
Use `build_wire_raw_delta_runtime.py`, `wire_raw_delta_probe.py` and
`wire_raw_delta_board.py` with the same native-probe and board-budget arguments.
Both reviewers support `--check` on their respective retained report directories.
[Compact admission controls](reports/wire-raw-delta-families/assessment.json)
reject unsupported filters after a valid reference without partial output, while
preserving native continuation after refusal. Reproduce with
`wire_raw_delta_family.py` using native-probe arguments, or replay with
`--check reports/wire-raw-delta-families`.
[Native raw-filter growth controls](reports/wire-raw-growth/assessment.json)
allocate supported filters after the reference and reconstruct constructor,
drive/force and restored collision states. New rows remain complete in every
difference frame and can exceed dense storage. Reproduce with `wire_raw_growth.py`
using native-probe arguments, or replay with `--check reports/wire-raw-growth`.

The [board wire budget](reports/wire-board-budget/assessment.json) binds every
allocated filter to its graph identity and native class before execution. It
measures full wire serialization and verifies repeated observations leave the
observed state unchanged. Initial-state output projections exclude later vector,
force and callback changes; callback/array-word list contents and combined
operational capture cost remain open. Reproduce with `wire_board.py` using the
reviewed wait-board source and wire runtime, or replay with
`wire_board.py --check reports/wire-board-budget`.

The [wire delta controls](reports/wire-delta/assessment.json) reconstruct complete
wire images from an immutable per-filter reference plus prefix/suffix splices.
Every call scans all native fields; omitted records mean exact equality to that
reference. New filter records are complete; disappearance is refused. Dense
images remain the independent oracle for force/release and restored faults.
Reference reset and observations before reference initialization are refused.
The [board delta budget](reports/wire-delta-budget/assessment.json) measures this
encoding on the compiled board before execution. Its small unchanged-state
output is not an operational storage bound; force changes and active vectors
still require combined capture/review measurements. Callback-list contents and
other functor payloads remain separate. Build with `build_wire_delta_runtime.py`,
run `wire_delta_probe.py` and `wire_delta_board.py`, and replay either producer
with `--check` and its retained report directory.

`build_wire_bridge.py`, `wire_board_capture.py` and `wire_board_review.py`
integrate lossless wire observations after reviewed graph controls. Every boundary
binds wire identities to allocated graph nodes and checks shared island-filter
payloads. Vec4/vec8 initialization faults run at paused startup; driven-value and
propagation faults run after firmware starts. All preceding layers, exact normal
waveforms and firmware records remain required. The capture retains the bounded
log limits and adds a measured wire-scan allowance to its timeout. Native force,
mask, link and strength controls remain necessary for paths absent from this
board fixture. Integration is unqualified until capture and retained replay pass.

The [signal ownership contract](reports/signal-source-contract/assessment.json)
pins static variable storage and procedural assignment semantics. Unfiltered
signal bits, partial assignment masks and source links are separate from wire
filter output and force helpers. The report identifies initialized fields and
required native fault/continuation controls; it does not establish payload
coverage. Reproduce with `signal_source_contract.py --archive PINNED_ARCHIVE
--vvp reports/net-types-board/board.vvp --out FRESH_REPORT`.

The [native signal controls](reports/signal-state/assessment.json) cover static
four-state unfiltered values, partial assignment masks, source relinking and
initialized flags. End-of-compilation observations check constructor state before
initial propagation; start-of-simulation callbacks are too late for that claim.
Assign/deassign, partial writes, wide X/Z values and force/release preserve exact
continuation while actual field faults restore without propagation. Visible forced
output is checked separately from underlying storage. Operational board integration
and combined capture/review budgets remain open. Build with
`build_signal_runtime.py`, run `signal_probe.py` with candidate/baseline/module
paths, or replay `signal_probe.py --check reports/signal-state`.

The [signal-family controls](reports/signal-families/assessment.json) exercise
active automatic storage, real/string variables and object storage through a
dynamic integer array. Native class inventories verify the intended families;
observation refuses without partial output, while disabled runs preserve
continuation. This does not qualify support for those families. Reproduce with
`signal_family_probe.py`, or replay its report using `--check`.

The [signal board budget](reports/signal-board-budget/assessment.json) binds all
static signal functors to allocated graph nodes and native classes before time
advances, with a compiled width cross-check. It measures dense serialization,
not operational state changes or combined cost. Budget or losslessly reduce this
output before integration; later masks/links can grow. Reproduce using
`signal_board.py --source REVIEWED_WAIT_BOARD --candidate SIGNAL_RUNTIME --out NEW_DIR`
or replay `signal_board.py --check reports/signal-board-budget`.

The [signal delta controls](reports/signal-delta/assessment.json) retain full native
scans and encode differences from an immutable per-signal reference. Dense images
remain the independent oracle for initialization, assignment relinking, partial
masks, force/release and restored faults. Reference resets and observation before
reference initialization are refused. The [board delta budget](reports/signal-delta-budget/assessment.json)
measures initial-state scans and exact reconstruction; unchanged output savings do
not bound active values, masks or links. Build with `build_signal_delta_runtime.py`,
then run `signal_delta_probe.py` and `signal_delta_board.py`; replay either with
`--check` and its retained report directory. Operational integration remains open.

`build_signal_bridge.py`, `signal_board_capture.py` and `signal_board_review.py`
extend reviewed wire controls with complete signal differences and an initial
native class inventory. Signals must retain their class/allocation bindings and
compiled widths; non-null procedural-assignment sources must reach destination
port 1 through the allocated graph. Initialization faults restore at startup;
stored-value and active-flag faults restore after firmware starts. Native mask,
link and force/release controls remain required for paths absent from this board.
All preceding state, waveform and firmware checks remain enabled. The capture
keeps bounded logs and adds a measured signal-scan allowance; operational acceptance
requires the campaign and retained replay, not the integration tests alone.

The [logic ownership contract](reports/logic-source-contract/assessment.json)
distinguishes cached mux/Boolean/unary state from BUFZ/BUFT forwarding classes.
Those exact forwarding classes have no additional per-instance payload; their
native-class/graph bindings and downstream state still matter. Muxes retain the
unselected input, selection and run history; Boolean gates retain inputs and
inversion. Pending destinations must be tied to scheduler wrappers using the
properly adjusted event-base pointer. The report pins source initialization and
required controls, not native payload coverage. Reproduce with
`logic_source_contract.py --archive PINNED_ARCHIVE --board reports/net-types-board --out NEW_REPORT`.

The [native mux controls](reports/mux-state/assessment.json) enumerate allocated
MUXZ caches and their properly cast scheduler-event identities, including idle,
queued and executing states. Unselected-input updates, later selection, X/Z
blending, wide vectors and partial source writes preserve exact output while
cache/select/run/pending-destination faults restore before execution. The
[direct partial-vector controls](reports/mux-partial/assessment.json) call native
`recv_vec4_pv` on data and select ports in both original and observed runtimes;
an independent four-state oracle checks wide-vector continuation, while cache
checks include silent unselected and unchanged writes. Other logic families,
board admission and capture budgets remain open. Build with `build_mux_runtime.py`,
then run `mux_probe.py` and `mux_partial_probe.py` with native
candidate/baseline/module paths. Replay with `--check reports/mux-state` and
`--check reports/mux-partial`, respectively.

The [mux board budget](reports/mux-board-budget/assessment.json) binds every native
MUXZ to its allocated graph node and checks compiled width totals. Initial-state
scans include scheduler-wrapper lookup; their size and timing projections exclude
later queue/cache growth and other observers. Use the lossless differences below for
combined integration, preserving full native scans and wrapper identities.
Reproduce with `mux_board.py --source REVIEWED_BOARD --candidate MUX_RUNTIME --out NEW_REPORT`;
replay with `mux_board.py --check reports/mux-board-budget`.

The [mux difference controls](reports/mux-delta/assessment.json) and
[direct partial controls](reports/mux-partial-delta/assessment.json) reconstruct
complete native snapshots from immutable per-mux references and byte splices.
Every frame includes complete queued/executing wrapper records; removed wrappers
are not inherited. Native scans still visit every cache and queue. Missing or
reset references are refused; new mux records require full data, and disappearing
reference muxes are refused. The [native allocation controls](reports/mux-growth/assessment.json)
create muxes after reference initialization, preserving their constructor,
queued/executing and drained states, partial writes and restored pending-target
faults. Live mux and wrapper identities must remain bound. Operational board
allocation changes and deletion/freed storage remain separate. Run
`mux_growth_probe.py` with the same native paths, or replay with
`mux_growth_probe.py --check reports/mux-growth`.
The [initial-state budget](reports/mux-delta-budget/assessment.json) measures
full-scan encoding and exact graph/class-bound reconstruction. Changed fixture
states can encode larger than dense snapshots, so unchanged-state savings are
not an operational bound. Measure actual combined cost before raising log caps.
Build with `build_mux_delta_runtime.py`, run `mux_delta_probe.py` both with and
without `--partial`, and run `mux_delta_board.py` with a reviewed board source.
Replay each report with its producer's `--check` option.

`build_mux_bridge.py`, `mux_board_capture.py` and `mux_board_review.py` add complete
mux differences and wrapper records to the reviewed signal-board controls.
Muxes retain their initial native class, allocated node, functor, event identity
and widths; unexpected allocation changes require profile re-admission.
Input-A faults restore at paused startup, with input-B, selection and run-history
faults after firmware starts. Pending-target faults remain covered by the native
fixtures. All preceding state checks and exact waveform/firmware comparisons stay
enabled. Log caps remain unchanged; the scan-time allowance comes from the mux
budget. Integration remains unqualified until capture and retained replay pass.

The [native gate controls](reports/gate-state/assessment.json) cover exact
AND/NAND, OR/NOR, XOR/XNOR and BUF/NOT cache classes. They enumerate every
allocated input vector, inversion flag and pending destination, binding queued
and executing wrappers through the adjusted event-base pointer. Full and direct
partial writes, X/Z values and unchanged writes preserve original-runtime output;
actual input/inversion/pending faults restore before execution. Other subclasses
of these cache bases refuse inventory. The [native family controls](reports/gate-families/assessment.json)
check equivalence/implication and Boolean/unary subclasses with behavior-changing
private state alongside an admitted AND, requiring refusal before any inventory
output. Disabled controls preserve original-runtime behavior. Run
`gate_family_probe.py` with the native paths, or replay with
`gate_family_probe.py --check reports/gate-families`. Input-path controls below
cover conversion and width changes; allocation lifecycle and board integration
remain open.
Build with `build_gate_runtime.py`, then run `native_gate_probe.py` with candidate,
baseline and module paths. Replay with `native_gate_probe.py --check reports/gate-state`.

The [native gate board budget](reports/gate-board-budget/assessment.json) binds
all admitted gate caches to allocated nodes and native classes, with independent
compiled family/inversion/width totals. Initial-state measurements include full
cache and scheduler-wrapper scans; they exclude later queue growth and combined
observer costs. Keep the measured dense cost explicit when selecting compact
encoding and capture limits. Reproduce with
`native_gate_board.py --source REVIEWED_BOARD --candidate GATE_RUNTIME --out NEW_REPORT`,
or replay with `native_gate_board.py --check reports/gate-board-budget`.

The [gate input-path controls](reports/gate-inputs/assessment.json) check finite
real rounding/LSB extraction, NaN/infinity conversion, shrinking/re-expanding
caches and neutral/controlling unequal widths against original-runtime behavior.
Both runtimes exhibit an unequal-width AND/OR discontinuity: the first absent
bit participates as X, while later absent bits force X even with a controlling
input. Matching this behavior establishes fidelity, not general gate semantics.
The board admission check requires equal cached widths; resolve this behavior
before admitting unequal-width profiles. Overflowing real values remain outside
these controls. Reproduce with `gate_input_probe.py` and the native runtime paths,
or replay with `gate_input_probe.py --check reports/gate-inputs`.

The [gate differences](reports/gate-delta/assessment.json) and
[input-path differences](reports/gate-input-delta/assessment.json) reconstruct
dense native caches, inversion and pending destinations from an immutable
reference. Every frame retains complete scheduler-wrapper records. Full native
field scans remain mandatory; absent/repeated references and disappearing
reference gates are refused. [Late-family controls](reports/gate-delta-families/assessment.json)
reject unsupported allocations after a valid reference without partial output.
The [board budget](reports/gate-delta-budget/assessment.json) measures unchanged
full-scan encoding and graph/class-bound reconstruction. Changed fixture records
can exceed dense sizes; operational output and runtime must still be measured.
Build with `build_gate_delta_runtime.py`; run `gate_delta_probe.py` with and
without `--inputs`, `gate_delta_family.py`, and `gate_delta_board.py`. Each report
replays with its producer's `--check` option. The [native allocation controls](reports/gate-growth/assessment.json)
create all admitted Boolean/inversion and unary variants after reference
initialization, checking complete new records, stable identities, constructor
caches, queued/executing/drained wrappers and restored faults. Reproduce with
`gate_growth_probe.py` using the native paths, or replay with
`gate_growth_probe.py --check reports/gate-growth`. Combined board integration,
deletion and freed-storage equivalence remain open.

`build_gate_bridge.py`, `gate_board_capture.py` and `gate_board_review.py` extend
reviewed mux controls with full-scan gate differences and complete wrapper
records. Gate class, inversion, cache widths and allocated node/functor/event
bindings must remain within the admitted profile. Queued NOT cache/destination
and wrapper records must agree with the existing primitive observer. Boolean
input-0 faults restore at paused startup; other input and inversion faults restore
after firmware starts. Unary/pending-target faults remain in native controls.
All preceding state and exact waveform/firmware comparisons remain required.
The capture keeps existing log caps and adds a measured scan-time allowance;
integration is unqualified until capture and independent retained replay pass.


The [joint I8282 constraints](reports/i8282-joint-constraints/assessment.json)
intersect the retained enabled-output, capacitance, propagation and release
experiments. The reviewer replays each source experiment before forming the
intersection. Each surviving resistance/capacitance pair has nonnegative internal
data, strobe and disconnect delay intervals limited by its worst retained supply,
polarity and leakage case; the report records the limiting case indices. These
intervals assume a constant pure transport delay followed by instantaneous drive
switching. They do not cover finite internal slew or untested capacitances.
The 250-ohm candidate with 12 or 30 pF remains rejected even at zero internal
delay. `check_delays` refuses those combinations, untested capacitances, missing
fields and out-of-budget delays. Passing that partial check does not admit a
device: Intel enable measurement, nonlinear behavior and operational integration
remain open. Reproduce or replay with
`i8282_joint_constraints.py --out reports/i8282-joint-constraints/assessment.json`
(add `--check` for replay). This uses retained SPICE measurements rather than
running a new simulation or changing the live board campaigns.


The [U880 output screen](reports/u880-output-candidates/assessment.json) applies
an independent data-valid constraint from the manufacturer's delay table (printed
pages 58–60). At 4.75 V with 100 pF, both endpoint-only CPU hypotheses require
about 340 ns even to rise from 0.8 V to 2 V, exceeding the 260-ns data-output
budget before internal delay. They cannot serve as complete output models under
this test condition. The screen uses 2 V as the declared high-valid level; it
does not reconstruct an instrument comparator or internal clock response.
Explicit 3-kohm and 4-kohm high-side alternatives satisfy the retained DC and RC
screens. With 10 pF added and a zero-volt initial output, their remaining delay
budgets are about 79.64 and 19.52 ns. The extra 10 pF is a sensitivity assumption:
the source capacitance limit is at 25 C, whereas the delay condition is at 70 C.
These alternatives remain unqualified for nonlinear I/V, release, supply law,
and board integration. ROM qualification remains separate. Run
`u880_output_probe.py --out NEW_REPORT`, or replay the retained decks and
measurements with
`u880_output_probe.py --out reports/u880-output-candidates --verify`.


The [finite-slew CPU controls](reports/u880-slew-candidates/assessment.json)
extend those alternatives with linear internal drive ramps of 0, 10, 30 and
60 ns, both output polarities, and zero/10-pF added capacitance. Every retained
SPICE crossing agrees with the independent first-order ramp solution. The
zero-ramp rising controls reproduce the earlier instantaneous-drive calculation.
Joint pure-delay intervals use the slower polarity; a null interval rejects the
combination even without internal transport delay. In particular, the
4-kohm/10-pF combination fails with a 60-ns ramp although its instantaneous
control passes. Falling edges pass this screen with the DC-derived low-side
resistance. Ramp times are assumptions, not measured device properties; these
controls do not qualify actual switching topology, enable/release or nonlinear
I/V. Run `u880_slew_probe.py --out NEW_REPORT`, or replay with
`u880_slew_probe.py --out reports/u880-slew-candidates --verify`.


The [1986 Intel source review](reports/intel-1986-enable-review/assessment.json)
records a later handbook's load circuits and enable waveform. It still leaves
the enable measurement convention unresolved. Its commercial/EXPRESS profiles,
plastic-package load exception and switching load remain separate from the
industrial I8282 contract. The source hash and exact pages allow independent
inspection; no existing model parameter or retained experiment is changed.


The [full coarse drain comparison](reports/postreset-drain-coarse-effect/assessment.json)
binds the completed 25-ns exact-tick-only and drain-enabled captures to the same
inputs and candidate build. All 1,427,676 electrical samples across 1.16 ms are
exactly equal. Draining does not change this coarse electrical trajectory;
finer-level convergence, internal scheduler state and complete campaign review
remain separate. Reproduce with `postreset_drain_coarse_review.py` using the
local capture paths in the report's `retention.json`. Full waveforms remain local.


The [full-window retention benchmark](reports/postreset-retained-stream/review.json)
replays all three existing 1.16-ms exact-tick refinements through capped raw/log
retention, then repeats both complete waveform comparisons from the new archives.
Both comparisons exactly preserve the original results, including the failed
numerical gate. Transport took 522.47 seconds and archive replay 444.08 seconds;
1,821 process-tree RSS samples reached 833,936 KiB (about 814 MiB), including
both stages but excluding preflight hashing and between-sample peaks.
The 1,134,797,587 raw bytes compress to 628,546,404 bytes; 2,034,388,918 authentic
log bytes compress to 119,960,816 bytes. All remain within the declared aggregate
caps. These are observed costs for existing captures, not simulator runtime,
an exact memory bound, full-repeat capacity or numerical admission.
The independent review decompresses every archive and verifies its logical
identity against the original capture receipt; its default mode does not rerun
sample comparisons already performed by the benchmark. Full archives remain at
the paths in `retention.json`; retained hashes alone cannot reproduce them.
Reproduce with `postreset_retention_benchmark.py --out NEW_DIRECTORY`, then
`postreset_retention_review.py --root NEW_DIRECTORY --out NEW_REVIEW.json`.
Add `--full` to repeat every sample comparison again in the independent review.


The [finite-slew I8282 controls](reports/i8282-slew-candidates/assessment.json)
constrain the same 125/250-ohm alternatives with 0/10/30/60-ns internal drive
ramps, both polarities, three supplies and 0/12/30-pF added capacitance. All
144 SPICE cases agree with the independent loaded RC solution. Zero-ramp
controls reproduce the prior edge and propagation calculations. Joint budgets
require both edge limits as well as propagation headroom: the 250-ohm/0-pF
alternative fails an edge limit with a 10-ns ramp, and the 125-ohm alternatives
fail at 30 ns despite positive propagation headroom. At 125 ohms, 12 pF and a
10-ns ramp, the joint data/strobe pure-delay maxima are 22.2592/42.2592 ns.
Resistance switches instantly to its final-state value while the drive source
ramps; this can initially move a falling output in the wrong direction. This
explicit hypothesis does not establish actual internal drive shape, finite
disconnect dynamics or enable behavior. Preserve the separate release constraints
and unresolved Intel enable convention before any device admission. Run
`i8282_slew_probe.py --out NEW_DIRECTORY`, or verify retained results with
`i8282_slew_probe.py --out reports/i8282-slew-candidates --verify`.


`cached_net_board_review.py` is a separate candidate for reducing repeated pure
snapshot parsing. It keeps one exact record-sequence/module-identity key and
returns a deep copy of the parsed tree. State lifetime checks, input scans,
raw comparisons and firmware acceptance still run in the original reviewer.
The candidate refuses unless its complete assessment equals the original
review's retained assessment. Its complete operational comparison is pending;
small timing probes and startup controls do not qualify the whole campaign.
Run it with `--root CAPTURES --producer net_board_capture.py --reference
ORIGINAL_ASSESSMENT.json --out NEW_RESULT.json`. Source hashes and cache counts
are recorded separately; pinned captures and the original reviewer are unchanged.


The [combined graph controls](reports/net-board/assessment.json) pass the complete
20-us service fixture across 55,156 normal boundaries and up to 1,820 allocated
nodes. They bind 258 code-net targets plus array ports and queued assignment/
primitive destinations to allocated nodes while preserving all earlier observer
layers. Head/foreign-target faults restore at startup; link/tag/functor/filter
faults restore at the 5-us boundary before controlled termination. Disabled
baseline and enabled-observer controls preserve exact waveform samples and
firmware records. The observed capture took 1,272.63 seconds and emitted
3,831,556,996 logical log bytes (4,663,296 compressed), within its 4-GiB logical
and 256-MiB compressed caps. This measured cost does not bound later payload
integration or a longer window. All capture evidence is retained; the manifest
check passes. A second full review of the retained copy is running before the
queued wire campaign. Wire/functor payload integration, complete private state,
general rollback, startup and supply recovery remain open. Regenerate the
review using `reports/net-board/retention.json`.


The [native scope referent controls](reports/scope-referents/assessment.json)
demonstrate that the hierarchy/thread-membership image does not cover scope
metadata or internal object membership. Direct native mutations of `time_units`,
`lineno` and the `intern` vector change scaled VPI time, source-line queries and
named signal lookup while every byte of that image remains unchanged. All
mutations restore before HDL continuation; original-runtime, disabled and
observed executions agree exactly. This is an injected-state coverage
counterexample, not evidence that ordinary board execution performs these writes.
Any applicability argument must distinguish initialization-only fields from
reachable runtime changes. The control does not cover all scope intern object
payloads, function metadata, automatic contexts or general rollback. Run
`scope_referents.py` with the candidate, baseline and module paths recorded in
`run.json`, using a new output directory. Existing campaigns remain pinned.


The [scope metadata source contract](reports/scope-metadata-contract/assessment.json)
retains declaration/timescale initialization, VPI consumers, function subtype
fields, internal attachment call sites and the existing scope walker. The
walker casts intern pointers without an independent allocation registry, so
future metadata coverage must admit registered pointers before dereferencing
corrupted entries. Selected compile-time writes do not prove an exhaustive
runtime nonmutation invariant across admitted modules. Native ownership,
foreign-pointer refusal, subtype/lifecycle controls and operational integration
remain required. Regenerate with `scope_metadata_contract.py --archive
PINNED_ARCHIVE --out NEW_REPORT.json`; `--check` verifies the retained report.


The [native scope admission controls](reports/scope-admission/assessment.json)
qualify a separate runtime revision that records completed scope declarations
and native internal-object attachment handoffs. The scope walker rejects foreign
root/intern pointers before casting and requires every initialized scope in the
reachable hierarchy. Foreign parents and omitted children refuse before output.
Two rounds exercise all four faults with negative status and zero bytes, followed
by exact restoration and original-runtime HDL continuation. Retained membership
controls preserve empty scopes, zombie/deferred-deletion paths and automatic
refusal; signal-scope controls preserve metadata/link comparisons and their
existing family refusals. The registry assumes the static native ownership
lifetime: deletion/address reuse, new runtime scope families, metadata payloads
and operational board cost remain unqualified. Existing campaigns keep their
pinned runtime. Build with `build_scope_admission_runtime.py`; reproduce native
controls with `scope_admission.py` and paths recorded in `run.json`.

The [native scope metadata controls](reports/scope-metadata/assessment.json)
add a separate observer for source locations, cell/timescale fields, bounded name
and definition bytes, function subtype/width/initial value, lazy scoped-time
backreferences and ordered internal-object identities/types. Native declaration
and attachment handoffs register pointer ownership before observation; the whole
static graph is checked before output. Two rounds distinguish fourteen metadata
mutations, refuse eight invalid states with zero bytes, and restore the exact
image before continuing identically to the original runtime. Automatic scopes
also refuse without output. Existing admission, membership/lifecycle and signal
controls pass with this runtime. Function fields are observed but not faulted;
internal-object payloads, deletion/address reuse, exhaustive initialization-only
proof and operational board integration/cost remain open. Running campaigns retain
their earlier pinned runtime. Build with `build_scope_metadata_runtime.py` and
reproduce with `scope_metadata.py` using the paths in the retained receipts.

The [scope metadata record controls](reports/scope-metadata-records/assessment.json)
parse all 32 retained native images without dropping name bytes, function fields,
time backreferences or internal-object ordering. The versioned parser rejects
truncation, invalid counts/ranges, duplicate scope identities, unknown families,
foreign time/parent references and inconsistent object types. Semantic review
checks the actual faulted field and exact restoration; malformed-image tests also
reject unrelated field changes. This prepares the record layer for integration;
object IDs are not yet bound to other observers, and no board state/cost claim is
made. Regenerate with `scope_metadata_records.py reports/scope-metadata/enabled.stdout
--out NEW_REPORT.json`; run `python3 -m unittest test_scope_metadata_records`.

The [native metadata binding controls](reports/scope-metadata-bindings/assessment.json)
join metadata scope IDs to native addresses and the existing traversal IDs, and
join ordered internal-object IDs to native addresses/types. A combined snapshot
binds two explicitly admitted signal handles to their owning scopes. Removing one
signal from its scope leaves the reference, thread-membership and signal images
unchanged, but the cross-observer reviewer rejects the missing ownership. Two
rounds restore exactly and continue identically to the original runtime; foreign
intern pointers refuse reference output before dereferencing. The existing
metadata mutation/automatic-refusal controls and lossless semantic replay pass
with the new runtime. Four tests cover retained replay, cross-observer mismatch,
reference truncation/alias and changed continuation. This is a static native
fixture; other internal payload bindings, lifecycle qualification and operational
board integration/cost remain open. Build with
`build_scope_metadata_bindings_runtime.py`; reproduce with
`scope_metadata_bindings.py` using the retained receipt paths.

The [initialized board metadata budget](reports/scope-metadata-board-budget/assessment.json)
checks the real keyboard bridge before its first coroutine advance: 32 scopes,
1,932 registered internal objects and all 18 admitted bridge signal handles join
across the native inventories. Repeated complete images remain identical. The
1,884 remaining object identities comprise 437 nets, 191 registers, 5 integer
variables, 3 memories, 56 parameters, 317 ports and 875 port bits; their identities
and types do not establish payload coverage. Metadata/reference images occupy
40,322/61,663 bytes. Sixty-four scans per API average about 0.426/0.500 ms locally;
repeating both dense images over the prior 110,312 snapshot calls projects to
11,250,169,320 logical bytes and about 102.1 seconds of these scans alone. These
initial-state projections exclude growth, other observers and review, and do not
qualify transient board coverage. Five tests replay the retained assessment and
reject changed images, cross-observer address mismatches, truncation and nonfinite
cost. Build with `build_scope_metadata_board_budget.py`, then run
`scope_metadata_board_budget.py` against the reviewed `reports/array-board` source
and the metadata-bindings runtime, using the paths in the retained build receipts.

The [native compact metadata controls](reports/scope-metadata-compact/assessment.json)
retain a complete native scan on every call and compare the entire body with the
previous image. Only exact byte equality permits reuse; a changed body is emitted
in full, with explicit timestamp, sequence and byte count. The decoder reconstructs
all 74 dense metadata/reference image pairs byte-for-byte across the existing
mutations, restorations and tick changes. Sixteen invalid-state calls and the
initial automatic-scope control refuse without output or advancing the reference.
This fixture emits 38,585 compact versus 64,944 dense bytes; repeated changing
bodies may increase size. Five tests check native replay, missing/reordered/
truncated references, decoder state preservation on failure, illicit cached-body
payload and corrupt evidence. Board savings, native buffering overhead, scan cost
and operational integration still require measurement. Build with
`build_scope_metadata_compact_runtime.py`; replay with `scope_metadata_compact.py`
using the retained runtime paths. The running campaigns keep their pinned revisions.

The [initialized compact board budget](reports/scope-metadata-compact-board-budget/assessment.json)
retains and decodes all 64 metadata plus 64 reference records from the actual
initialized keyboard bridge. Every reconstructed image equals its dense source;
post-scan dense images remain unchanged. The records total 106,546 compact bytes
versus 6,527,040 dense bytes. Repeated complete scans average about 0.428/0.507 ms
for metadata/references locally, including serialization and file flush; this is
not a demonstrated runtime optimization. With unchanged bodies, 110,312 snapshot
calls project to at most 12,896,524 bytes with maximum-width future timestamps,
versus the dense 11.25-GB initial-state projection. Changed bodies still emit in
full. Retained cache content totals 101,956 bytes, excluding allocation capacity,
transient buffers and peak RSS. Five tests cover retained replay, lost records,
changed dense state, payload mismatch and invalid cost. Build with
`build_scope_metadata_compact_budget.py`, then use `scope_metadata_compact_budget.py`
with `reports/array-board` and the compact runtime. Changing-state cost, peak
memory and operational integration remain open.

The [combined metadata startup preflight](reports/scope-metadata-combined-preflight/assessment.json)
adds scope metadata and reference images to the complete typed-signal/prior-layer
snapshot. Native before/repeat/restoration comparisons remain dense. Only the log
writer applies exact previous-body reuse; the reviewer reconstructs records and
checks scope/signal ownership before delegating to every preceding state review.
This placement avoids making observer sequence numbers look like native state
changes. All ten existing callback/typed-signal startup faults pass, with 22
snapshots binding 32 scopes and 18 admitted signals. Full restoration is checked
for both the dense old layers and reconstructed metadata. Build with
`build_scope_metadata_bridge.py`, capture using `typed_signal_fault_capture.py
--startup-only`, and review with `scope_metadata_combined_review.py`. The retained
source is reviewed `reports/array-board`; this startup preflight is independent of
the ongoing ordered transient campaigns. Scope-specific board faults, normal
transient/firmware equivalence, peak memory and operational qualification remain
open. The native compact API remains a separate tested transport; the combined
bridge compacts serialized dense snapshots instead of calling that API inside
native equality comparisons.

The [scope-specific board startup faults](reports/scope-metadata-fault-preflight/assessment.json)
exercise native time units, source line, function type, function width and function
initial value, plus an invalid intern pointer. Direct metadata and complete dense
snapshots detect each change/refusal; the reviewer requires the exact selected
field change and no unrelated change, followed by full restoration before exit.
The ten earlier callback/typed-signal controls also pass with this runtime and
bridge, retained under `regression/`. The three function fields are now faulted on
the real compiled board at paused startup. This does not prove later execution,
firmware continuation, lifecycle or normal transient equivalence. Build with
`build_scope_metadata_fault_runtime.py` and `build_scope_metadata_fault_bridge.py`;
capture using `scope_metadata_fault_capture.py --startup-only` and review with
`scope_metadata_fault_review.py`. The separate core walker and compact adapter
preserve existing state checks; tests reject wrong function fields and missing
restoration/direct detection. Keep ongoing campaigns pinned.
