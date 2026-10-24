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
| What constrains live reset-release convergence? | [Solver audit](reports/reset-release-audit/assessment.json) and [matched scheduling](reports/fixture-grid-reset/assessment.json) establish completed short prefixes with stable observed bus edges. [Peak witnesses](reports/fixture-grid-reset/peak-review.json) localize voltage differences. [Gear controls](reports/fixture-grid-gear/assessment.json) reduce the finest-pair maximum but still fail per-node monotonic refinement; full-repeat and physical admission remain open. |
| Which reset-capacitor orientation does the reference support? | [Signed-voltage diagnostic](reports/reset-capacitor-polarity/assessment.json) and [proposed polarity](reports/reset-capacitor-polarity/proposed-polarity.json). Reproduce with `reset_capacitor_polarity.py --out <directory>`; complete compressed traces are local outputs. Does not identify installed polarity or admit real capacitor behavior. |
| Does the C4 source disagreement change reset release? | [Source variants](reset-capacitance-sources.json), [generic comparison](reports/reset-capacitance/generic/assessment.json) and [SC236 DC-profile comparison](reports/reset-capacitance/sc236-dc/assessment.json). Isolated startup/recovery timing with fixed loads; no installed-value or full-board qualification. Reproduce with `reset_capacitance_review.py --out <directory>` and optionally `--npn-profile sc236-dc`; complete compressed traces are local outputs, while decks, logs and hash receipts are retained. |
| Does the host-loaded closed board qualify? | [Startup-inclusive capture](reports/board-host-rising-full-startup/assessment.json) passes reset, bit transport and scenario-window checks with rising RxC. Host voltage, nominal-threshold width and sampled-stability screens complete, but CPU clock high-level and timing screens fail. Refinement, supply recovery and device qualification remain open. |
| Does corrected sampling cover service scenarios? | [Single press](reports/firmware-host-rising-load-fine/assessment.json), [reset](reports/firmware-host-rising-reset-minbreak-fine/assessment.json), [modifier](reports/firmware-host-rising-modifier-minbreak-fine/assessment.json), [release/repress](reports/firmware-host-rising-release-repress-minbreak-fine/assessment.json) and [control](reports/firmware-host-rising-control-minbreak-fine/assessment.json) pairs support logical and serial-edge agreement. The [independent timing screen](reports/host-receiver-timing-review/assessment.json) supports sampled stability, not U856 device applicability. [Indicator refinement](reports/firmware-host-rising-indicators-minbreak-fine/assessment.json) also supports serial and LED intent timing, with ordinal LED agreement against C. Other scenarios and device qualification remain separate. |
| Does the held-key/repeat/release capture pass review? | [Repeat capture](reports/firmware-host-rising-repeat-minbreak/assessment.json) passes sampled voltage-envelope, receiver-stability and nominal clock-width screens. A matched refinement pair and device applicability remain open. |
| Do loaded voltages converge? | [Single-press refinement](reports/firmware-host-rising-load-refined/assessment.json), [release/repress](reports/firmware-host-rising-release-repress-minbreak-fine/assessment.json), [control](reports/firmware-host-rising-control-minbreak-fine/assessment.json) and [indicator comparison](reports/firmware-host-rising-indicators-minbreak-fine/assessment.json) retain material absolute-time voltage differences despite serial-edge agreement. |
| What constrains the strict-tolerance failure? | [Numerical assessment](reports/host-mpfr-transient/assessment.json): Gear with higher-precision linear solving completes the coarse replay but fails refinement; further linear precision does not change the trajectory. The [integration arithmetic audit](reports/host-mpfr-integration/assessment.json) also fails with higher-precision integration alone and combined with linear solving. [Exact rollback and represented-time controls](reports/host-represented-time/assessment.json) also fail. The [capacitor-stamp audit](reports/host-capacitor-stamps/assessment.json) isolates material assembly loss in the final frozen system. The [transition-window audit](reports/host-capacitor-onset/assessment.json) finds material sensitivity in a bounded saved state before the rejected voltage excursion; frozen corrections do not establish a transient remedy. [Bounded accepted-state captures](reports/host-accepted-budget/assessment.json) show that exact capacitor additions alone retain large cable-voltage excursions and refinement differences; they do not qualify a remedy. [Later resistor/switch additions](reports/host-postcap-additions/assessment.json) permit two finer short-window completions, but coarse failure and material absolute-time differences remain. [History sensitivity](reports/host-history-sensitivity/assessment.json) bounds hypothetical single-rounding perturbations in selected frozen systems; it does not bound accumulated trajectory error. |
| Which alternative solver controls were checked? | [Tighter truncation](reports/firmware-host-strict-trtol-point1/assessment.json) and [KLU](reports/firmware-host-klu-strict/assessment.json) still fail. The [mapped ngspice control](reports/host-driver-mapped-ngspice/assessment.json) and [Xyce replay](reports/host-driver-mapped-xyce/assessment.json) do not establish equivalent trajectories. |
| Does service qualification cover onboard startup? | [Service repeat qualification](reports/repeat/refined-strict-time/qualification/qualification.json) uses external clock/reset. [Supply isolation](reports/clock-output/full-precision-supply-isolation/assessment.json) and [independent startup replay](reports/clock-output/xyce-recorded-supply/assessment.json) retain the separate oscillator convergence question. |
| Are oscillator device models applicable? | [Device-condition review](reports/clock-output/diode-role-review/assessment.json), [candidate admission](reports/clock-output/device-admission/assessment.json) and [output I/V review](reports/clock-output/ls00-output-iv/assessment.json) constrain candidates. [Internal-state analysis](reports/clock-output/oscillator-internal/assessment.json) and [independent transfer replay](reports/clock-output/xyce-transfer500/assessment.json) do not establish calibrated dynamics or general stability. |
| Are CPU reads electrically valid? | [Electrical-bus assessment](reports/rom-read-envelope/electrical-bus/assessment.json) and [floating-read analysis](reports/floating-io/static-analysis.json) separate functional output from released-input voltage and pin timing. |
| Are the host and cable models qualified? | [Host circuit evidence](reports/host-receiver/assessment.json), [filter hypotheses](reports/filter-coupling/assessment.json) and [buffer switching](reports/host-buffer-switching/assessment.json) retain uncalibrated winding, clamp and device assumptions. [Reference 7406 switching](reports/host-driver-switching/assessment.json) leaves driver dynamics unqualified; the [vendor candidate](reports/host-driver-vendor-review/assessment.json) fails SN7406 DC admission. The [matched filter comparison](reports/firmware-filter-strict/assessment.json) finds no convergence remedy in the tested coupling hypothesis. |
| Does reset recover after a supply dip? | [Reset dip response](reports/reset-brownout/report.json) does not establish reliable firmware restart or specimen brownout behavior. |

## Electrical evidence index

[`electrical-status.json`](reports/electrical-status.json) indexes the scoped
results for DAC; `electrical_status.py --check` checks its source hashes.
[Static device endpoints](reports/device-endpoints/assessment.json) pass the
sampled published conditions, but do not qualify switching or oscillator dynamics.
[Exact BJT/diode additions](reports/host-device-additions/assessment.json) preserve
the disabled control and still leave coarse failure and material refinement error.
The [qualified-CPU bridge audit](reports/qualified-cpu-bridge-time/assessment.json)
records a backwards time request exceeding the HDL tick; logging leaves the
control waveforms byte-identical. The [input-boundary regression](reports/input-barrier/assessment.json)
reproduces the cause in the original scheduler and verifies an input-boundary
patch against paired qualified-CPU captures. This fixes the tested input-driven
ordering failure, not general rollback for autonomous HDL or multiple clients.
Service acceptance now stops at a supply-relative bus-voltage failure; full-board
startup timed out. Neither result establishes complete electrical acceptance.

The [isolated bus-read replay](reports/bus-read-replay/assessment.json) preserves
all D1 loads, driver resistances and recorded supply/enable transitions. Tight
ngspice, Xyce and independent KCL integration reproduce charge above the falling
rail. This is conditional agreement on sampled boundary data, not a bound on the
coupled solver or proof of a specimen fault. The retained `coupled/` runs include
a tighter-tolerance abort and timeout. Reproduce the capture with
`bus_read_capture.py`, then replay it with `bus_read_replay.py`; keep input limits
unchanged while reviewing driver dynamics and transient applicability.
The [bus-device admission review](reports/bus-device-admission/assessment.json)
separates logic thresholds, static input ranges and maximum ratings. The latter
cannot substitute for operating guarantees. Linear nominal-supply drivers fail
the loaded-high guarantee at minimum rated supply; they remain stress fixtures.
`bus_device_contract.json` records the source-reviewed scope and missing dynamics.

The [transition isolation](reports/bus-transition/assessment.json) reproduces the
first tight-tolerance failure without HDL feedback. The existing zero-hysteresis
switch correction passes its plateau regression, preserves nonzero-hysteresis
controls byte-for-byte and completes that isolated replay. The coupled run still
fails later; a recorded-output replay of the later prefix completes but cannot
prove equivalence to the live trajectory. The corrected runtime remains diagnostic.
Use `bus_transition_probe.py` for tolerance sweeps and recorded-output isolation;
retained decks, runtime fingerprints and reproduction notes accompany the review.

The [live-transition audit](reports/live-transition/assessment.json) isolates
truncation/error-estimation rejection with converged Newton solves and no ADC
state change inside the selected collapse window. Logging preserves the waveform.
Recorded-output replay changes both forcing history and breakpoint placement, so
its completion cannot identify a feedback defect. A reduced fixture keeps CPU/bus
feedback and output/supply circuitry live, but substitutes the inactive matrix and
fails later; it is not equivalent full-board evidence.

The opt-in [DAC corner experiment](engine-patches/dac-ramp-breakpoint.patch)
schedules a missing ramp-end breakpoint when an event lands at the analog boundary.
The compiled upstream regression verifies the omission and unchanged output
arithmetic. Tight live controls still abort or time out, so the candidate is not
adopted. `build_live_transition_models.py` builds fingerprinted code models;
`live_transition_probe.py` reproduces controls with explicit runtime inputs.

The [live-state replay](reports/live-state/assessment.json) captures accepted
histories and pre-factorization equations. Independent 80/160-digit solves
separate the initial capacitor rejection from the terminal ill-conditioned
solve: correcting the logged LTE recurrence alone does not remove rejection.
Use `live_state_review.py LOG --out REPORT` to recompute the frozen comparison.
`--state-audit` requires the supplemental live-state patch; `--mpfr-transition`
requires the MPFR linear and live-window patches and changes linear arithmetic
only after the selected transition boundary. This is a diagnostic intervention,
not a qualified solver or a full high-precision trajectory. The short timestep
pair completes, but a drive timing mismatch, tighter-tolerance timeout and later
long-run failure leave convergence open. `live_prefix_review.py` compares the
retained short waveforms without phase alignment.

The [switching-event review](reports/switching-events/assessment.json) excludes
constant-capacitor stamp rounding as the dominant cause in the captured initial
and terminal trials. Picosecond bus-edge observations expose timing hidden by
whole-nanosecond logs. Analytic threshold breakpoints stabilize the ideal fixture
clock in short controls; they do not repair the general ADC crossing model.
The [later-collapse audit](reports/output-switch/assessment.json) identifies
L1.1 flux-history rejection with converged Newton solves and a stable switch.
The [inductor-chain replay](reports/inductor-chain/assessment.json) traces that
later collapse to lost cancellation in floating-capacitor history-current
assembly. Its paired-RHS regression restores current conservation without
changing matrix coefficients; an inductor-only correction does not explain the
observed current jump.

Exact capacitor assembly plus recovery of resistor/switch matrix additions
allows both [full live refinement runs](reports/inductor-chain/network-refinement.json)
to complete with matching firmware reads and latches. Disabled corrections and
added observations preserve their baseline traces. The correction remains
opt-in: absolute-time waveform differences around ideal switch transitions
still prevent a convergence claim. General ADC timing, device admission and
coupled startup/service qualification remain open. Reproduce the comparison
with `network_refinement_review.py`; patch order and build provenance live in
[the runtime receipt](reports/inductor-chain/provenance.json).

The [boundary trace](reports/boundary-refinement/boundary-review.json) follows
D0 through undefined receiver logic to the DAC's threshold plateau; observation
preserves the original waveforms. The [small reproducer](reports/boundary-refinement/unknown-output/assessment.json)
shows why that plateau retains the ideal switch's previous state rather than
specifying a physical 7406 transfer curve. The opt-in
[ADC crossing candidate](engine-patches/adc-crossing-breakpoint.patch) requests
rollback to interpolated threshold crossings, retaining unknown states and
native threshold rules. Analytic ramp and RC controls pass, and the
[matched three-level live series](reports/boundary-refinement/assessment.json)
completes with preserved firmware reads. RMS disagreements improve relative to
the baseline, but ideal-switch voltage peaks remain and waveform convergence is
not established. Keep the candidate opt-in pending those electrical gates and
physical-driver admission. [Traffic preflight](reports/boundary-refinement/traffic/assessment.json)
prepares press/release, overlapping contacts and reset during observed serial
activity; production-C coverage is not electrical execution.

The experimental [7406 dynamic candidate](reports/7406-dynamic/report.json)
fits storage parameters to published typical delays while treating junction
capacitance as an explicit hypothesis. `ttl7406_dynamic.py --out DIRECTORY`
reproduces calibration and withheld edge/DC checks; fitting is not independent
device validation. `ttl7406_dynamic_validation.py --device-report REPORT --out
DIRECTORY` checks temperature, loading refinement and intermediate-input settling.
Use `prepare_dynamic_driver.py` on a prepared electrical D0/WR fixture with
`--bus-7406-pf 0` to avoid counting gate capacitance twice. It removes the serial
intent DAC channels and connects the candidate directly to both physical inputs.
`live_transition_probe.py --network-trace --physical-driver-trace` observes these
inputs and driver currents. This path remains diagnostic until device admission
and absolute-time board refinement pass; CPU drivers remain endpoint fixtures.
The [CPU drive screen](reports/serial-path/cpu-drive/report.json) compares the
fixed-resistance control with a supply-anchored endpoint hypothesis.
`cpu_serial_drive.py --device-report REPORT --out DIRECTORY` reproduces the
supply, temperature and pin-load checks. Passing logic levels or matching a DC
endpoint does not validate the predicted transient currents or CPU I/V law.
The [complete live refinement](reports/7406-dynamic/live/assessment.json) preserves
reference firmware reads and reduces serial-voltage disagreement to millivolt
scale. The [expanded saved-vector review](reports/direct-repeat/assessment.json)
checks bus, receiver and drive-control observations too. Board voltages meet the
short-window budget; the strict all-saved/nonincreasing screen fails. The retained
full-repeat attempts and disabled controls do not qualify. A bounded startup
comparison supports the opt-in DAC-corner correction; no production default changes.
Use `saved_network_review.py --help` to replay complete-window comparisons and
`startup_drive_review.py --help` for the startup controls. New live runs can select
`--all-saved-network`; `complete_network_review.py --end-seconds` requires the
explicit complete interval. Retention preserves every available sample, including
failed controls. Longer runs need a concrete board/receiver decision, not merely
an improved private fixture waveform.

The [serial-path review](reports/serial-path/assessment.json) separates that
numerical agreement from physical admission. Internal observations identify
reverse output-transistor operation; isolated recovery controls expose load
sensitivity and disagreement between candidates passing the same selected
screens. The [manufacturer scope review](reports/7406-dynamic/operating-region-review.json)
does not supply the missing device-specific recovery parameters.
`serial_device_trace.observe` adds internal probes without changing components;
`serial_device_review.py` checks their live control and current balance.
`serial_path_probe.py --live TRACE.xz --device-report REPORT --ngspice RUNTIME
--out DIRECTORY` reproduces the isolated experiment; `serial_recovery_review.py`
compares its hypotheses. `retain_serial_recovery.py` retains inputs, logs and
all accepted points in the reviewed event window, with original-capture hashes;
failed controls remain explicit. These forced-input replays are not feedback
runs or proof of initialization independence.
[Direct-driver traffic fixtures](reports/7406-dynamic/traffic/assessment.json)
are prepared and C-checked. Their electrical acceptance remains gated on
independent driver, CPU/bus and load admission.

The optional [evaluator cache](engine-patches/eval-cache.patch) reuses shared pure
subexpressions only within one value/gradient evaluation. It defaults off;
`ROBOTRON_EVAL_CACHE=exact` enables it. Build the pinned ngspice 47 archive with
the patch set and configure flags in [the runtime receipt](reports/eval-cache/runtime.json).
Do not use fast-math. The [startup benchmark](reports/eval-cache/assessment.json)
retains byte-equality receipts for disabled/enabled runs; use
`eval_cache_benchmark.py` to reproduce them from a prepared startup directory.
New captures derive their window from the deck and reject incomplete, nonfinite
or nonmonotonic traces; timeout/failure receipts remain in the output directory.
The runtime receipt fingerprints the executable, initialization, code models and
external co-simulation/VPI libraries. Loaded-library changes invalidate paired runs.
The [extended startup comparison](reports/eval-cache-startup-2ms/assessment.json)
covers the first 2 ms, including supply settling into its rated range; it does not
cover later firmware service. The
[recorded bus-read comparison](reports/eval-cache-bus-read/assessment.json) checks
an unchanged captured-boundary replay, not live CPU/HDL service. A prepared
`fixture.json` can select its deck, input files and output traces; without it the
runner uses the startup fixture. Longer startup and live service controls must
pass before enabling the cache in qualification runs.


Verify retained endpoint and bridge evidence with `device_endpoint_probe.py
--verify reports/device-endpoints` and `bridge_time_review.py --verify --out
reports/qualified-cpu-bridge-time` from this directory.

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

## Reference CPU clock acceptance

`clock_acceptance.py --out BUILD --retain REPORTS` screens startup from zero
with the reference oscillator wiring and closed BR1 against the published U880
levels and valid-level timing. The [retained screen](reports/clock-acceptance/assessment.json)
keeps supply/load assumptions, model identities, source hashes and complete
lossless captures. Replay their acceptance checks with
`python3 verification/robotron-keyboard/analog/verify_clock_acceptance.py verification/robotron-keyboard/analog/reports/clock-acceptance`.
It is an isolated oscillator screen, not closed-board or
independent device qualification. The reference behavioral models fail; raising
the high level alone does not repair pulse width or slew. Loose intended-family
gate measurements around the switching region and under the reference pullup
are needed before admitting a replacement model.
