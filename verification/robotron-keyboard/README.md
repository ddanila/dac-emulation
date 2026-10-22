# Robotron keyboard board co-simulation

This harness compares a KiCad-derived reference circuit with the production
keyboard emulator. It is separate from the browser runtime. The canonical
schematic and physical reconstruction live in `3d-models`; [reference/source.json](reference/source.json)
pins the imported revision and connectivity. [generate.py](generate.py) emits
numbered-pin wiring; [chips.v](chips.v) owns chip behavior.

## Run

Requirements: Python 3, a C compiler and Icarus Verilog (`iverilog`, `vvp`).
Run from the repository root:

```sh
make test-keyboard-controller
make audit-keyboard-controller
make qualify-keyboard-controller S600_ROM=/path/to/s600.bin
```

The ordinary test covers supported transactions; the audit broadens address
coverage. A15-high writes are excluded because they can contend with the physical
input latch. The firmware target uses an external ROM, without modifying or
redistributing it, and the independently implemented TV80 CPU pinned under
`third_party/cpu/tv80`. The same scheduled contacts drive both implementations.
See [reports](reports/) for coverage, hashes, event comparisons and timing offsets.

Digital qualification injects clock/reset through open virtual BR1/BR2. Sense
transistors and analog circuitry have explicit digital boundaries. Four-state
chip semantics do not model propagation, metastability, floating-input bias or
supply behavior. Raw LED latches are compared electrically; the emulator's
separate display persistence is only a rendering aid.

Logical agreement does not establish exact CPU-cycle equivalence: retained
reports explicitly distinguish them. For electrical circuits and closed-board
firmware execution, use the [analog guide](analog/README.md).

## Synchronize

After committing CAD changes:

```sh
python3 verification/robotron-keyboard/sync_reference.py ../3d-models
```

The importer rejects dirty sources and stale exports, pins connectivity and
regenerates HDL. Rerun the digital qualifications and retain reports before
publishing; museum synchronization verifies their implementation and source
hashes. Generated interconnect checks consistency with the transcription, not
its independent correctness. Keep physical interpretation in the CAD evidence
ledger rather than editing generated wiring.

## Failures and replay

Failures return nonzero and retain stimulus, counterexamples and source hashes
under `build/keyboard-controller/`. `failure.json` indexes failure evidence.
Bus and firmware comparisons can replay a bounded first-divergence waveform;
`run.py --wave` requests full capture. Missing events remain failures, and firmware
diagnostics retain both CPU time coordinates without aligning them. Transaction
bench timestamps are synthetic, not specimen measurements. Runs clear previous
result metadata so an aborted run cannot leave an earlier pass as its result.

## Service and experimental boundaries

The generated service model separates clock/reset sources from the CPU at BR1/BR2.
Service tests cover isolation, injection, release and contention. These are virtual
circuit tests, not evidence of physical terminal order or a manufacturer procedure
for opening specimen links.

Explicit CPU profiles generate isolated read-phase candidates without modifying
vendored TV80 sources. For example:

```sh
python3 verification/robotron-keyboard/run.py --audit --rom /path/to/s600.bin --cpu-profile falling-indexed-candidate --out build/keyboard-controller-indexed-candidate
```

The default remains `tv80`. Candidate functional agreement does not qualify U880
pin timing or synthesis suitability. The manual `keyboard-cpu-phase.yml` workflow
retains profile comparisons separately from fast CI. Consult `run.py --help` for
profile and released-read substitution options. Floating-I/O experiments test
firmware dependence on released reads; they neither add physical pullups nor
waive electrical unknown-input failures. Retained analysis states its assumptions
in [analog/reports/floating-io](analog/reports/floating-io/).

## Sources and independence

- [Zander drawing 56-330-4103-7](https://www.sax.de/~zander/pc1715/pc_tasts.pdf)
- [Robotron service handbook](https://www.tiffe.de/Robotron/PC1715/PC-1715-Servicemanual.pdf#page=91), printed pp. 89–92
- [TI 7406](https://www.ti.com/product/SN7406), [LS74 function table](https://www.ti.com/lit/ds/symlink/sn74ls74a.pdf), [Intel 8282/8283](https://tvsat.com.pl/PDF/8/8282_intel.pdf)
- [TV80 upstream](https://github.com/hutch31/tv80), pinned and licensed in the repository

Published oscillator revisions differ; do not merge them to fit the emulator.
Chip models, the C emulator, TV80 and firmware provide separate checks with shared
inputs and explicit boundaries. Specimen firmware, physical copper and measured
timing remain separate claims.

## Digital completion gate

`digital/qualify.py --rom /path/to/s600.bin` exercises every matrix contact,
overlapping keys, modifier changes and two reset positions within a serial frame.
`digital/review.py build/keyboard-controller-digital --out /tmp/digital-review.json`
combines those captures with the existing repeat/release, bus and virtual-bridge
checks. It returns failure while any completion gate remains open. Raw CPU cycle
coordinates are never shifted; observations outside the declared half-open capture
interval are retained separately. Reports distinguish logical output agreement
from CPU assertion timing and electrical qualification.
