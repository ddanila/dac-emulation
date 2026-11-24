# Juku application font comparison

This opt-in investigation targets [issue #19](https://github.com/infoaed/juku3000/issues/19)
using MFD.COM from VAKSTU05.JUK and the BOWLING.COM version distributed on the
public browser's game1.juk. It compares native default and experimental paced
floppy builds with MAME 0.289, using unmodified EKTA #0037 and EKDOS 2.30.
Measurements, the diagnosis, and limitations belong in [results.json](results.json).

## Reproduce

Requirements: C compiler, Python 3 with Pillow, MAME and its Juku ROM set.
Historical media are external inputs. Sources are the
[museum collection](https://elektroonikamuuseum.ee/failid/juku/tarkvara/),
[public emulator](https://infoaed.ee/juku/), and
[software catalogue](https://j3k.infoaed.ee/tarkvara-kataloog.txt).

```sh
python3 verification/juku-fonts/run.py \
  --rom ../8080-cosim/roms/ekta37.bin \
  --base /path/to/prog1.juk \
  --bowling /path/to/game1.juk \
  --mfd /path/to/VAKSTU05.JUK \
  --roms /path/to/mame/roms \
  --mame /path/to/mame \
  --output /tmp/juku-font-comparison
```

The output directory must be new. The harness extracts each live CP/M file
without changing its bytes and installs it into an unused block/directory slot
on a disposable copy of the same boot disk. It supports this specific DS/DD
layout and single-block applications, not arbitrary CP/M media. Original
inputs are never modified; the generated disk is read-only during execution.

The normal runs execute the original programs. The explicitly labelled
**control** runs change their initial font-copy source from DD01 to DD02.
Native controls substitute the operand of an executed `LXI H,DD01` inside the
observation harness. MAME controls modify the initial copy's operand in guest
RAM after decompression, when the application installs its font pointer. These
are counterfactual experiments, not emulator fixes or patched software releases.
Both control paths must execute exactly once. Other font-selection/restoration
paths remain outside this correction's scope.

Both engines receive the same timed physical keyboard contacts through the
issue-20 scheduler. The comparison checks firmware initialization of the font
pointer, all 1,728 source reads, the resulting 864-byte font, and final screens.
BOWLING deliberately replaces two glyphs with its own bitmaps; the expected
ROM transformation excludes those glyphs, while cross-engine comparisons
include them. Screens must match apart from BOWLING's single blinking cursor
cell. MAME's physical RAM share is captured separately from its CPU-visible
address space, which may contain a ROM overlay.

`comparison.png` contains the original and control screens for all three builds.
Generated disks, binaries, traces, RAM and images remain outside Git. The JSON
summary records hashes for provenance; assertions test behavior, not stored
report hashes. No CI job or production emulator hook is added.

For a public WASM runtime comparison, build `make wasm` with Emscripten and run:

```sh
python3 verification/juku-fonts/wasm.py \
  --rom ../8080-cosim/roms/ekta37.bin \
  --comparison /tmp/juku-font-comparison
```

This reuses the unmodified application disks and schedules, compares both final
screens against native, and writes `wasm-results.json`. The recorded WASM
measurements are in [wasm-results.json](wasm-results.json). These runs exercise
original applications only; the public API has no diagnostic font-address
substitution. A portable application correction would preserve and use the
firmware-provided font pointer before installing a replacement font, and restore
that saved pointer on exit, rather than assume one ROM address.

## Boundaries

The investigation covers the initial MFD menu and BOWLING speed-selection
screen. It does not cover every application function, other ROMs, real hardware,
or FEDITOR, whose executable remains unavailable. The issue does not specify
its original ROM or show a screenshot, so these are concrete reproductions of
the named applications' font corruption, not proof of every reported symptom.
