# FEDITOR graphics and font verification

This investigation revisits [issue #17](https://github.com/infoaed/juku3000/issues/17)
and [issue #19](https://github.com/infoaed/juku3000/issues/19) with the recovered
[Font Editor archive](https://p6drad-teel.net/~p6der/font-editor.zip). Its executable
is named `fed.com`; the supplied help calls it FEDITOR. Measurements and input
hashes are in [results.json](results.json) and [wasm-results.json](wasm-results.json). Regression-suite and Monitor 3.3 checks
are recorded in [validation.json](validation.json).

The [cross-emulator suite](../juku-comparison/README.md) extends these workloads
to the independent `sinijarv-juku/juku-emu` core.

## Hardware contract

The [1988 Juku manual](https://elektroonikamuuseum.ee/failid/juku/Mikroarvuti_JUKU_kasutamisjuhend_1988.pdf),
section 0.4, printed pages 10–12, specifies that modes 1 and 2 read high ROM
but write video RAM. Suppressing those writes loses FEDITOR's picture data.
Mode 0 similarly writes RAM behind ROM. Mode 2's external-memory window still
does not select internal RAM. The core implements this read/write distinction
without recognizing application addresses or changing firmware.

FEDITOR blanks its display by writing zero to D54 counter 1 through port 11,
then restores the count after redrawing. The renderer publishes black frames
while horizontal output remains blanked, preserving the acquired geometry.
Entire blank scanlines still advance the vertical raster. No application-specific
mode sequence or redraw delay is used. Unit coverage varies the phase of the
blanking write and checks restoration of the displayed pixels.

The application's Latin font paths contain five `LXI H,DD01` instructions.
EKTA #0037's font begins at DD02. The diagnostic control changes only those five
operands in a disposable application copy; it is neither an emulator fix nor
a distributed patched application. Original-program runs retain the font
compatibility problem, including restoration of the wrong font pointer on exit.
A portable application correction should preserve the firmware's font pointer
before installing its own font and restore the saved pointer afterward.

## Reproduce

Requirements: C compiler, Python 3 with Pillow, MAME 0.289 and its Juku ROMs,
EKTA #0037, an EKDOS boot disk in the supported 819200-byte DS/DD layout, and
the external archive. From the repository root:

```sh
python3 verification/juku-feditor/run.py \
  --rom ../8080-cosim/roms/ekta37.bin \
  --base /path/to/prog1.juk \
  --archive /path/to/font-editor.zip \
  --roms /path/to/mame/roms --mame /path/to/mame \
  --output /tmp/juku-feditor-comparison
make wasm
python3 verification/juku-feditor/wasm.py \
  --rom ../8080-cosim/roms/ekta37.bin \
  --comparison /tmp/juku-feditor-comparison
```

The output directory must be new. The harness preserves the boot tracks and
creates a disposable filesystem containing all eight archive files, verifies
their installation, and uses timed physical keyboard contacts. It compares the
historical core at `577f09ba`, current default and experimental paced native
builds, and MAME; the font-address control runs in default native and MAME.
The WASM check uses the public runtime and the unmodified application.

The schedule enters keyboard operation, selects Latin, loads a font, saves
`TEST.LAT`, opens and closes help, and exits. Assertions check the space glyph,
midpoints of each sustained blanking interval, the saved font and unrelated
disk bytes. The saved font may differ in its first pixel; this is recorded
explicitly and is not evidence of successful pixel-edit persistence. Screen
captures at the selection, editor, help and exit stages supplement the checks.
`comparison.png` presents the baseline, default core, MAME and both controls.

Historical binaries, disposable disks, screenshots, traces and RAM dumps stay
outside Git. The committed reports describe these specific runs, not golden
hash tests. Mouse operation, Cyrillic correction, other ROMs and physical
hardware remain unverified. This does not establish complete FEDITOR correctness
or promote the experimental floppy mode.
