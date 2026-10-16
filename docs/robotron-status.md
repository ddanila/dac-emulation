# Current Robotron emulation status

Baseline: **0.17.0**, snapshot layout **15**, ABI **1**. This page supersedes
present-tense summaries in dated bring-up notes. Hardware fidelity is bounded;
the reference S550/CAS/S600/TOS-M configuration is not an identified owner dump.

Implemented: banked 256 KiB memory; Z80 DMA with timed read/write phases and bus
ownership; scanline display with scheduled byte fetches and attributes; S600
keyboard CPU/matrix/serial input; two timed floppy drives and writable raw/DSK
media; asynchronous SIO, printer readiness, serial transfers; deterministic
snapshots, observation and replay. See the museum's
[capability matrix](https://github.com/ddanila/dac/blob/main/docs/robotron/capabilities.md) for the browser tools.

0.17.0 corrects keyboard decoding against the KiCad-derived reference HDL:
all I/O cycles clock raw LED latches, A15 enables matrix input, selected contacts
combine with OR, and WR clocks serial output for memory as well as I/O writes.
The 131,072-vector audit and independent TV80/S600 logical comparison pass.
Display indicators have an explicit 2 ms peak hold; raw latches are separately
observable. Snapshot layout 15 includes this display state. CPU-clock offsets,
analog timing, physical copper and specimen identity remain separately unqualified.
See [board qualification](../verification/robotron-keyboard/README.md).

0.16.0 gives both SIO receivers per-character error FIFOs. Framing errors follow
characters; parity/overrun latch when the affected character reaches the FIFO
head. A fourth character replaces the third. First-character error lock/reset and
special receive vectors now use the same rules on both channels. A sampled high
parity bit prevents false V.24 BREAK; x16/x32/x64 framing errors add half-bit
recovery. The x1 path still has no half-clock sampling resolution.
Reference: [Zilog UM008101](https://www.zilog.com/docs/z80/um0081.pdf), printed
pp.235–237. Layout 14 includes the receive error buffers and sampled parity;
layout 13 requires the preserved 0.15.1 core. ABI remains 1.

0.15.1's short-character fix remains: 5–7-bit reception retains sampled parity
and fills unused high bits with ones (7E1 data `61h`, parity one reads `E1h`).

## Reproduce qualification

Fast checks require no historical firmware, MAME or HDL:

```sh
make test test-runtime-sanitize
make test-wasm  # requires the pinned Emscripten toolchain
```

Native device tests cover both receive channels, all four clock divisors,
5/6/7/8-bit words, no/odd/even parity, both parity bit values, and short-word
BREAK. The WASM fixture saves during 7E1 reception, then compares its received
register after batched and single-clock continuation.

Optional qualification uses local caller-supplied media:

```sh
make test-s600-workload S600_ROM=/path/to/s600.bin
python3 tools/compare_robotron_mame.py --media /path/to/media --output build/mame.json
python3 tools/compare_robotron_historical.py --media /path/to/media --output build/historical.json
python3 tools/compare_robotron_historical.py --suite wordstar --media /path/to/media --output build/wordstar.json
python3 tools/compare_robotron_historical.py --suite pascal --media /path/to/media --output build/pascal.json
python3 tools/compare_robotron_serial.py --media /path/to/media --output build/serial.json
```

The basic historical comparison boots both implementations, drives the same S600
switch coordinates, compares text and monochrome rasters at boot and five command
checkpoints, independently decodes a 10 KiB PIP.COM copied to B, and checks printer
bytes from AUTOEXC.SUB. Application suites compare WordStar create/save/reopen and
Turbo Pascal source creation/compile/run, including exact saved file contents.
They compare full text screens; application raster differences are retained but
not pass criteria. The basic raster check excludes only the final prompt cursor.
Each tool uses temporary media copies; supplied historical files remain unchanged.

The serial probe compares seven S600 observations: 8N1, deliberately mismatched
7E1, and FIFO overrun data/status. MAME 0.289 agrees, including the delayed overrun
flag on the third buffered character. MAME is an independent implementation, not
a hardware oracle. Reports record input hashes, core identity and limits.

Native fault tests additionally interrupt writes after 1, 128 and 255 bytes through
motor loss, controller reset and drive-door opening. They assert the written
prefix, bad CRC metadata, unchanged remainder and untouched other drive. Formatting
interruptions and the S600/DMA/printer/V.24 snapshot workload also pass. These fault
and overlap cases are native regression checks, not independent MAME comparisons.

## Evidence still needed

Display DACK latency, dot-level CPU contention, IRQ routing, DMA half-clock
arbitration, CTC waveform duty cycle and SIO x1 half-stop timing need more specific
evidence. Existing explicit-clock fixtures qualify an ideal diagnostic waveform;
they do not justify changing the museum's CTC route. Synchronous serial modes,
flux/PLL and weak-sector support are absent. Drive trajectories are a documented
reference profile; see [drive fidelity](../machines/robotron1715m/DRIVE-FIDELITY.md).

ROM/PROM dumps, board straps, drive suffixes/jumpers and clock/logic captures from
the actual specimen remain necessary. More software agreement cannot establish
these facts. The museum inventory tool records supplied hashes and provenance
without promoting reference media to specimen evidence.
