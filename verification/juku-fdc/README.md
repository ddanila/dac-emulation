# Juku floppy synchronization investigation

Scope: [issue 25](https://github.com/infoaed/juku3000/issues/25), comparing
MAME's Juku data-register retry handlers with the portable Juku controller.
The baseline is in `results.json`; implementation evidence is in
`implementation.json`. The experimental synchronization model is opt-in. It
is not yet a verified reconstruction of the board circuit.

## Experimental implementation

Build with `DAC_JUKU_EXPERIMENTAL_FDC_SYNC=1`. The dedicated targets isolate
these objects from the default build:

```sh
make test-juku-fdc-sync
make build/libdac-fdc-experimental.so build/fdc-experimental.mjs
make test-juku-fdc-sync-wasm
```

Emscripten must be on PATH for the WASM targets. The normal emulator retains
its existing behavior. No browser setting or public session API is added.

The 8080's optional `io_ready` callback observes an IN/OUT at the end of its
I/O T2 (nine nominal cycles from instruction start). It must have no bus
side effects. A low result advances one Tw; a high result completes T3 and
invokes the existing read/write callback exactly once. Operand, direction,
port and pending state survive execution-budget returns and snapshots.
Interrupt acceptance waits until completion. This models the I/O phase;
memory-fetch wait states and the complete board clock circuit are not modeled.

Juku's provisional rule holds a matching active data transfer while BUSY is
set and DRQ is clear. DRQ or command completion releases it. It observes raw
signals without acknowledging INTRQ. It neither rewinds PC nor completes an
instruction with dummy data before retrying. Controller data-register access
after an error remains an ordinary register access, without a transfer-buffer
side effect. Reset cancels pending I/O. An indefinitely blocked transfer still
returns when the host execution budget is exhausted.

The experimental path enables byte pacing and retains Write Sector preload
timing. It supplies index events at 300 RPM with a 2 ms pulse while a mounted
drive's motor is on. This is a functional rotating-drive model, without
spin-up, flux, rotational sector placement or electrical waveform claims.
The shared WD179x implementation and Kaypro configuration are unchanged.

Juku internal snapshots use distinct version tags for the default and
experimental configurations, reject earlier layouts, and restore the READY
callback from the running build. Pending state is serialized, not callbacks.

## Guest and HDL verification

```sh
python3 verification/juku-fdc/workload.py \
  --library build/libdac-fdc-experimental.so --wasm build/fdc-experimental.mjs \
  --mame /path/to/mame --roms /path/to/mame-roms \
  --rom /path/to/ekta37.bin --disk /path/to/prog1.juk \
  --output /tmp/juku-fdc-workload

python3 verification/juku-fdc/hdl.py \
  --cosim ../8080-cosim --rom /path/to/ekta37.bin --disk /path/to/prog1.juk \
  --output /tmp/juku-fdc-hdl --full-board
```

Use new output directories. The guest diagnostic creates `FDC25.TST`, writes
eight distinct 128-byte records, closes/reopens the file, verifies every byte
and EOF, and returns to EKDOS. An independent image decoder checks persisted
contents and forbids changes outside its allocated blocks and the directory.
All three engines receive separate disposable copies. Raw captures remain
outside Git. Native tests also cover remounting, both controller clocks,
multi-record operations, formatting, index-dependent errors, interrupt
deferral, lost data and write protection. Snapshot/chunk-invariance tests run
through the public runtime in native and WASM builds.

The HDL script reads the sibling checkout without changing it. It runs the
existing timed controller tests, the AG3 scheduler test and a focused VM80A
bench through the captured D2/D30 READY path. That bench deliberately supplies
READY-low/high PROM addresses; it does not claim those stimuli reconstruct
board wiring. It also checks all D94 rows against the captured table and tests
A4 qualification of data-register reads and writes. No baseline report hash
is an acceptance criterion.

`--full-board` instruments the existing boot harness. Its forced READY-high
signal and the runnable board's constant D94 A4 input prevent using it as a
hardware wait oracle, even if boot succeeds. The result explicitly records
whether a sector-transfer boundary was reached. Component success does not
turn an unsuccessful full-board run into a pass.

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

A verified default replacement must establish the decoded I/O qualification, stall
assertion, DRQ release, completion/error release, and reset behavior from
schematics/manuals or a physical capture. It must preserve one pending bus
transfer while devices advance, without completing and replaying an IN/OUT
or acknowledging controller status as a side effect. That requires a CPU/bus
interface supplied by the experimental 8080 path.

After establishing that contract, cover normal reads and writes, the initial
write preload interval, delayed/missing DRQ, missing sectors, write protection,
Force Interrupt, reset, and controller/port variants. Verify guest-visible data
and error recovery as well as timing. Remove the machine's write lead-in
override only together with working synchronization. Neither enabling pacing
alone nor adding a fixed delay constitutes the hardware model.

## Limits

Real-firmware coverage is EKTA #0037/EKDOS 2.30 on MAME 0.289, native and WASM.
MAME error-release behavior, other ROM/controller variants and real hardware
remain unverified. Formatting and abnormal transfer tests exercise our
experimental machine model, not MAME. The baseline script records observations
without requiring a corrected emulator to preserve the earlier failure.

The Western Digital FD179X-02 data sheet (printed pages 6 and 12–13) supplies
the independent controller-side DRQ, status acknowledgement, lost-data and
write-preload contract. MiSTer's `Vector-06C_MiSTer/rtl/wd1793.sv` is a useful
separate functional implementation, but its CPU-enable-counted read timer and
watchdog are not a physical timing oracle for Juku. Neither source establishes
the board's synchronization wiring. Default promotion requires that evidence
and a successful full-machine timing comparison.
