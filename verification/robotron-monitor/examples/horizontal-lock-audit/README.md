# Horizontal lock audit: failed connected frame, completed isolation benches

The connected four-field S550 replay completed in 177.62 seconds, but is **not an
accepted warmed frame**. It produced 933 flybacks rather than 936; the last three
fields drifted 3.335 lines. Direct comparison to captured ordinary BSYN pulses
found three missing matches out of 926. No short-interval ringing was detected.
The final field's control voltage ranged from -2.757 to 16.972 V.

The six-point forced-control sweep shows a non-monotonic oscillator response.
At 0, 4, 8, 12 and 18 V, periods were 63.757, 67.207, 63.775, 59.575 and 48.685 us.
The 16-point phase sweep used actual recorded sync and feedback cycle shapes,
explicitly retimed to 62.5 us, with prescribed relative phase. Mean control
voltage ranged from -3.771 to 1.818 V. Both isolation benches retain the 39-part
horizontal stage but use a dummy secondary load. They do not establish loaded
loop gain, feedback sign, connected lock or actual-monitor calibration. Large
control ripple also prevents treating the DC tuning curve as an exact prediction
of the connected oscillator frequency.

`audit.json` hashes the numerical evidence and exact SPICE decks. The recorded
cycle samples, source periods and input raw trace hash are in `phase/stimulus.json`.
The source table and device models are embedded in every deck. Numerical source,
thermal and magnetic assumptions of the connected run are in its metadata.
Large binary waveforms remain in `build/monitor/sync-audit-tank1532`.

Reproduce an archived deck with the verified runtime from the repository root:

```python
from pathlib import Path
import sys
sys.path.insert(0, 'verification/robotron-monitor')
import steady_supply
source = Path('verification/robotron-monitor/examples/horizontal-lock-audit/connected/run.cir')
steady_supply.solve(source.read_text(), Path('build/monitor/reproduce-lock-audit'),
                    Path('build/monitor/runtime-clean'), timeout_s=400)
```

Substitute `tuning/0.cir` or `phase/0.cir` through `phase/15.cir` to reproduce an
isolation point. Source stimulus repetition in those decks is intentional and
must not be used as a connected-monitor acceptance stimulus.
