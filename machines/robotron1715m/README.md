# Robotron 1715M / PC-1715W functional profile

An experimental portable C machine using the shared Z80 adapter. The tested profile is the S550 boot ROM, 287 CAS PROM and TOS/M 1.0 disk decoded from `A92V010A.TD0`. It cold-boots to `A>`, accepts keyboard packets, creates/reads/copies/deletes files and reboots from an exported session disk. No guest ROM patches or guest-PC traps are used. Matching Danila's exact physical machine is still pending.

Implemented: 256 KB RAM with independent read/write banks selected through the supplied CAS PROM; boot ROM/gap/character/video windows; CTC timer cascade and DMA/CTC interrupt priority with in-service/RETI handling; optional S600 keyboard CPU/matrix with clocked SIO reception, or a legacy byte adapter; DMA addressing, ready polarity, end-of-block interrupt control and board-gated terminal count; raw 80×2×5×1024 media; floppy specify/sense/recalibrate/seek/read-ID/read/write/deleted-data/read-track/format/scan commands. Storage uses `common/media`. Native I/O events use `common/trace`.

The bounded 8275 renderer honors display start/stop, programmed geometry (up to 80×24 cells and 16 scanlines), cursor position/style, field attributes, alternate glyph page, and end-of-row/screen controls. TOS/M programs 80×24×12, producing 640×288 pixels. The row scheduler produces status independently of rendering; local fetch response remains idealized.

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

## Historical limitations at initial bring-up

This list predates the updates below. For the current display implementation see
“Scanline output — 0.8.8”; for storage see DRIVE-FIDELITY.md. The museum maintains
a current [capability matrix](https://github.com/ddanila/dac/blob/main/docs/robotron/capabilities.md).

### Initial limitations

- Functional, not cycle-accurate: DMA byte/burst timing, search/match/ready interrupts, auto-restart, pulse output and six-command reset sequencing remain incomplete. End-of-block interrupt/TC, ready polarity and DMA/CTC in-service priority have focused tests; this does not qualify all peripheral modes.
- Two drives share one explicit raw geometry. Format accepts exactly five unique 1024-byte sector IDs on the current cylinder/head; arbitrary layouts, deleted-sector/flux-level behavior and detailed scan semantics remain incomplete. Whole/partial write completion, write protection, busy/data/result transitions and reset cancellation have focused checks.
- CTC external trigger timing, SIO synchronous modes, other serial channels and V.24 are pending. Printer TX A supports an always-ready byte-capture device clocked by CTC0 channel 0. The keyboard receiver implements asynchronous width/parity/clock division, three-byte FIFO, error status and receive interrupts; it is not a complete SIO.
- The 8275 has a functional character-clock/row scheduler, burst spacing, stop-DMA consumption, underrun and raster IR status. It does not reproduce per-byte board response, CPU interrupt wiring, double-spaced pixel rows, light pen or external LA0/LA1 graphics wiring. Character attributes now decode VSP/LTEN and highlight/blink, retaining the reference Robotron glyph wiring. Blink follows the scheduled frame counter; unusual geometries are bounded to the supported framebuffer. Field attributes and cursor are not a claim of complete 8275 emulation.
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

Focused pixel/register tests cover these cases. Historically, 0.8.3 did not yet implement the
16-byte FIFO's overflow/overwrite behavior, row-fetch scheduling, underruns,
light pen or exact raster/interrupt timing. The renderer still reads the bounded
video stream directly; status-bit clearing does not imply every flag producer
is implemented. Keyboard S600 testing additionally checks normal output after
releasing Shift and Ctrl; its existing address-clocked LED latches agree with
the keyboard drawing. The transplanted specimen keyboard ROM is not identified
by this reference-firmware test. No Verilog run is needed for these C changes.


### Attribute FIFO — 0.8.4

Each decoded row now has an 80-byte bounded row buffer and a 16 × 7-bit
attribute FIFO. The entire row is filled before display: the 17th following
character overwrites slot zero, the 33rd overwrites it again, and output wraps
through the same 16 slots. FIFO indices reset for each row. Visible attributes
do not use the FIFO. Tests cover counts 16 through 33, seven-bit data, row
boundaries, pixel output and status read-clear behavior.

In 0.8.4, FO was latched by emulation on the nominal 80000-tick display-frame
cadence, even when no host renderer is called. Rendering never mutates status;
small and large run slices produce the same flag. This is a functional FIFO
model, not cycle-accurate row DMA: exact FO latency, burst/stop-DMA consumption,
underruns, light pen, spaced rows and raster IRQ timing remain separate work.
The shared FIFO decoder follows Intel 8275 pp. 8-236–8-237; FIFO width/wrapping
was also cross-checked against MAME's BSD-3-Clause i8275 implementation (Curt
Coder/AJR, already credited in NOTICE). No persistent state layout was changed.

### Functional display scheduler — 0.8.5

The 8275 now advances on a rational character clock (45/104 of the existing
3.9936 MHz CPU clock). The nominal 13.824 MHz / 8 display clock comes from the
PC1715 family reference; it is **not a measured W/M specimen clock**. Programmed
characters, horizontal retrace, scanlines, spaced-row timing and vertical
retrace determine row/frame boundaries. Host drawing never advances counters.

Rows prefill during the preceding row, with the first row prefilling during
final vertical retrace. Burst lengths and gaps control completion time. End-row
and end-screen stop-DMA codes stop consumption, including the documented dummy
byte when a stop lands inside a burst. A missed deadline sets DU and blanks the
remaining frame; status reads clear DU without prematurely unblanking it.
FO is latched on row-fill completion. IR is set at the last visible row when IE
is enabled, including read-clear behavior. Preset counters holds the scheduler
until another command; Stop Display stops fetching but retains raster timing.

This remains a functional approximation: bytes are sampled at row-fetch start,
one local DACK per character clock is assumed. Per-byte FO latency,
contention, scanline-accurate tearing and exact board delays are not reproduced. IR is
exposed as controller status; no unverified CPU interrupt connection is added.
Spaced-row timing is supported; doubled blank pixel rows and light pen are not.
The display controller never uses the system UA858 floppy DMA.

Sources: [Intel 8275](https://www.emuverse.ru/downloads/datasheets/peripherals/display/8275/8275.pdf),
printed pp. 8-236, 8-239–8-241, and the [family service manual](https://xepb.org/robotron/docs/pc_serv.pdf).
Tests cover row deadlines, burst/dummy consumption, FO, DU recovery, IR masking,
read-clear, preset, host-render independence and run-slice equivalence.

The raw Robotron snapshot layout is version 4 because it now contains scheduler
phase and pending fetch state. DAC preserves the 0.8.4 core for its older saved
sessions; old snapshots are not silently interpreted using the new layout.

### Latched scanout — 0.8.6

Completed pending fetches are latched at visible-row boundaries. Host drawing
uses those historical rows and their starting field/end-screen state, never
current VRAM. A write after fetch start becomes visible on a subsequent fetch;
rows that have not yet been scanned are blank after Start Display. Missed
fetch deadlines latch blank rows. This is row-level sampling, not a claim of
per-byte DMA or measured board timing. Cursor and character-generator output
remain evaluated at host drawing time.

Tests exercise writes between fetch and scanout, blank initial rows, unchanged
host-render state, attribute FIFO behavior, deadlines and subsequent refresh.
Native and WASM historical TOS/M boot pixels remain identical. Snapshot layout
is now **5**, retaining pending and displayed rows plus attribute state; DAC
archives core 0.8.5 for saved sessions using its previous layout.

### Scheduled byte fetches and retained output — 0.8.7

The display now reads one byte at each idealized local DACK, with the programmed
burst lengths and 0/7/15/…/55 character-clock gaps. Start Display itself does not
read VRAM. Invisible-attribute data and stop-DMA dummy reads each consume their
own fetch. FO appears on the seventeenth FIFO write. Writes between fetches can
therefore affect unfetched bytes without changing bytes already in the buffer.

At each visible-row boundary the completed row retains its decoded glyph bits,
highlight, cursor, blink, and controller attributes. Host drawing no longer
re-evaluates old rows with changed character ROM, cursor or attribute registers.
Snapshot layout **6** retains partial fetch phase, FIFO index, burst wait, pending
bytes and decoded rows. Active fetch state is bounded during snapshot validation.
DAC preserves core 0.8.6 for previous saved sessions.

This still assumes one local acknowledgement per character clock and samples
scanout state per row. It does not claim measured W/M DACK latency, CPU bus
contention, individual scanline output, light-pen behavior or verified IRQ wiring.
Tests cover writes between DACKs, burst gaps, independent FIFO bytes, retained
glyph/cursor output, dummy reads, underruns, snapshots, and native/WASM TOS/M boot.
The burst/stop/FIFO rules use the existing Intel 8275 source, pp. 8-236–8-240.

### Scanline output — 0.8.8 (current)

Fetched character rows remain buffered, but glyph-ROM, cursor and attribute
output is now sampled at each scanline boundary. Lines already emitted retain
their pixels and intensity while later lines can reflect a register change.
A new frame replaces old output progressively; Start Display clears retained
output. Spaced rows do not emit extra glyph lines during the spacing interval.
Host rendering remains read-only. Horizontal dot timing, measured DACK latency,
CPU contention and unverified board IRQ wiring remain outside this model.

Snapshot layout **7** preserves per-line intensity and partially refreshed rows;
restore validates row dimensions and intensity values. DAC archives 0.8.7.
Focused tests change glyphs and cursor between scanlines, check the exact line
boundary, resume mid-line deterministically and verify restart blanking. Existing
FIFO, underrun, row-buffer and native/WASM parity tests remain in place.
Timing basis: Intel 8275 horizontal/vertical formats, the same datasheet linked
above; nominal family clock is unchanged and is not a specimen measurement.

## DMA bus phases and matrix audit (0.8.9)

Sequential transfers now latch a byte at the end of a read cycle and commit it
at the end of a distinct write cycle. Default memory cycles take three clocks;
I/O cycles take four. WR1/WR2 timing bytes select four, three or two clocks per
port. RDY gates the start of a byte, so deasserting DRQ after a source read does
not discard the pending write. CPU execution pauses across both phases.

Timing basis: [Zilog Z80 CPU Peripherals User Manual, UM008101-0601](https://www.zilog.com/docs/z80/um0081.pdf),
printed pp.96–98 and 153 (PDF pp.114–116 and 171). Reserved cycle encoding 11
uses four clocks defensively. Half-clock pin edges, external WAIT, exact
BUSREQ/BUSACK arbitration, simultaneous/search modes and unimplemented reset
commands remain limitations. This is improved sequential timing, not a claim of
complete pin-level DMA fidelity.

Snapshot layout **8** includes phase, countdown and latched data. A public-runtime
test saves after a DMA read and compares every subsequent snapshot through the
write. Preserve 0.8.8 for older portable sessions. Focused tests cover all three
programmable lengths, RDY dropping after a read, CPU pause, FDC completion and
terminal count. Bounded TOS/M PIP, WordStar and Turbo Pascal checks pass, as does
native/WASM historical framebuffer parity.

`build/robotron-keyboard-rom-test s600.bin --audit` emits all 104 matrix positions
under four modifier states (416 cases). Normal mode also checks overlapping-key
release and observes held A for two seconds. The emitted report is a ROM behavior
record, not an independent oracle or identification of the specimen EPROM.
