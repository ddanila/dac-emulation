# Optional S600 qualification with active peripherals

Run `make test-s600-workload S600_ROM=/path/to/S600.bin`. The target is optional:
ordinary `make test`, sanitizers and CI do not require a historical ROM or HDL.

The supplied reference used for this run has SHA-256
`4b54891c02a8ec279e2b8aec03489a961fc8647e08ad2036dcf82d0634bf7273`.
It is not an owner dump or identification of the specimen's replacement EPROM.

The original host test ROM repeatedly programs DMA copies, emits printer/V24
characters and polls received keyboard/V24 bytes. The S600 keyboard CPU scans
18 matrix press/release boundaries: A, Shift+A, Ctrl+A, Caps and SI/SO. After
each input edge, a production session snapshot is loaded into a second session.
A batched run and one-clock slices must produce identical complete state and
bus trace hashes. Observed lowercase/uppercase characters and Ctrl prefixes,
DMA reads, V24 reception and printer/serial output must all occur. LED latches
are checked after release; held contacts may still be in the firmware's scan
and debounce path. Both sessions must agree even at those intermediate points.
The initial sequence uses 8.2 million emulated clocks per session, with no OS boot.

The same optional target then runs the existing standalone S600 fixture for
held keys, REP, overlapping modifiers, clean release and keyboard power gating.
Both checks passed with the reference hash above. Default runtime tests also
passed. This qualifies deterministic behavior through our production snapshot
path; it is not independent hardware timing evidence or exhaustive S600 coverage.

## Extended mixed-peripheral boundaries

The optional workload also tests overlapping Shift/Ctrl, releasing Shift before
Ctrl, a production snapshot during actual partial keyboard reception, held-A REP
repetition and clean REP release, and reset with A held followed by a new press.
DMA, printer and V24 remain configured in the original host fixture. Repeated
characters, combined modifier prefixes and post-reset serial/DMA activity must
occur, as well as full snapshot and bus-trace equality under batch versus
single-clock scheduling.

The mid-byte search examines snapshot layout 13 (asserted explicitly), stopping
when keyboard RX has a nonzero phase and between one and seven received bits.
It searches at most 1,600 intervals of 256 clocks. Every comparison window uses
the public production snapshot save/load APIs. Runtime reset clears input matrix
state; the test qualifies this API behavior, not specimen reset wiring.

Maximum work is 23,809,600 clocks per session, including the search, with no OS.
The unchanged reference S600 hash above passed the expanded workload and the
standalone fixture. The test adds no ROM distribution or ordinary CI workload.
