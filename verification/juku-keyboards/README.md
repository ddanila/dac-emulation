# JUSS and AT keyboard qualification

[Issue #15](https://github.com/infoaed/juku3000/issues/15) requests JUSS
(EKTA #0024/#0035) and AT (#0043) layouts. Selecting a hardware profile,
producing a character code, and reproducing a physical keyboard are separate
qualification claims. The [Estonian input study](../juku-input/README.md)
covers the accented letters and their glyphs; it does not qualify every key.

## Reproduce

```sh
python3 verification/juku-keyboards/run.py \
  --roms /path/to/roms/juku --output /tmp/juku-keyboards --emcc emcc
```

Requires a C compiler, Python, historical ROMs and, for `--emcc`, Emscripten
and Node. Omit `--emcc` for native only. Use a fresh output directory.
The script builds the current core. Each of the 255 nonzero host identities
gets a fresh boot and an original monitor TTI call at FFD3h, with a 600,000
cycle response window. A null result means that call did not return within
the window, not that no conceivable firmware state could recognize the key.
Mode 1 is entered through a CPU OUT instruction. No scanner, translation
table or console byte is patched. A disposable #0043 copy receives only the
explicit checksum correction recorded in the report.

The hold probe continuously calls TTI and counts returns. Five four-million-
cycle intervals exercise press/hold, release, press again, another down event
without release, then release. It measures firmware-visible output, not
physical debounce or the electrical timing of an AT cable. Native/WASM must
agree on these observations; The physical probe independently checks letters, modifiers, locks, navigation,
function keys and keypad contacts. Historical output is not compared to a frozen
report. Captures stay outside Git. [results.json](results.json) holds the
host-to-guest inventory, input provenance and qualification summary.

## Interpretation and remaining scope

ASCII host identities generally request characters, while 80h–91h identify
particular Juku keys. Different firmware may assign different control codes
to equivalent physical keys. Codes 5Ch, 60h, 7Bh–7Eh also represent Estonian
letters in the installed EKTA font, so ASCII byte equality alone is not a
complete character or glyph test. LF intentionally selects the Return key.

The core models independent physical contacts and text-generated contact
combinations. Their union drives the matrix encoder or AT make/break transport;
releasing a generated Shift cannot release a physical Shift. Matrix row priority
matches the 74148 encoder. Host repeat events are ignored: matrix repeat belongs
to the monitor, and AT typematic uses a 500 ms initial delay and approximately
10.9 Hz in emulated cycles, with the most recently pressed repeatable key owning
repeat. These defaults follow the [IBM PC AT technical reference](https://ftpmirror.your.org/pub/misc/bitsavers/pdf/ibm/pc/at/6183355_PC_AT_Technical_Reference_Mar86.pdf).

`juku_keyboard_contact` accepts matrix IDs `column * 8 + row` (rows 0–5),
Shift 128 and Ctrl 129; AT IDs are set-1 scan codes, extended codes plus 256,
and Pause 512. `juku_keyboard_release_all` clears both ownership sources.
The text-contact query reports unsupported identities before typing begins.
The bounded AT host transport accepts complete transitions atomically; callers
retry busy input after running the machine. Repeat yields queue space to releases.
This queue is not a PC 8042. Snapshots retain contacts, queued/latching scan
bytes and repeat deadlines. The runtime snapshot version is 25.

[keyboards.json](../../machines/juku/keyboards.json) supplies browser physical
positions and legends. JUSS function/navigation positions and Caps/LAT-RUS were
checked through original-ROM TTI calls using independent contact constants in
`physical.c`. The #0043 scanner at 120Fh recognizes Caps break BAh, LAT/RUS
break C6h (Scroll Lock), and Num Lock break C5h. The physical probe exercises
these locks, right Ctrl and keypad Enter; Monitor 3.3 retains Latin output in
this language-toggle case. Text punctuation follows the original ROM tables,
not US scan positions. In default AT language state, `[` and `]` have no text
mapping and are rejected. Character byte aliases for Estonian glyphs remain
intentional; the separate glyph qualification must also pass.

The adapter remains a firmware-derived PPI contract, not an electrical PS/2
simulation. Extended keys, Print Screen and Pause have transport sequences;
that does not imply the historical ROM gives every modern key a function.
Print Screen uses its ordinary set-1 sequence; modifier-specific variants and
host-to-keyboard commands are outside this adapter model. Hardware debounce,
keyboard cable timing and every multi-key chord have not been qualified on
physical Juku hardware. No console bytes or ROM translation tables are patched.

## Other emulators

Current upstream [MAME Juku source](https://github.com/mamedev/mame/blob/master/src/mame/ussr/juku.cpp)
contains one standard keyboard input definition and explicitly lists JUSS/AT
layouts as TODO. The issue's January 2026 comment mentions a preliminary
XT/AT driver in the J3K laboratory; that separate implementation is not covered
by the upstream comparison and must not be described as disproven by it.

The inspected [sinijarv keyboard core](https://github.com/sinijarv-juku/juku-emu/blob/1b82a399240b14cc9a54679cc075983a47ccdc33/core/src/keyboard.rs)
exposes matrix contacts and Shift/Ctrl; its frontend supplies the standard
Juku positional map. A caller can supply other matrix contacts, but this is
not a packaged JUSS layout, and it is not an AT serial adapter. These are
source capability comparisons, not new GUI or alternate-profile dynamic
runs. The previous standard-Juku cross-emulator control remains in the
[Estonian input study](../juku-input/README.md).
