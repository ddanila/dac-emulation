# Juku controller variants

This opt-in investigation covers [issue #16](https://github.com/infoaed/juku3000/issues/16)
using unmodified ROMs in our emulator, MAME, and the
[sinijarv core](https://github.com/sinijarv-juku/juku-emu).
Measurements and limitations belong to [results.json](results.json).

The [Western Digital FD179X datasheet](https://bitsavers.trailing-edge.com/components/westernDigital/FD179X-01_Data_Sheet_Oct1979.pdf)
defines inverted DAL lines for FD1791 and true DAL lines for FD1793. FD1792
is single-density only; complementing bytes is not sufficient to claim FD1792
support. Controller polarity and the machine's I/O address decoder are separate
configuration choices. The sibling `8080-cosim/docs/fdc-bus-polarity.md` provides
additional firmware and board evidence for the direct-bus replica profile.

## Reproduction

Use Python 3, a C compiler, Rust supporting edition 2024, MAME with Juku ROMs,
a checkout of the sinijarv emulator, preserved Ekta/Monitor ROM images, and an
819200-byte EKDOS 2.30 base disk without `FDC25.COM` or `FDC25.TST`.
The output directory must not exist. Raw captures and disposable disks stay
outside Git; the summary records their hashes without using them as test gates.

```sh
make test-juku-fdc-variants
python3 verification/juku-fdc-variants/run.py \
  --roms ../8080-cosim/roms \
  --base /path/to/prog1.juk \
  --source /path/to/juku-emu \
  --mame /path/to/mame \
  --mame-roms /path/to/mame-roms \
  --rustc /path/to/rustc \
  --output /tmp/juku-controller-study
```

The integration test exercises CPU `IN`/`OUT` for all 256 track, sector and data
register values, complete sector reads, writes and readback, with either bus
polarity and both FDC timing implementations. It does not identify ROMs or patch
instructions.

The real-media runner compares direct and inverted buses explicitly. Its
`JUKU_FDC_BUS_INVERT=1` setting selects the existing internal diagnostic option;
it does not add a frontend machine profile. For ROM #0024, adapters supply JUSS
physical keyboard contacts. MAME's fixed input fields omit some of those
contacts, so its adapter supplies the encoded keyboard lines at port 5 while
preserving DIP-switch bits. All other emulated hardware remains unchanged.

The EKDOS guest creates a file, writes eight records, reopens and verifies them,
checks EOF, and returns to the prompt. The host independently checks all file
bytes and forbids changes to unrelated disk blocks. Our capture observes the
ROM console vector for the guest's PASS/FAIL message. Cross-core captures also
check the persisted file; process or Lua failures are recorded as failures.

Monitor 3.3 uses a different bootstrap layout. A generated disk places a small
marker-and-halt program at its entry sector. The runner checks all 13 sector
transfers (6656 bytes), their order, their RAM destinations, and execution of
the marker at CE00. This establishes bootstrap/controller compatibility; it is
not evidence that a historical operating-system disk boots successfully.

The firmware inventory recognizes raw IN/OUT byte patterns and adjacent
CMA/NOP bytes. It does not establish reachability of every match. Expansion-card
ROMs #0032/#0043 are inventoried at ports 30–33 but are outside the dynamic boot
matrix. Complete selectable machine profiles, JUSS frontend input, FD1792/FM,
and expansion-card emulation remain separate implementation work.
