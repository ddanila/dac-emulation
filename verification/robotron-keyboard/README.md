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

The first target checks 8,205 supported transactions: each individual matrix
column plus every address in the low serial-output range. It passes with zero
differences. It does not claim equivalence outside that subset.

The audit exercises all 65,536 read addresses and the 32,768 writes that do not
enable the 8282 against the CPU write driver. It currently **fails** with 57,101
differences. Writes with A15 high are excluded because they can contend with the
8282 on the physical bus. `run.py --wave` additionally writes a VCD in
`build/keyboard-controller/`. Reports retain initial counterexamples and source
hashes; comparison failures return nonzero rather than becoming accepted tests.

The firmware target adds the separately implemented TV80 Z80, pinned and licensed
in `third_party/cpu/tv80`. It runs 3.2 million CPU clocks with A, Shift, Caps,
Ctrl, REP, release and reset stimuli. It consumes an external 2 KB ROM without
modifying or redistributing it. Neither CPU comes from the other implementation.
Memory reads use the reference ROM, and the same scheduled contacts drive both.
The HDL CPU uses external digital clock/reset boundaries, not an analog oscillator.

## Recorded results and discrepancy ledger

See `reports/common-subset.json` and `reports/full-audit.json`.

With reference S600 SHA-256
`4b54891c02a8ec279e2b8aec03489a961fc8647e08ad2036dcf82d0634bf7273`,
both CPU implementations emit the same 130 serial bits. Every corresponding
bit has a constant two-CPU-clock timestamp offset in this run. This supports
relative serial timing for this workload, not measured specimen timing.

Coarse LED samples agree, but transitions do not: C records 5 changes and HDL
records 6,783 (including its initial resolution from unknown). The HDL shows
scan-time LED pulses hidden by coarse samples. The whole comparison is therefore
**not equivalent**, despite matching serial data.

| Area | Reference transcription | Production emulator | Status |
| --- | --- | --- | --- |
| LED clock | Inverted IORQ via A2.2B | Updated only with A15 low | Unresolved drawing/firmware/specimen reconciliation |
| Matrix output enable | Inverted A15 via A2.2C | Address range 8000–9FFF | Wider decoding differs |
| Multiple selected columns | Digital sense boundary ORs active contacts | Selected bytes are ANDed | Requires front-end and specimen verification |
| Serial clock | A1 inverts WR directly | Only low-range I/O writes emit callbacks | Wider decoding differs; memory-write clocking remains outside bus audit |

An experimental production change to follow the transcription broke the
existing stable-LED firmware test and was reverted. Do not change the schematic
or expected results simply to obtain a pass. The production core and browser
distribution retain their previous behavior while these differences are resolved.

## Sources and independence

- [Zander drawing 56-330-4103-7](https://www.sax.de/~zander/pc1715/pc_tasts.pdf)
- [TI 7406 documentation](https://www.ti.com/product/SN7406)
- [TV80 upstream](https://github.com/hutch31/tv80), revision recorded in its source manifest

Generated interconnect establishes consistency with the transcription, not an
independent proof that it is correct. Chip models, the C emulator, TV80 and the
firmware exercise provide separate checks with the boundaries above. Physical
trace geometry and specimen identity are separate qualification tasks.
