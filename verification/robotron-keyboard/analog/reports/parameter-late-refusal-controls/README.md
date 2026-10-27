# Late parameter refusal through complete snapshots

All three native unsupported subclasses (binary, real, string) are allocated at 5 us after successful startup and pre-allocation combined observations. Both direct parameter inventory and complete snapshot construction refuse immediately and again at 6 us. The compact logger keeps its cache pointer identities and sequence counters; no partial or stale snapshot is serialized after refusal.

For each family, all six compact streams decode three complete supported snapshots: startup before/repeat and pre-allocation. Native bindings cover 56 parameters, 651 signals, 317 ports, three memories and 23 memory read ports. All 27,578 waveform samples across 31 signals and complete firmware records equal the original 20-us execution. Four bus edges occur after the second refusal, at the same times as the reference.

Seven tests pass, including full campaign replay and missing-refusal, failed-refusal, cache-identity and post-refusal serialization rejection checks. JSON replay comparison normalizes dictionary keys through serialization. The separate activity assessment replays the full review before checking bus activity. All captures were copied byte-for-byte after review, and the manifest binds every retained file and reviewer source.

The unsupported objects remain allocated. This is refusal and continuation evidence, not private-state observability after refusal, object destruction/address reuse, full observer integration or a general cost bound.

Replay from the repository root:

```sh
python3 -m unittest discover -s verification/robotron-keyboard/analog -p 'test_parameter_late_refusal*.py'
python3 verification/robotron-keyboard/analog/retained_evidence.py verification/robotron-keyboard/analog/reports/parameter-late-refusal-controls
```
