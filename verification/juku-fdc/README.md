# Juku floppy synchronization investigation

Scope: [issue 25](https://github.com/infoaed/juku3000/issues/25), comparing
MAME's Juku data-register retry handlers with the portable Juku controller.
Measurements and conclusions are in `results.json`. This is a read-path
investigation, not a replacement for the board synchronization circuit.

## Reproduce

From the repository root, with Python/Pillow, a C compiler and MAME:

```sh
python3 verification/juku-fdc/run.py \
  --rom /path/to/ekta37.bin --disk /path/to/prog1.juk \
  --roms /path/to/mame-roms --mame /path/to/mame \
  --output /tmp/juku-fdc-investigation
```

Use a new output directory. MAME requires the Juku ROM set with BIOS
`3.43m_37`; the native ROM must be that same EKTA #0037 image. The script
boots with `TDD`, then types `dir` and Return at 16 seconds, ending at 30
seconds. Native input uses instruction-boundary CPU time; MAME uses host
screen callbacks, as in the issue-20 harness. Input timing is independent of
the guest's video interrupts. The original disk is never mounted writable:
native uses read-only memory storage, MAME a read-only disposable copy.

The native probe records FDC state immediately before IN/OUT instructions.
Its `paced_without_wait` run deliberately changes only `paced_data`, exposing
the absence of machine-level synchronization; this is not a production fix.
State can advance during the instruction, so the pre-IN DRQ count is an
observation, not an exact bus-edge measurement. Final framebuffer text is
decoded using the EKTA #0037 ROM font.

The MAME probe observes I/O callbacks after the driver handler. A retried IN
therefore appears twice, with the PC rewound on the first callback. These are
not two successfully delivered bytes. It does not read FDC status itself,
which would acknowledge INTRQ and disturb the experiment. Lua subscriptions
are retained for the whole run. The final cursor may decode as `?`.

## Hardware evidence required for a replacement

The `8080-cosim` sibling repository retains the relevant schematic reviews:

- `ref/schematics/fdc-irq-conditioner-map.md`: D93 DRQ/INTRQ through D28 to
  D96; the source-drawn set-only behavior leaves the remote clear source
  unresolved. Do not invent that source.
- `docs/d101-section-a-input-source-review.md`: D96-to-D101 source path,
  incomplete owner-board continuity, and the runnable HDL's functional tie.
- `docs/fdc-hardware-handoff.md`: remaining board continuity and timing limits.

These documents are evidence inventories, not proof of a complete CPU wait
equation. The controller's READY input and the CPU's READY input are distinct.

A proper replacement must establish the decoded I/O qualification, stall
assertion, DRQ release, completion/error release, and reset behavior from
schematics/manuals or a physical capture. It must preserve one pending bus
transfer while devices advance, without completing and replaying an IN/OUT
or acknowledging controller status as a side effect. That requires a CPU/bus
interface beyond this instruction-atomic 8080 core's current callbacks.

After establishing that contract, cover normal reads and writes, the initial
write preload interval, delayed/missing DRQ, missing sectors, write protection,
Force Interrupt, reset, and controller/port variants. Verify guest-visible data
and error recovery as well as timing. Remove the machine's write lead-in
override only together with working synchronization. Neither enabling pacing
alone nor adding a fixed delay constitutes the hardware model.

## Limits

Runtime coverage here is EKTA #0037, EKDOS 2.30, boot and directory reads on
MAME 0.289 and native Juku. It does not exercise disk writes, formatting,
error-release behavior in MAME, WASM, other ROM/controller variants, or real
hardware. Source-level concerns about those paths remain hypotheses. The
script records measurements without pinning counts or requiring a corrected
emulator to preserve today's failure.
