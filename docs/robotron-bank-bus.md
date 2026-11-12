# 1715M/W memory-bank bus sequencing

Port 24h contains source (bits 2..0) and destination (bits 6..4) selectors.
The former implementation treated these as unconditional read/write banks.
PC001 measurements on 2026-11-12 disproved that rule.

The corrected functional model observes the CPU's actual bus pins every
T-state. M1 resets the sequence. Subsequent non-refresh memory machine cycles
alternate source, destination, source, destination, regardless of RD/WR.
Held strobes are one cycle, not several accesses. Opcode fetches use source.
The CAS PROM still maps the resulting selector and address to physical RAM.
DMA retains independent source-read/destination-write routing.

This explains more than LDIR: `LD (HL),A` writes source; `LD (HL),n` fetches
its operand from source and writes destination. `LD (nn),A` has two operand
reads and writes source. `LD HL,(nn)` reads its low and high data bytes from
different banks. PUSH, POP, EX (SP),HL, indexed operations, read-modify-write,
and all four block-copy instructions follow the same sequence. No opcode
recognizer, guest address special case, or BIOS patch is involved.

## Evidence and regression

`tests/fixtures/robotron-bank-bus/pc001.txt` is the console output from a
20-case diagnostic executed under banked CP/M on physical PC001, headless at
62400, W4 4.0.0. Columns are source[4000], source[4001], destination[4000],
destination[4001], L, H, A. Each case independently initializes the banks to
11/22. Source data is 5A at common F060. The diagnostic returns to CP/M; no
power cycle was needed. The matching assembly and generator are included.
Build with `python3 tests/fixtures/robotron-bank-bus/build.py` and z80asm on
PATH. BANK.COM is a destructive diagnostic for scratch RAM, not a normal app.

`make test-robotron-bank-bus` executes Z80 byte sequences and compares all
seven values against those measurements. It failed on the old model at the
first scalar copy. It also checks held-strobe/WAIT invariance, refresh and M1
handling, DMA isolation and callback rebinding. It is part of `make test`
and the native sanitizer CI checks. Expectations come from the hardware,
not from the emulator's bank-selection helper.

The corrected model also rejects the original scalar-copy CP/M BIOS in the
existing instruction-executed BIOS probe. The corrected LDIR BIOS passes.

## Precision and limits

This is a hardware-measured functional bus model, not a claim of reconstructed
schematic gate timing. The public classic-1715 schematic is not the W/M
motherboard circuit; neither the MAME nor FPGA reference models captured
this distinction. Twenty instruction cases constrain the inferred cycle rule;
additional analog timing, WAIT/interrupt transitions and DMA arbitration on
physical hardware have not been measured here. WAIT/refresh tests are model
invariants, not new physical measurements. Keep this distinction when extending
the model or describing its fidelity.
