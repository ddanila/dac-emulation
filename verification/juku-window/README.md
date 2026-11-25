# Juku mode-2 memory window

[Issue #13](https://github.com/infoaed/juku3000/issues/13) concerns external
memory selection in mode 2. The base machine disconnects internal memory in
`4000–BFFF`; a separately decoded external device may respond there. Selecting
mode 2 alone does not install or select an additional RAM bank.

The distinction matters for writes as well as reads. An external ROM must not
receive writes, but internal RAM beneath the window must not receive them either.
This differs from the system BIOS overlays: writes beneath low BIOS in mode 0
and beneath high BIOS in modes 1/2 reach internal RAM/video memory.

## Hardware evidence

The 1988 [Juku manual](https://elektroonikamuuseum.ee/failid/juku/Mikroarvuti_JUKU_kasutamisjuhend_1988.pdf),
section 0.4, printed pages 10–12, explicitly describes a 32 KiB window from
4000h through BFFFh, with internal memory deselected. Multiple external pages
require additional hardware for their individual selection. The inconsistent
16K–34K/8800 wording mentioned in the issue is not a supported alternative map.

The preserved D6 `.038` PROM provides independent evidence from the reproduction
project. Its input wiring is A0–A4 = BA15–BA11, A5 = inverted PC0,
A6 = inverted PC1, A7 = the I/O-cycle qualifier. For memory cycles in mode 2,
all sixteen 2 KiB blocks in the window output Fh: both internal RAM and ROM
selects are inactive. The neighboring blocks retain their normal mapping.
The runner decodes the supplied PROM directly; its hash is provenance rather
than a required match against a stored report.

The reconstruction's
[D6 evidence](https://github.com/ddanila/8080-cosim/blob/dfadee28dc2be6cbd0ee921bc6d449c6832c0a14/docs/d6-physical-decode.md)
documents the captured PROM and continuity-derived wiring. Its
[cartridge boundary](https://github.com/ddanila/8080-cosim/blob/dfadee28dc2be6cbd0ee921bc6d449c6832c0a14/docs/basic-cart-readiness.md)
also distinguishes an external cartridge model from a ROM merely populated
in an on-board socket: the stock D8 decode does not select that socket in this
window. The functional cartridge option is not proof of a stock on-board decode.

## Emulator behavior and scope

DAC's `juku_overlay` selects external memory in this interval, and `juku_wb`
drops its writes. Its other BIOS overlays retain write-through behavior.
The [sinijarv implementation](https://github.com/sinijarv-juku/juku-emu/blob/1b82a399240b14cc9a54679cc075983a47ccdc33/core/src/machine.rs)
maps expansion reads separately and directs mode-2 writes to a discard area.

MAME's [memory map](https://github.com/mamedev/mame/blob/master/src/mame/ussr/juku.cpp)
overlays the cartridge with a read-only mapping over its underlying RAM map.
The CPU-driven probe demonstrates that writes fall through to internal RAM.
The proper distinction is to suppress writes specifically in the external
window, while keeping the BIOS/video write paths. No MAME source is patched
by this investigation.

All three implementations lack a configurable writable external RAM device
in the inspected configurations. This is a separate feature gap from internal
RAM isolation. It should be addressed through an identified expansion device
and its actual address/bank-selection circuitry, not an invented bank port or
an unconditional extra 32 KiB attached to every machine profile.

DAC and sinijarv use FFh for an empty window and unpopulated cartridge space.
Stock MAME supplies JBASIC with the selected BIOS and zero-fills the remaining
region. These read-value conventions are recorded separately from the write
isolation defect. A precise electrical idle-bus value has not been measured.

## Reproduce

The opt-in runner needs Python 3, a C compiler, Rust, MAME with the Juku ROM set,
an unmodified sinijarv checkout, EKTA #0037, JBASIC, and the preserved D6 dump.

```sh
python3 verification/juku-window/run.py \
  --rom /path/to/ekta37.bin --cart /path/to/jbasic11.bin \
  --roms /path/to/mame/roms --mame /path/to/mame \
  --source /path/to/sinijarv-juku/juku-emu \
  --prom ../8080-cosim/ref/physical-proms/validated/d6_038.raw.bin \
  --output /tmp/juku-window
```

Use a new output directory. `--rustc` can specify a compiler path. The runner
compiles current DAC and unmodified sinijarv sources. Results and source/input
provenance belong in [results.json](results.json); generated programs, binaries,
logs and RAM captures remain outside Git.

Each adapter installs the same generated 8080 program at C100h. All diagnostic
reads, writes and PPI mode selections execute as guest instructions. The program
initializes internal RAM to 5Ah in mode 3, selects the tested mode, reads sample
addresses, writes A5h throughout the window and at boundary/overlay controls,
then reads the samples again and signals completion. The host verifies all
32768 underlying bytes plus the sampled reads and controls. Interrupts are
disabled; timing and BIOS startup are outside this memory-decode probe.

The matrix exercises all four modes with an empty window and with the same
JBASIC bytes. For these comparisons, MAME's existing cartridge region is
explicitly filled with FFh and optionally populated, without altering its
address-map handlers. Additional stock-MAME runs leave the region untouched.
Thus the write-through finding also has an unmodified-region reproduction.

The current DAC behavior needs no core change for these configurations. The
suite records other engines' discrepancies without requiring them to keep
failing. Physical PROM contents and software execution support the decode
conclusion, but this is not a new electrical measurement, an expansion-RAM
qualification, or a complete Multibus implementation.
