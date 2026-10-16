# Current Robotron emulation status

Baseline: **0.15.1**, snapshot layout **13**, ABI **1**. This page supersedes
present-tense summaries in dated bring-up notes. Hardware fidelity is bounded;
the reference S550/CAS/S600/TOS-M configuration is not an identified owner dump.

Implemented: banked 256 KiB memory; Z80 DMA with timed read/write phases and bus
ownership; scanline display with scheduled byte fetches and attributes; S600
keyboard CPU/matrix/serial input; two timed floppy drives and writable raw/DSK
media; asynchronous SIO, printer readiness, serial transfers; deterministic
snapshots, observation and replay. See the museum's
[capability matrix](https://github.com/ddanila/dac/blob/main/docs/robotron/capabilities.md) for the browser tools.

0.15.1 fixes asynchronous SIO receive data for 5–7-bit characters on both
channels. The data register retains the sampled parity bit when enabled and
fills unused high bits with ones. For example, 7E1 reception of data `61h` with
parity one produces `E1h`, not `61h`. BREAK detection still examines the actual
data bits. No state fields, snapshot layout, clock route or oscillator changed.
Reference: [Zilog UM008101](https://www.zilog.com/docs/z80/um0081.pdf), printed
pp.235–236. The previous implementation stripped these bits; an independent
S600/MAME parity-mismatch probe exposed the difference.

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
python3 tools/compare_robotron_serial.py --media /path/to/media --output build/serial.json
```

The historical comparison boots both implementations, drives the same S600
switch coordinates, compares text and monochrome rasters at boot and four
command checkpoints, and independently decodes a 10 KiB PIP.COM copied to B.
Colours and the final blinking cursor cell are excluded from raster comparison.
Fixed execution bounds allow settling; CPU clocks, interrupts and disk timing
are not asserted equal. Input ROM/disk hashes and differences are retained in
JSON. The serial probe compares 8N1 and deliberately mismatched 7E1 receiver
data/status, without stripping unused bits to hide differences. MAME is an
independent implementation, not a hardware oracle.

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
