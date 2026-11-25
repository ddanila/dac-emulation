# Estonian host keyboard input

[Issue #18](https://github.com/infoaed/juku3000/issues/18) concerns accented
letters in MAME's natural-input mode. Keyboard contacts, firmware character
codes and displayed glyphs are distinct layers. The fix belongs in host-key
translation; it must not inject console bytes or replace the historical font.

DAC accepts the Latin-1 identities for `äõöüÄÕÖÜ` through `juku_key`/`dac_key`,
alongside its existing ASCII and synthetic keys. They select physical matrix
contacts or AT scan codes. Firmware still performs scanning, shift handling,
character translation and rendering. The browser accepts these Unicode letters
for host key events and paste; pasted decomposed text is normalized to NFC.
Other unsupported Unicode remains rejected by paste. Other machines retain
their existing input character repertoire.

## Mapping evidence

For the Juku keyboard, ä/õ/ö/ü use column/encoded-row pairs 11/5, 10/3, 12/5
and 11/3 respectively; capitals use the same contacts with Shift. JUSS uses
11/3, 12/2, 10/3 and 11/2. The #0043 AT firmware decodes scan-set-1 positions
40, 26, 39 and 27 respectively. Its Õ/Ü positions differ from the usual Juku
positional mapping; assuming US bracket positions would exchange these letters.

The ROM's TTI service at FFD3h is documented in the 1988
[manual](https://elektroonikamuuseum.ee/failid/juku/Mikroarvuti_JUKU_kasutamisjuhend_1988.pdf),
section 7.2, printed page 37. The probe calls that entry in memory mode 1,
records the returned character, and reads its glyph through the ROM-selected
font pointer. For the qualified EKTA images the sequence is:

| Host text | ä | õ | ö | ü | Ä | Õ | Ö | Ü |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Guest code (hex) | 7C | 7D | 7B | 7E | 5C | 60 | 40 | 5E |

These codes are not Unicode or Latin-1 text. Some replace ASCII punctuation;
software that installs an ASCII or custom font can display different glyphs.
The host key identity is preserved in recordings, not the resulting guest code.

## Independent emulators

MAME's [Juku input definitions](https://github.com/mamedev/mame/blob/master/src/mame/ussr/juku.cpp)
name accented keys without providing the corresponding Unicode character
bindings. Its [natural keyboard fallback](https://github.com/mamedev/mame/blob/master/src/emu/natkeyboard.cpp)
transliterates unsupported accented letters to ASCII. The comparison runs the
real `natkeyboard:post` path and a separate physical-contact control, both
through the original monitor TTI routine. The latter distinguishes a host
mapping problem from a firmware/font defect.

Sinijarv's [host mapping](https://github.com/sinijarv-juku/juku-emu/blob/1b82a399240b14cc9a54679cc075983a47ccdc33/frontends/windows/src/keymap.rs)
is positional rather than character-based. Its independent core is exercised
with those same physical contacts through public APIs. This is a core/firmware
comparison, not a test of its native GUI or a Unicode paste implementation.

## Reproduce

Requires Python, a C compiler, Rust, MAME with the Juku ROM set, external ROM
images, and an unmodified sinijarv source checkout. Emscripten and Node enable
the optional native/WASM comparison; initialize the Emscripten environment first.

```sh
python3 verification/juku-input/run.py \
  --roms /path/to/mame/roms/juku \
  --source /path/to/sinijarv-juku/juku-emu \
  --mame /path/to/mame --emcc emcc \
  --output /tmp/juku-input
```

Use a fresh output directory; `--rustc` can name an explicit compiler. Results,
input hashes, returned bytes and glyphs are in [results.json](results.json).
Original inputs are read-only. Native and WASM cover #0024, #0031, #0032,
#0035, #0037, #0043 and Monitor 3.3 with their corresponding hardware profiles.
The #0043 fixture makes the explicitly recorded checksum correction at offset
000Ah in a disposable copy; production does not silently repair ROMs.

The adapters allow startup to initialize the monitor, install a tiny caller in
RAM, enter mode 1 through the PPI, and call TTI. They do not alter the scanner,
keyboard table or font. Native/WASM exercise DAC's host identities; MAME and
sinijarv comparisons use #0037. The raw executable and capture files remain
outside Git. This suite is opt-in, not a new CI workflow.

Monitor 3.3 has a different font and case behavior: Õ/Ö requests return the same
codes as õ/ö, and several glyphs use capitals even at nominal lowercase codes.
This is retained historical behavior, not normalized by the emulator. The
generated single-density profile has no additional historical ROM pairing to
qualify. Arbitrary language-mode switches, remapped firmware, IME composition,
and physical keyboard electrical timing are outside this qualification.

Browser regression coverage lives in the museum's `tests/workbench.spec.js`:
Unicode normalization/rejection, host key presses and releases, paced paste,
recording, and deterministic replay. The firmware probes separately establish
that those host identities reach the intended characters and glyphs.
