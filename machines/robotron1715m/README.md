# Robotron 1715M / PC-1715W functional profile

An experimental portable C machine using the shared Z80 adapter. The tested profile is the S550 boot ROM, 287 CAS PROM and TOS/M 1.0 disk decoded from `A92V010A.TD0`. It cold-boots to `A>`, accepts keyboard packets, creates/reads/copies/deletes files and reboots from an exported session disk. No guest ROM patches or guest-PC traps are used. Matching Danila's exact physical machine is still pending.

Implemented: 256 KB RAM with independent read/write banks selected through the supplied CAS PROM; boot ROM/gap/character/video windows; CTC timer cascade and DMA/CTC interrupt priority with in-service/RETI handling; optional S600 keyboard CPU/matrix with clocked SIO reception, or a legacy byte adapter; DMA addressing, ready polarity, end-of-block interrupt control and board-gated terminal count; raw 80×2×5×1024 media; floppy specify/sense/recalibrate/seek/read-ID/read/write/deleted-data/read-track/format/scan commands. Storage uses `common/media`. Native I/O events use `common/trace`.

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
- Two drives share one explicit raw geometry. Format accepts exactly five unique 1024-byte sector IDs on the current cylinder/head; arbitrary layouts, deleted-sector/flux-level behavior and detailed scan semantics remain incomplete. Whole/partial write completion, write protection, busy/data/result transitions and reset cancellation have focused checks.
- CTC external trigger timing, SIO synchronous modes, other serial channels and V.24 are pending. Printer TX A supports an always-ready byte-capture device clocked by CTC0 channel 0. The keyboard receiver implements asynchronous width/parity/clock division, three-byte FIFO, error status and receive interrupts; it is not a complete SIO.
- The 8275 stream renderer does not implement scan timing, real display DMA/FIFO limits, raster interrupts, double-spaced rows, light pen or external LA0/LA1 graphics wiring. Character attributes now decode VSP/LTEN and highlight/blink, retaining the reference Robotron glyph wiring. Blink uses a nominal 50 Hz clock; unusual geometries are bounded to the supported framebuffer. Field attributes and cursor are not a claim of complete 8275 emulation.
- No MAME runtime differential or physical-machine comparison has been performed. Source comparisons and passing applications do not prove hardware accuracy.

See [source identities](../../docs/z80-provenance.json), [validation](../../docs/z80-browser-validation.md) and `REFERENCE_LICENSE`. Original DAC code is MIT; reference attributions are preserved in `NOTICE`. ROMs and disks are neither bundled nor licensed by this repository.

## Keyboard firmware, floppy timing and session state (2026-10-10)

With optional firmware slot 3, the K7658 U880 runs the unpatched 2 KB S600 ROM at a nominal 683 kHz alongside the 3.9936 MHz main CPU. Its 13×8 switch matrix, mirrored ROM, LED flip-flops and D0 serial strobes follow [Zander’s schematic](https://www.sax.de/~zander/pc1715/pc_tasts.pdf), cross-checked against the pinned MAME source. The RC oscillator is approximated by that nominal frequency. There is no keyboard RAM. The Zander drawing specifies U556/U2716; another kbdbabel board drawing shows a 2732 arrangement. Neither establishes the chip inside Danila’s specimen.

`dac_matrix` holds/releases a switch; `dac_tap` queues a bounded 60 ms press and 40 ms release with optional Shift/Ctrl contacts. The firmware performs scanning, encoding and repeat behavior. In particular Ctrl+A emits a modifier header followed by `a`; the BIOS interprets it. No firmware patch turns it into an ASCII shortcut. S600’s layout can differ from the specimen’s printed shifted legends. Without slot 3, `dac_key` retains the existing character adapter. With it loaded, character injection is rejected; release-all remains supported.

```sh
make build/robotron-keyboard-rom-test
build/robotron-keyboard-rom-test /path/s600.bin
```

The FDC now uses independent drive phase/index signals for Read-ID and sector searches, exact rational 250 kbit/s byte cadence, DMA overrun detection, and READY-based termination. The reference mechanical profile models startup/coast, head load/unload, per-step movement and settling; recalibration is limited to 77 pulses. Standard/extended DSK images preserve supported track order and metadata alongside raw-image support. See [drive fidelity](DRIVE-FIDELITY.md) for the supported subset, assumptions and validation.

The additive browser ABI exposes internal Robotron state save/load. It includes both CPUs, keyboard contacts/tap queue/LEDs, RAM/video/glyph memory, SIO, timers, DMA, floppy state and disk bytes. Pointers are removed and rebound on restore. The header, CRC, sizes, firmware, write mode and internal bounds are checked before mutation. These are **same-build internal snapshots**, not a portable save-file format; the museum additionally keys them by the WASM hash. Juku/VJUGA snapshots are also implemented; see the extension below. Browser disk persistence is managed by DAC, outside the portable core.


## Two drives, printer and application coverage (0.3.0)

Both drive units have independent media, write protection and physical cylinders.
`robotron_disk_unit` / `dac_mount_unit` mount units 0/1; a zero-length browser
mount ejects. The native API rejects replacement during a transfer, result phase
or seek. The museum requires power-off for media changes. Existing single-drive
APIs remain aliases for unit 0. Motor/transfer/presence/protection/seek/cylinder
status is available per unit through `dac_drive_status_unit`.

FDC reset release queues four Sense Interrupt responses. Multi-track reads/writes
cross side 0 EOT to side 1 without moving the physical cylinder. Format Track
validates the complete C/H/R/N list before writing fill bytes. Unsupported geometry
and protected media fail explicitly; the raw format does not retain gaps or custom
ID order. Motor spin-up and head-load delays remain unmodeled.

SIO A transmission has a holding register, a shift register, programmed character
width/stop/parity length and clock division, and TX-empty/all-sent polling status.
CTC0 channel 0 clocks it; completed bytes go to a bounded 64 KB virtual-printer
capture. This is an always-ready sink, without cable waveforms, printer rendering
or TX interrupts. Overflow is explicit; export preserves original control bytes.

Snapshot headers changed with the core build. Both disk payloads and protection
modes participate in Robotron state. Juku snapshots preserve CPU/RAM/devices,
keyboard and disk metadata; VJUGA snapshots preserve its current CPU/memory/ports
profile. Host callbacks are removed and rebound from fresh core code. CRC, sizes,
firmware and indexing bounds are checked before replacing the current session.
These remain same-build snapshots, not a cross-version archival file format.

Run the optional real-application checks against the already documented TOS/M disk:

```sh
python3 tests/integration/robotron_applications.py s550.bin cas.bin tosm10.img
```

The bounded cases copy PIP.COM between drives and independently compare bytes,
capture `PIP LST:=AUTOEXC.SUB`, create/save a WordStar document, and compile/run a
small Turbo Pascal program. Input images remain untouched. This is functional
coverage of these paths, not qualification of every application feature.

## Serial transmitter interrupts (2026-10-11)

Channel A now latches a transmit interrupt when its holding register empties,
respects WR1 enable, supplies the channel-A TX vector, and acknowledges WR0
reset-TX-pending and return-from-interrupt commands. RX has priority over TX;
DMA/CTC retain priority over the SIO. Loading another byte clears TX pending.
Focused tests cover nesting, vectors, servicing, reset and printing.
This is the asynchronous printer channel, not a full SIO implementation.
Reference: [Zilog Z80-SIO Technical Manual](https://www.hartetechnologies.com/manuals/Zilog/Zilog%20Z80-SIO%20Technical%20Manual.pdf),
transmit interrupts and WR0/WR1. Robotron internal state version is now 3.


### Keyboard indicator latch correction

The Zander 56-330-4103-7 drawing connects A6A/A6B (DL074) D inputs to A14/A13,
with an IORQ-derived clock enabled when A15 is low. An I/O cycle latches those
address bits: 0000 turns both off, 2000 selects SI/SO, 4000 Caps, and 6000 both.
Repeated reads preserve the state. Matrix reads with A15 high do not change it.
This corrects the previous MAME-derived toggle interpretation, which made S600
scan cycles produce continuous LED chatter and failed to represent both lamps.
The original ROM remains unmodified. Tiny original-ROM/device checks cover the
address combinations; the optional S600 test checks stable states across idle
scans and sequential Caps/SI/SO key presses. No state-structure or ABI change.

### Drawing audit, 2026-10-14

The original [W drawings](https://xepb.org/robotron/docs/1715w.zip)
(1.93.310411.8/09 and CRT 1.93.310412.6/04) distinguish the motherboard
UA858/floppy DMA from the display board's local counter/RAM/multiplexer fetch
circuitry. No system-DMA shortcut has been introduced for video.

The [Intel 8275 datasheet](https://www.emuverse.ru/downloads/datasheets/peripherals/display/8275/8275.pdf),
printed pp. 8-237 and 8-241, establishes the fixes in this release:

- The byte following an invisible field attribute is seven-bit glyph data,
  even if its original high bit would have denoted another attribute or command.
- Character attributes inherit field reverse-video and GPA, but supply their
  own highlight/blink state.
- Reading status clears IR/LP/IC/DU/FO while preserving IE/VE. Excess or
  interrupted parameter strings set IC.

Focused pixel/register tests cover these cases. This does not implement the
16-byte FIFO's overflow/overwrite behavior, row-fetch scheduling, underruns,
light pen or exact raster/interrupt timing. The renderer still reads the bounded
video stream directly; status-bit clearing does not imply every flag producer
is implemented. Keyboard S600 testing additionally checks normal output after
releasing Shift and Ctrl; its existing address-clocked LED latches agree with
the keyboard drawing. The transplanted specimen keyboard ROM is not identified
by this reference-firmware test. No Verilog run is needed for these C changes.
