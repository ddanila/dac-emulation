# Robotron 1715M / PC-1715W functional profile

An experimental portable C machine using the shared Z80 adapter. The tested profile is the S550 boot ROM, 287 CAS PROM and TOS/M 1.0 disk decoded from `A92V010A.TD0`. It cold-boots to `A>`, accepts keyboard packets, creates/reads/copies/deletes files and reboots from an exported session disk. No guest ROM patches or guest-PC traps are used. Matching Danila's exact physical machine is still pending.

Implemented: 256 KB RAM with independent read/write banks selected through the supplied CAS PROM; boot ROM/gap/character/video windows; CTC timer cascade and DMA/CTC interrupt priority with in-service/RETI handling; SIO keyboard receive registers with K7658 packets; DMA addressing, ready polarity, end-of-block interrupt control and board-gated terminal count; raw 80×2×5×1024 media; floppy specify/sense/recalibrate/seek/read-ID/read/write/scan commands. Storage uses `common/media`. Native I/O events use `common/trace`.

The bounded 8275 renderer honors display start/stop, programmed geometry (up to 80×24 cells and 16 scanlines), cursor position/style, field attributes, alternate glyph page, and end-of-row/screen controls. TOS/M programs 80×24×12, producing 640×288 pixels. Rendering remains separate from raster/DMA timing.

Build `make`, then:

```sh
build/robotron-boot /path/s550.bin /path/cas.bin /path/robotron.img 40000000 $'DIR\r'
```

`--writable` enables only an in-memory disk copy. Add `--export /path/new-session.img` to save that copy to a **new** file. Input files and existing output files are never overwritten. The native scripted runner allows two emulated seconds after Enter/EOF so the following command does not race a disk operation. `DAC_TRACE_IO=1` logs I/O writes. Convert an external CAS hex file with `python3 tools/prepare_robotron_media.py 287.hex cas.bin`.

## TOS/M media recovery and the PIP failure

The reference release's `sw/images/tosm10_x/robotron.img` boots, but its `PIP.COM` differs from the original TeleDisk file in all ten 1 KB sectors. The emulator loads those damaged bytes faithfully; that binary returns without creating the requested file. This was an input-media problem, not evidence of a CPU or DMA copy defect.

Decode `sw/images/tosm10_orig/A92V010A.TD0` from the same externally supplied archive instead. The optional host tool uses libdsk; libdsk is not included in or linked into the emulator or browser. With libdsk headers/library installed:

```sh
cc -std=c11 tools/robotron_td0_to_raw.c -ldsk -o build/robotron-td0-to-raw
build/robotron-td0-to-raw /path/A92V010A.TD0 /path/new-robotron.img
```

For Homebrew installations, add `-I"$(brew --prefix)/include" -L"$(brew --prefix)/lib"` to the compiler command. The tool reads every sector in cylinder/head/sector order, rejects sector errors and refuses existing output paths. The expected raw SHA-256 is `f724763d5e48c0f15341e95d7b85f645533dd7dfa270cbce4e44d3025e62b23b`. No repair bytes, firmware or historical software are distributed here.

```sh
python3 tests/integration/robotron_boot.py s550.bin cas.bin new-robotron.img --file-operations
make build/browser-reference
node tests/integration/wasm_parity.mjs s550.bin cas.bin new-robotron.img --file-operations
```

The native regression creates text via `PIP ...=CON:`, reads it, copies text and the 10 KB PIP executable, compares file bytes independently, reboots the exported disk, deletes the new files and checks every original file is intact. Read-only media must remain byte-identical. The optional WASM check compares both boot pixels and the complete disk after create/read/copy with native execution.

## Known limits

- Functional, not cycle-accurate: DMA byte/burst timing, search/match/ready interrupts, auto-restart, pulse output and six-command reset sequencing remain incomplete. End-of-block interrupt/TC, ready polarity and DMA/CTC in-service priority have focused tests; this does not qualify all peripheral modes.
- Only one drive and one explicit raw geometry. Seek/rotation timing, reset interrupt queues, multi-track head switching, format commands, deleted-sector/error metadata and detailed scan semantics remain incomplete. Whole/partial write completion, write protection, busy/data/result transitions and reset cancellation have focused checks.
- CTC external trigger timing, SIO serial clocks/interrupts, printer and V.24 are pending. Keyboard packets do not execute the keyboard MCU firmware.
- The 8275 stream renderer does not implement scan timing, real display DMA/FIFO limits, raster interrupts, double-spaced rows, light pen or character-attribute line graphics. Blink uses a nominal 50 Hz clock; unusual geometries are bounded to the supported framebuffer. Field attributes and cursor are not a claim of complete 8275 emulation.
- No MAME runtime differential or physical-machine comparison has been performed. Source comparisons and passing applications do not prove hardware accuracy.

See [source identities](../../docs/z80-provenance.json), [validation](../../docs/z80-browser-validation.md) and `REFERENCE_LICENSE`. Original DAC code is MIT; reference attributions are preserved in `NOTICE`. ROMs and disks are neither bundled nor licensed by this repository.
