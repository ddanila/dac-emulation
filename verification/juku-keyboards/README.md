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
agree on these observations; historical output is not compared to a frozen
report. Captures stay outside Git. [results.json](results.json) holds the
host-to-guest inventory, input provenance and qualification summary.

## Interpretation and remaining scope

ASCII host identities generally request characters, while 80h–91h identify
particular Juku keys. Different firmware may assign different control codes
to equivalent physical keys. Codes 5Ch, 60h, 7Bh–7Eh also represent Estonian
letters in the installed EKTA font, so ASCII byte equality alone is not a
complete character or glyph test. LF intentionally selects the Return key.

The AT host mapping currently mixes US punctuation positions with #0043's
layout and lacks the synthetic navigation/function keys. Its latch accepts
make/break bytes but does not implement keyboard typematic. JUSS maps text
and four arrows, with other synthetic functions absent. Completing those
paths requires independent contact/scan evidence, not injecting expected
characters into RAM or rewriting the ROM tables. Language modes, caps-lock,
keypad/extended sequences, overlapping keys and snapshot continuation also
need separate qualification before claiming a complete keyboard model.

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
