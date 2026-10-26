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
The [long-window negative controls](reports/postreset-instance-state/negative-assessment.json)
detect the external instance-queue mutation, including delayed injection after
firmware execution. Positive-control equivalence remains a separate requirement.

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
