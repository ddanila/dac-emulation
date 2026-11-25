# Juku disk-image ordering

[Issue #23](https://github.com/infoaed/juku3000/issues/23) concerns the distinction
between an emulator sector image and a CP/M logical image. The existing JUK
contract should remain compatible with existing media. A linear CP/M image
needs explicit conversion before mounting; its size or filename extension
cannot reliably identify its ordering.

## Three separate orderings

For the EKDOS DS/DD format, each head has 80 cylinders, each track has ten
512-byte physical sectors, and the image contains 819200 bytes.

* JUK stores cylinders in increasing order, with head 0 then head 1 at each
  cylinder. Within a track, it stores sector IDs 1 through 10 in numeric order.
* EKDOS logical tracks visit head 0 cylinders 0–79, then head 1 cylinders 0–79
  (`outout`, not `outback`).
* EKDOS logical sectors visit physical IDs 1,3,5,7,9,2,4,6,8,10. Each physical
  sector contains four successive 128-byte CP/M records.

Thus the emulator's raw image offset is
`((cylinder * 2 + head) * 10 + sector_id - 1) * 512`.
Firmware translates logical requests into those physical coordinates. The
controller must not apply CP/M skew or logical side ordering a second time.

For example, logical track 2 starts at raw offset 20480, while its offset in a
linear CP/M image is 10240. Logical track 80 starts at raw offset 5120 but
linear offset 409600. These address different representations of the same sectors.

JUK is a coherent physical-sector payload image. It does not preserve flux,
gaps, CRCs, sector timing, or arbitrary track formatting, and it is not a linear
CP/M block image. There is no universal CP/M image layout that can replace
these conventions without declaring the conversion.

## Source evidence

DAC uses `dac_media_offset` in `common/media/media.c`, through
`common/fdc/wd_disk.c`. The
[sinijarv disk implementation](https://github.com/sinijarv-juku/juku-emu/blob/1b82a399240b14cc9a54679cc075983a47ccdc33/core/src/floppy.rs)
uses the same cylinder/head/sector offset.

MAME's [Juku format](https://github.com/mamedev/mame/blob/master/src/lib/formats/juku_dsk.cpp)
inherits
[`wd177x_format::get_image_offset`](https://github.com/mamedev/mame/blob/master/src/lib/formats/wd177x_dsk.cpp),
which sums all heads of preceding cylinders and then preceding heads of the
current cylinder. Its `outout` format comment describes the filesystem's
logical traversal; it does not select a head-major file layout.

The [disk-reading documentation](https://j3k.infoaed.ee/kettad/) and
[EKDOS source](https://github.com/infoaed/juku3000/blob/master/src/EKDOS30.ASM)
describe the filesystem geometry and translation table. The published
[libdsk configuration](https://github.com/infoaed/juku3000/blob/master/src/libdskrc)
declares logical `outout` traversal. A tool must honor both its image driver's
storage order and that logical geometry. Merely supplying a sector skew table
does not solve the head-order difference.

## Reproduce

The opt-in runner compiles current DAC and unmodified sinijarv cores, reuses the
cross-emulator capture adapters, and runs MAME with original EKTA #0037 firmware.
It needs a C compiler, Rust, Python with Pillow, MAME, cpmtools, a ROM set and
a historical DS/DD EKDOS disk such as the public emulator's `prog1.juk`.

```sh
python3 verification/juku-layout/run.py \
  --base /path/to/prog1.juk \
  --rom /path/to/ekta37.bin --roms /path/to/mame/roms \
  --source /path/to/sinijarv-juku/juku-emu \
  --mame /path/to/mame --output /tmp/juku-layout
```

Use a new output directory; optionally supply `--rustc`. Original inputs are
read-only. Generated binaries, writable media and captures stay outside Git.
Measurements and input hashes are in [results.json](results.json).

The runner converts the historical image to linear logical order and back,
requiring byte-for-byte preservation. It lists the converted historical
directory using a cpmtools definition with no skew. On a disposable copy, it
replaces the directory and installs a generated BDOS diagnostic and a patterned
16 KiB file in allocation blocks 96,97,98,196. Block 97 crosses the head boundary;
block 196 reaches the last complete allocation block. The guest checks every
input record and EOF, then rewrites every record and closes the file. Host
verification checks persisted content and preservation of unrelated bytes.

An independent cpmtools extraction checks the converted diagnostic file. A
negative control interprets the original JUK as linear and must fail to extract
the expected content. This demonstrates the tooling mismatch without changing
emulator behavior or silently guessing an image's format.

## Scope

This investigates ordinary EKDOS DS/DD media ordering, not controller timing,
flux fidelity, all historical filesystem variants, or physical hardware.
The test exercises both heads through guest firmware but is not an exhaustive
test of every sector or every historical file. The historical directory listing
alone is not proof that all its file contents are correct.

No core format change follows from this issue. If linear-image import/export
is exposed in the product, it should be an explicit, reversible conversion
with a declared filesystem geometry, preserving existing JUK compatibility.
Single-sided images still require sector-skew handling, but do not have the
two-head ordering distinction tested here.
