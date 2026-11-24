# Juku smooth-scrolling investigation

This opt-in comparison targets [issue #20](https://github.com/infoaed/juku3000/issues/20)
with unmodified EKTA #0037 firmware and EKDOS 2.30 on the public `prog1.juk`.
Measured outcomes, input provenance, and limitations are in [results.json](results.json).
Historical ROMs/disks and generated captures are external inputs, not vendored here.

## What the comparison distinguishes

An escape sequence sent **to console output** is different from the same keys
entered at the EKDOS command prompt. The monitor's `E` command provides a direct
echo path. The diagnostic `SCROLL.COM` emits control sequences using BDOS
function 2; it switches smooth/normal/smooth/normal and prints three sets of
60 numbered lines. It returns through the normal warm-boot entry.

The relevant observation points for these particular firmware/media versions are:

| Address | Meaning |
| --- | --- |
| ROM `0DEE`, `0DF7` | Set/clear bit 0 of `D499` for `ESC :` / `ESC ;` |
| ROM `1076` | Software framebuffer scroll, with one-row or ten-row copying |
| `D9DF`, `DCD1` | Console input return in A / output character in E |
| EKDOS `B690` | Accept the character before `:` as a drive designator |
| EKDOS `CD71–CD74` | `MOV A,C; CPI 03; RP` drive-range check |
| EKDOS `CD83` | Index the disk parameter headers |

These are observation points only. The harness does not patch ROM, change
registers, inject console bytes, or recognize these PCs inside the emulator.
Different firmware versions require locating their own observation points.

## Reproduce

Requirements: C compiler, Python 3 with Pillow, MAME 0.289, and an existing MAME
`roms/juku/` ROM set. From the repository root:

```sh
python3 verification/juku-scroll/test_tools.py
python3 verification/juku-scroll/run.py \
  --rom ../8080-cosim/roms/ekta37.bin \
  --disk /path/to/prog1.juk \
  --roms /path/to/mame/roms \
  --mame /path/to/mame \
  --output /tmp/juku-scroll-comparison
python3 verification/juku-scroll/analyze.py \
  /tmp/juku-scroll-comparison ../8080-cosim/roms/ekta37.bin \
  /tmp/juku-scroll-comparison/analysis.json
```

The output directory must be new. Native disks are read-only memory devices;
MAME gets a separate read-only filesystem copy in each case directory. Media
preparation preserves allocated files, adds the generated diagnostic in one
free 4096-byte block, and refuses to replace the source. It assumes EKDOS's
DS/DD geometry, two reserved logical tracks, 128 directory entries, 4096-byte
blocks, outout sides, and the documented sector skew. It is not a general disk
image editor.

Each schedule row is `milliseconds hexadecimal-key down`, with `00 0` releasing
all contacts. Native scheduling follows CPU time; MAME scheduling follows host
screen callbacks, independent of guest interrupt delivery, with up to one
20.032 ms frame of quantization. The default hold/gap is 120/160 ms, with 60/80
and 240/320 ms variants for the decisive EKDOS cases. The runner checks that
all scheduled contact events and the shutdown capture actually occurred.
Contact events alone do not prove that firmware accepted every character.

The native harness records instruction observations, keyboard reads, timer
writes, interrupt acknowledgements, console-state writes, periodic CPU/state
samples, and completed PBM frames. MAME records keyboard reads, timer writes,
periodic CPU/console-state samples, and PNG frames. Its `.ram` file is the
CPU-visible address space at shutdown, including any ROM overlay; native
`.ram` is physical RAM. They must not be compared as interchangeable dumps.

The analyzer reads the firmware's font rather than relying on OCR or a saved
screenshot. It requires all 180 diagnostic labels, a completion marker and
returned prompt, and evidence of both one-pixel and ten-pixel upward movement.
Movement is measured over a 32-row band of the numbered labels; copying takes
multiple display frames, so full-screen instantaneous translation is not
required. Counts are observations, not target frame rates or physical-hardware
fidelity claims. Cursor phase and CPU timing can differ between emulators.

For the public WASM runtime, build with `make test-wasm` and Emscripten on PATH,
then reuse the same diagnostic disk and input schedule:

```sh
node verification/juku-scroll/wasm_capture.mjs \
  ../8080-cosim/roms/ekta37.bin \
  /tmp/juku-scroll-comparison/diagnostic.juk \
  /tmp/juku-scroll-comparison/diagnostic/input.keys \
  /tmp/juku-scroll-comparison/wasm 180000
```

WASM captures the diagnostic interval (17–130 seconds) and the final screen,
with public video dimensions sampled every 20 ms. The same command can replay an EKDOS failure case
with the original disk, that case's schedule, and its duration.

## Boundaries

The comparison diagnoses guest behavior and rendering for the stated inputs.
It does not establish that the original reporter used exactly this firmware,
disk, or input context. It does not fix EKDOS or claim that MAME is a hardware
oracle. No emulator behavior changes, public API changes, or snapshot migration
are needed unless a core defect is demonstrated. FEDITOR acceptance and the
physical video-address validation from issue #17 remain separate work.

Keep generated disks, executables, frame sequences, traces, and intermediate
reports outside Git. The small summary records hashes for provenance only;
tests never require a capture to match a saved report hash.
