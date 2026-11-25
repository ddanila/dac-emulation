# Cross-emulator Juku issue workloads

This opt-in suite compares the default DAC core, MAME, and the unmodified
[sinijarv-juku/juku-emu](https://github.com/sinijarv-juku/juku-emu) Rust core.
It extends the existing investigations of issues
[#17](https://github.com/infoaed/juku3000/issues/17),
[#19](https://github.com/infoaed/juku3000/issues/19),
[#20](https://github.com/infoaed/juku3000/issues/20), and
[#25](https://github.com/infoaed/juku3000/issues/25).
The experimental DAC floppy configuration is an additional #25 comparison.
Versions, input provenance and measurements belong in [results.json](results.json).

## Workloads and observations

| Issue | Workloads | Observations |
| --- | --- | --- |
| #17 | FEDITOR startup, help and exit; Monitor 3.3 boot | Timer-requested blanking, complete pictures and active geometry |
| #19 | MFD, BOWLING, original FEDITOR and diagnostic font-address control | Installed font bytes, space glyph, and FEDITOR editor grid |
| #20 | EKDOS plain/escape-colon/escape-semicolon/escape-colon-Ctrl-Q, monitor echo, SCROLL.COM | Invalid drive value, scroll state, 180 numbered lines, one- and ten-pixel movement, completion and returned prompt |
| #25 | FDC25.COM through EKDOS/BDOS | Eight written/read records, EOF, persisted 1024-byte file, unchanged unrelated disk bytes, guest PASS marker |

FEDITOR also loads and saves a font. The saved file is compared with the loaded
font, allowing and recording the first-pixel difference observed in the scripted
workflow. This is not a verification of arbitrary editing operations. The
DD01-to-DD02 control changes five operands in a disposable FEDITOR copy; all
normal runs use original application bytes and unchanged ROMs.

The suite records both successful behavior and disagreements. A completed
capture is not a passing hardware test. In particular, reproducing the EKDOS
invalid-drive bug or an application's wrong font address is reported as a
reproduction, not as successful application behavior. A failure of an expected
behavior remains visible in the report. Emulator process failures are recorded
with their exit status; a Monitor 3.3 failure in MAME is retried without the
capture script. Monitor 3.3 also gets three extra MAME runs with and three
without the adapter, retaining intermittent failures. Build errors, missing frames after a successful process exit,
and incomplete input schedules abort the run.

## Reproduce

Requirements: Python 3 with Pillow, a C compiler, Rust (tested with stable
1.100.0), MAME with its Juku ROM set, the external ROMs/disks/archive and a
checkout of the third-party source. No GUI or Rust workspace dependencies are
needed: the adapter links the dependency-free core directly with `rustc`.
The third-party checkout is only read, never patched or built in place.

```sh
git clone https://github.com/sinijarv-juku/juku-emu /tmp/juku-emu
python3 verification/juku-comparison/run.py \
  --source /tmp/juku-emu \
  --rom /path/to/ekta37.bin --monitor33 /path/to/jmon33.bin \
  --base /path/to/prog1.juk --mfd /path/to/VAKSTU05.JUK \
  --bowling /path/to/game1.juk --archive /path/to/font-editor.zip \
  --mame /path/to/mame --roms /path/to/mame/roms \
  --output /tmp/juku-comparison
```

Use a new output directory. `--rustc` accepts an explicit compiler path.
`--case fdc25` (repeatable) selects individual workloads.
`--analyze-only` re-reads an existing completed comparison without rerunning
the emulators; supply the same input arguments.
Historical media sources and layout assumptions are documented in the
[FEDITOR](../juku-feditor/README.md), [font](../juku-fonts/README.md),
[scrolling](../juku-scroll/README.md), and [floppy](../juku-fdc/README.md)
investigations. Inputs are preserved; each writable guest receives its own
in-memory or filesystem copy. Generated executables, disks, traces and frame
sequences stay outside Git. `comparison.png` shows FEDITOR's selection and
editor screens in the three emulators.

The adapters press physical keyboard matrix contacts using the same schedules.
DAC and Rust schedule at instruction boundaries; MAME schedules at frame
callbacks. Firmware must still scan and accept those contacts. The Rust adapter
records completed active-area frames, physical RAM, I/O writes and selected
instruction observations through public APIs. Its FDC timing counter measures
whole data-I/O instructions longer than 18 cycles; it is not a bus-edge trace.
MAME's physical RAM share is saved separately from its CPU-visible address space.

## Limits

The engines are independent implementations, not physical-hardware oracles.
The third-party FDC model gates waits with PA6 and advances to controller events;
its documentation explicitly leaves the production DRQ-to-READY wiring unknown.
Agreement on file contents does not settle that circuit, error-release behavior,
CPU bus phases, or host execution-budget responsiveness. This comparison does
not promote DAC's experimental floppy mode.

The third-party raster follows sync and porch timing; this suite compares its
active area, not the CRT shader or the full analog monitor response. Mouse,
other firmware/application versions, abnormal FDC transfers and the original
scrolling study's full input-timing matrix are outside this extension. Existing
specialized native/WASM and controller tests remain separate.

Controller polarity, JUSS input and historical bootstrap coverage are provided
by the separate [issue #16 investigation](../juku-fdc-variants/README.md).

Disk-image ordering and BDOS file I/O across the head boundary are covered by
the separate [issue #23 investigation](../juku-layout/README.md), which reuses
these capture adapters with a generated file in explicitly selected blocks.

The [issue #13 investigation](../juku-window/README.md) uses a separate generated
8080 program to compare external-window reads and internal RAM write isolation
across all memory modes, with the preserved D6 PROM as decode evidence.

The [issue #18 investigation](../juku-input/README.md) compares natural and
physical Estonian keyboard input through original ROM services, including
native/WASM profile coverage and the resulting glyphs.
