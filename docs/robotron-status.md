# Current Robotron emulation status

The reference S550/CAS/S600/TOS-M configuration is not an identified specimen
ROM set. The [machine guide](../machines/robotron1715m/README.md) describes the
implementation; the museum's
[capability matrix](https://github.com/ddanila/dac/blob/main/docs/robotron/capabilities.md)
summarizes behavior and remaining fidelity limits. Runtime manifests own version,
ABI and snapshot identities; release changes belong in git history.

Keyboard logical comparisons and electrical qualification have distinct scopes.
Use the [board guide](../verification/robotron-keyboard/README.md) for C/HDL
comparisons and the [analog guide](../verification/robotron-keyboard/analog/README.md)
for closed-board simulation. The keyboard backend has a separate Z80 bus-timing
acceptance suite. Its digital contract does not establish U880 specimen timing,
applicable analog device behavior, physical copper or specimen firmware identity.

## Reproduce qualification

Fast checks require no historical firmware, MAME or HDL:

```sh
make test test-runtime-sanitize
make test-wasm  # requires the pinned Emscripten toolchain
```

Optional qualification uses local caller-supplied media:

```sh
make test-s600-workload S600_ROM=/path/to/s600.bin
python3 tools/compare_robotron_mame.py --media /path/to/media --output build/mame.json
python3 tools/compare_robotron_historical.py --media /path/to/media --output build/historical.json
python3 tools/compare_robotron_historical.py --suite wordstar --media /path/to/media --output build/wordstar.json
python3 tools/compare_robotron_historical.py --suite pascal --media /path/to/media --output build/pascal.json
python3 tools/compare_robotron_serial.py --media /path/to/media --output build/serial.json
```

The comparison tools retain inputs, core identity, observations and limits in
their reports. They use temporary media copies. MAME is an independent
implementation, not a hardware oracle; native fault and snapshot regressions
remain separate from those comparisons. See the museum's
[qualification guide](https://github.com/ddanila/dac/blob/main/docs/robotron/emulation-qualification.md#independent-reference-scope)
for comparison scope and interpretation.

## Evidence still needed

Display DACK latency, dot-level CPU contention, IRQ routing, DMA half-clock
arbitration, CTC waveform duty cycle and SIO x1 half-stop timing need more specific
evidence. Existing explicit-clock fixtures qualify an ideal diagnostic waveform;
they do not justify changing the museum's CTC route. Synchronous serial modes,
flux/PLL and weak-sector support are absent. Drive trajectories are a documented
reference profile; see [drive fidelity](../machines/robotron1715m/DRIVE-FIDELITY.md).

ROM/PROM dumps, board straps, drive suffixes/jumpers and clock/logic captures from
the actual specimen remain necessary. More software agreement cannot establish
these facts. The museum inventory tool records supplied hashes and provenance
without promoting reference media to specimen evidence.
