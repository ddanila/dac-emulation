# Juku digital video investigation

The portable core clocks D54/D55 rather than recognizing ROM-specific write
sequences. `juku_frame()` exposes the last completed packed monochrome frame;
`juku_video()` remains a bounded view of live video RAM. Runtime and native
video capture consume completed frames. Historical media are external inputs.

The investigation targets [juku3000 issue 17](https://github.com/infoaed/juku3000/issues/17).
Current measured results, media provenance, and outstanding acceptance criteria
are in [results.json](results.json). Monitor 3.3 geometry is measured separately from its pre-existing missing
header in the native core; no full monitor-display equivalence is claimed.
FEDITOR acceptance remains open until an
intact executable and its required font files are available and exercised.

## Timing contract

D40 supplies a 1 MHz clock to all D54 counters. D54.OUT0 drives D54.GATE1/2
and D55.CLK0. D55.OUT0 drives D55.GATE1/2. D54.OUT2 triggers D56.Q2;
the resulting falling edge of Q2_N clocks D55 counters 1 and 2. Retriggering
the 5.04 us one-shot extends the pulse without inventing another clock edge.
The inverted D55.OUT1 edge latches IR5; delivery respects the PIC mask, CPU
interrupt enable and EI delay. Keyboard sampling follows frame edges even
while IRQ delivery is inhibited.

Control words select binary/BCD counting, access width and mode. Writes to
running periodic counters take effect on reload; mode-1 retriggering loads on
the following clock. Partial writes cannot install a new divisor. Latches
hold a captured counting element until consumed. D57's existing baud/serial
implementation is separate and unchanged.

Stock binary vertical count `0139` gives 313 lines; BCD `0312` in Monitor 3.3
gives 312 lines. Subtracting the BCD 72-line blanking interval gives 241 and
240 visible lines respectively. MODX programs horizontal blanking `14` and
vertical blanking `011A`; the current counter model interprets the latter as
120 clocks and acquires 400 × 193 rather than forcing the old 400 × 192 crop.
`A` is not a valid BCD digit: this interpretation needs a physical 8253 check
before claiming exact undocumented behavior (especially immediate readback).

MAME 0.289's `screen_height` directly combines
the bytes as binary, unlike its vertical blanking helper. Its interpretation
of `0312` is therefore 786 total / 714 active lines.

CPU accesses remain instruction-granular. Digital counter edges run at their
own timestamps; drawing samples one byte per active 1 MHz interval before
subsequent guest writes. Completed frames are published without blank-frame
insertion or a mode-switch debounce. Storage clips scanout to 640 × 384;
clipping does not change the guest counters or interrupt rate.

The active-byte address walk starts at D800 and wraps at 16 bits. This retains
the functional framebuffer mapping; **the physical D44–D47 preset/load network
and porch-dependent addressing are not yet validated**. Full DRAM contention,
serializer/analog voltage and monitor acquisition are also outside this model.
Consequently this is not a claim that every unusual video program now matches
physical hardware. The existing HDL address/slot audit has open boundaries;
its timing model is a period/wiring cross-check, not a complete pixel oracle.

## Reproduce

From the repository root:

```sh
make test-juku-video build/juku-video-capture
mkdir -p /tmp/juku-video
build/juku-video-capture ../8080-cosim/roms/jmon33.bin - /tmp/juku-video/jmon33 '' 10000000
build/juku-video-capture ../8080-cosim/roms/ekta37.bin /path/to/prog1.juk /tmp/juku-video/ekdos 'TDD|' 30000000
node verification/juku-video/wasm_capture.mjs ../8080-cosim/roms/jmon33.bin /tmp/juku-video/wasm33 10000000
```

Build WASM with `make test-wasm` first (Emscripten must be on PATH). The native
capture writes every completed PBM frame, a frame index, cycle-stamped timer
writes/interrupt acknowledgements, nanosecond counter edges, and a JSON summary.
Signal numbers 0–2 are D54.OUT0–2; 3–5 are D55.OUT0–2. Bus timestamps have CPU
instruction resolution. No firmware is patched and disks are read-only.
The `KEYS` argument uses the existing native keyboard notation: `|` waits for
the EKDOS prompt; pass an actual carriage return for a command terminator.

For MAME, arrange the ROMs under `/path/to/roms/juku/`, then run from a scratch
directory so its configuration and NVRAM stay outside the checkout:

```sh
JUKU_CAPTURE_PREFIX=/tmp/juku-video/mame33 SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
 mame juku -bios jmon3.3 -rompath /path/to/roms -video none -sound none \
 -nothrottle -seconds_to_run 5 -skip_gameinfo -noreadconfig \
 -autoboot_delay 0 -autoboot_script /absolute/path/to/verification/juku-video/mame_capture.lua
```

This produces a PNG and dimensions at frame 150. Inspect the entire captured
image: a successful process exit alone does not establish correct rendering.
Native tests cover unrecognized geometry, alternate write order, BCD/binary,
reload and latch behavior, frame publication, clock chunking and IRQ delay.
Runtime and WASM tests restore snapshots through active video timing. Old Juku
snapshots are rejected by version; the external runtime API is unchanged.

Synthetic `frame_cyc` in the internal legacy harness remains an explicit test
injection. Use zero for normal hardware-driven timing. It must not be used to
claim video-timing correctness. Bulk captures and downloaded media stay out of Git.
