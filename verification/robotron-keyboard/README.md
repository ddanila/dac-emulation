# Robotron keyboard board co-simulation

This qualification harness compares a KiCad-derived reference circuit with the
production keyboard emulator. It is not part of the browser runtime. The
schematic and physical reconstruction are maintained in `3d-models`; the pinned
revision and connectivity hash are in `reference/source.json`.

`generate.py` emits numbered-pin Verilog interconnect from the exported schematic.
`chips.v` separately implements 7406 open-collector inverters, DL003 open-collector
NAND gates, DL074 flip-flops and the 8282 transparent input latch. The sense
transistors are a documented digital boundary; oscillator frequency, analog
reset, contact resistance and propagation delay are not simulated. Supply
pull-ups use Verilog pull strength. Unused pins remain explicit.

## Run the comparisons

Requirements: Python 3, a C compiler and Icarus Verilog (`iverilog`, `vvp`).

```sh
make test-keyboard-controller
make audit-keyboard-controller
make qualify-keyboard-controller S600_ROM=/path/to/s600.bin
```

The first target checks 8,210 supported transactions: LED latch addresses, each individual matrix
column and every address in the low serial-output range. It passes with zero
differences. It does not claim equivalence outside that subset.

The audit exercises all 65,536 I/O read addresses, 32,768 I/O writes and
32,768 memory writes. It **passes 131,072 transactions with zero differences**.
Writes with A15 high are excluded because they can contend with the 8282 on the
physical bus. Repeated callback ticks must not emit duplicate serial clocks.
`run.py --wave` writes VCD traces under `build/keyboard-controller/`.
Failures return nonzero; reports retain counterexamples and source hashes.

The firmware target adds the separately implemented TV80 Z80, pinned and licensed
in `third_party/cpu/tv80`. It runs 4.6 million CPU clocks with A, Shift, Caps,
Ctrl, REP, release and reset stimuli. It consumes an external 2 KB ROM without
modifying or redistributing it. Neither CPU comes from the other implementation.
Memory reads use the reference ROM, and the same scheduled contacts drive both.
The HDL CPU receives external digital clock/reset through the CPU sides of open
BR1/BR2 in generated wiring. The analog oscillator/reset sources are boundaries.

## Recorded results and discrepancy ledger

See `reports/common-subset.json` and `reports/full-audit.json`.

With reference S600 SHA-256
`4b54891c02a8ec279e2b8aec03489a961fc8647e08ad2036dcf82d0634bf7273`,
both CPU implementations emit the same 390 serial bits. Every corresponding
bit has a constant two-CPU-clock timestamp offset in this run. This supports
relative serial timing for this workload, not measured specimen timing.

The 11,971 raw LED state records now agree, as do coarse samples. The original
emulator incorrectly gated LED updates with A15, narrowed matrix decoding to
8000–9FFF, ANDed selected columns, and restricted serial strobes to low I/O writes.
The corrected reference implementation clocks LEDs on every I/O access, enables
the matrix whenever A15 is high, ORs active contacts, and clocks serial output on
memory writes as well as I/O writes. The unchanged KiCad-derived HDL independently
checks these changes. The earlier failing reports remain available in git history.

This is **logical equivalence within the stated digital boundaries**, not exact
CPU-clock equivalence: serial timestamps differ by two clocks; LED transitions
usually differ by -1 clock, with +2 on write cycles and separate initialization/
reset settling offsets. The report records the offset histogram and explicitly
sets `cycleEquivalent` false. Analog settling and bus contention are outside scope.

The production `leds` field and `dac_keyboard_latches` expose raw electrical state.
`dac_keyboard_leds` applies a display-only 2 ms peak hold to avoid frame-sampling
flicker; it is not an analog LED model and never feeds the electrical simulation.
The S600 visible-LED test checks this display state; co-simulation checks raw latches.
A synthetic firmware fixture now sets A14/A13 during its matrix polling loop if
it intends to leave both lamps on. Snapshot layout 15 preserves display persistence.

## Synchronization

After committing CAD changes, run:

```sh
python3 verification/robotron-keyboard/sync_reference.py ../3d-models
```

This rejects dirty CAD sources and stale exports, pins connectivity and its source
revision, and regenerates HDL. Rerun both qualifications and save their reports
before publishing. Reports hash the harness, production keyboard, both CPU
implementations and generated wiring. Museum synchronization rejects stale reports.
Unsupported digital components and colliding HDL net names fail generation.

## Sources and independence

- [Zander drawing 56-330-4103-7](https://www.sax.de/~zander/pc1715/pc_tasts.pdf)
- [TI 7406 documentation](https://www.ti.com/product/SN7406)
- [TV80 upstream](https://github.com/hutch31/tv80), revision recorded in its source manifest

Generated interconnect establishes consistency with the transcription, not an
independent proof that it is correct. Chip models, the C emulator, TV80 and the
firmware exercise provide separate checks with the boundaries above. Physical
trace geometry and specimen identity are separate qualification tasks.


## Bridge isolation and source review

Every comparison first runs `service_tb.v`: 13 checks cover closed bridges,
independent reset injection with the onboard clock, external clock/reset with both
bridges open, the clock pullup, floating reset and opposing drivers resolving to X.
`build/keyboard-controller/service.vcd` and `service.log` retain the waveform and
check result. The `service` section of each report records this scope.

`controller_service` is generated from BR1/BR2 and CPU pin connections in KiCad;
it does not duplicate their wiring in the testbench. BR1 isolates A7:8 from A5:6;
BR2 isolates V4.9:C from A5:26. Separate source/CPU nets preserve those boundaries.
The virtual tests establish digital isolation behavior, not measured reset delay,
physical bridge locations, or a manufacturer-approved hardware procedure.

The source review also corrected the reset transistor/capacitor network, separated
BUSRQ from the other CPU pullups, and corrected the cable filter windings and
clock/ground terminal assignments. These were outside the earlier peripheral
comparison. Passing that comparison did not validate those schematic sections.

The [Robotron service handbook](https://www.tiffe.de/Robotron/PC1715/PC-1715-Servicemanual.pdf#page=91)
(1985, printed pp. 89–92) independently supports WR-based serial synchronization,
active-high matrix sensing and IORQ-clocked LED state. Its 700 kHz ±10% nominal
clock encompasses the emulator's 683 kHz setting. Its approximately 100 ms reset
is a reference expectation, not currently an analog model. Oscillator gate pins
and capacitor values differ from Zander's drawing; do not merge the two revisions.
