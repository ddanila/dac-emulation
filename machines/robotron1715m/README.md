# Robotron 1715M / PC-1715W functional profile

An experimental portable C machine using the shared Z80 adapter. The tested profile is the S550 boot ROM, 287 CAS PROM and TOS/M 1.0 disk decoded from `A92V010A.TD0`. It cold-boots to `A>`, accepts keyboard packets, creates/reads/copies/deletes files and reboots from an exported session disk. No guest ROM patches or guest-PC traps are used. Matching Danila's exact physical machine is still pending.

Implemented: 256 KB RAM with independent read/write banks selected through the supplied CAS PROM; boot ROM/gap/character/video windows; CTC timer cascade and DMA/CTC interrupt priority with in-service/RETI handling; optional S600 keyboard CPU/matrix with clocked SIO reception, or a legacy byte adapter; DMA addressing, ready polarity, end-of-block interrupt control and board-gated terminal count; raw 80×2×5×1024 media; floppy specify/sense/recalibrate/seek/read-ID/read/write/scan commands. Storage uses `common/media`. Native I/O events use `common/trace`.

The bounded 8275 renderer honors display start/stop, programmed geometry (up to 80×24 cells and 16 scanlines), cursor position/style, field attributes, alternate glyph page, and end-of-row/screen controls. TOS/M programs 80×24×12, producing 640×288 pixels. Rendering remains separate from raster/DMA timing.

Build `make`, then:

```sh
build/robotron-boot /path/s550.bin /path/cas.bin /path/robotron.img 100000000 $'DIR\r'
```

`--writable` enables only an in-memory disk copy. Add `--export /path/new-session.img` to save that copy to a **new** file. Input files and existing output files are never overwritten. The native scripted runner allows eight emulated seconds after Enter/EOF so the following command does not race a disk operation. `DAC_TRACE_IO=1` logs I/O writes. Convert an external CAS hex file with `python3 tools/prepare_robotron_media.py 287.hex cas.bin`.

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
- Only one drive and one explicit raw geometry. Reset interrupt queues, multi-track head switching, format commands, deleted-sector/error metadata and detailed scan semantics remain incomplete. Whole/partial write completion, write protection, busy/data/result transitions and reset cancellation have focused checks.
- CTC external trigger timing, SIO synchronous modes, TX, other serial channels, printer and V.24 are pending. The keyboard receiver implements asynchronous width/parity/clock division, three-byte FIFO, error status and receive interrupts; it is not a complete SIO.
- The 8275 stream renderer does not implement scan timing, real display DMA/FIFO limits, raster interrupts, double-spaced rows, light pen or character-attribute line graphics. Blink uses a nominal 50 Hz clock; unusual geometries are bounded to the supported framebuffer. Field attributes and cursor are not a claim of complete 8275 emulation.
- No MAME runtime differential or physical-machine comparison has been performed. Source comparisons and passing applications do not prove hardware accuracy.

See [source identities](../../docs/z80-provenance.json), [validation](../../docs/z80-browser-validation.md) and `REFERENCE_LICENSE`. Original DAC code is MIT; reference attributions are preserved in `NOTICE`. ROMs and disks are neither bundled nor licensed by this repository.

## Keyboard firmware, floppy timing and session state (2026-10-10)

With optional firmware slot 3, the K7658 U880 runs the unpatched 2 KB S600 ROM at a nominal 683 kHz alongside the 3.9936 MHz main CPU. Its 13×8 switch matrix, mirrored ROM, LED flip-flops and D0 serial strobes follow [Zander’s schematic](https://www.sax.de/~zander/pc1715/pc_tasts.pdf), cross-checked against the pinned MAME source. The RC oscillator is approximated by that nominal frequency. There is no keyboard RAM. The Zander drawing specifies U556/U2716; another kbdbabel board drawing shows a 2732 arrangement. Neither establishes the chip inside Danila’s specimen.

`dac_matrix` holds/releases a switch; `dac_tap` queues a bounded 60 ms press and 40 ms release with optional Shift/Ctrl contacts. The firmware performs scanning, encoding and repeat behavior. In particular Ctrl+A emits a modifier header followed by `a`; the BIOS interprets it. No firmware patch turns it into an ASCII shortcut. S600’s layout can differ from the specimen’s printed shifted legends. Without slot 3, `dac_key` retains the existing character adapter. With it loaded, character injection is rejected; release-all remains supported.

```sh
make build/robotron-keyboard-rom-test
build/robotron-keyboard-rom-test /path/s600.bin
```

The FDC now schedules seek completion from SPECIFY’s step-rate field, exposes seek-busy bits and senses completed seeks. Read/write execution uses ideal 300 RPM rotation with five evenly spaced sector positions and 250 kbit/s byte pacing. Sense/Read-ID reject absent drive B. Wrong-cylinder reads require a seek. Terminal-count next-ID reporting no longer moves the physical head. Drive motor register bits, selected unit, transfer state, write protection and cylinder are exposed to the browser. Spin-up, head-load delay, flux/gap layout, index pulse and realistic mechanical sounds are still unmodeled; the timing is a bounded approximation, not a drive qualification.

The additive browser ABI exposes internal Robotron state save/load. It includes both CPUs, keyboard contacts/tap queue/LEDs, RAM/video/glyph memory, SIO, timers, DMA, floppy state and disk bytes. Pointers are removed and rebound on restore. The header, CRC, sizes, firmware, write mode and internal bounds are checked before mutation. These are **same-build internal snapshots**, not a portable save-file format; the museum additionally keys them by the WASM hash. Juku/VJUGA machine snapshots are not implemented. Browser disk persistence is managed by DAC, outside the portable core.
