# Single-frame charge, energy and lock audit

**No accepted warmed frame.** This archive records completed numerical checks
and failed acceptance evidence. It is not a diagnosis of the photographed CRT.
The compact archive omits large raw waveforms and current arrays; those remain
in the build directories identified by `audit.json`.

![Unaccepted connected diagnostic, fixed exposure](diagnostic/frame.png)

The fresh 240×180 diagnostic remains very dim and distorted. It comes from the
last native S550 field of the connected four-field solve in `connected/run.cir`.
Its failed synchronization/periodicity checks accompany the image. Prior
identical electrical fields are assumed only for phosphor initialization.
This preview does not replace the independent full-resolution refinement gates.

## Completed evidence

- The initial trajectory collection pass accounts for 1.8583891406740551 nC.
  Relative charge error is 2.23e-15, with no unresolved collector charge. About
  half reaches the phosphor; the rest reaches the explicitly assumed anode
  sleeve. See `collection.json` and the collector assumptions it retains.
- Initial beam electrical work and trajectory kinetic-energy gain agree within
  0.000465%. This is an **uncoupled initial check**, not evidence that outer
  circuit/collection iteration converged. See `beam-work.json`.
- All nine connected R24 trim settings fail lock/periodicity. At trim 0.99 the
  final three fields contain the correct 936 flybacks, but phase variation is
  about 0.24 line; the limit is 0.01. See `lock-scan.json`. Each trial ran eight
  fields (156 ms), using the same declared T3/yoke hypotheses.
- The 53 local perturbation solves separate amplitude and solver refinement.
  Oscillator amplitude changes converge, but its last timestep comparison is
  still 1.44%, and pre-perturbation waveform settling fails. None of the four
  combined phase-sign screens is usable. These results cannot reject a T3
  polarity. See `loop-response/response.json`.

The first emission probe used microvolt-scale signals and produced a negative
sample near -0.97 microamp. That rejected pass led to the explicit 1 V/microamp
probe now used by the connected diagnostic. BJT and rectifier energy accounting
was also changed to direct terminal-current probes. Small RC, RL, mutual-inductor,
ideal-transformer and semiconductor fixtures validate the ledger independently.

## Energy window scope

`energy-coarse/` and `energy-fine/` contain the same connected circuit over one
**transient** 19.5 ms field, at 200 ns and 100 ns maximum steps respectively,
with tighter tolerances in the fine run. These windows test signed work and
storage accounting. They do not establish a periodic warmed state or waveform
agreement between independently initialized full-length runs.

The coarse residual is 1.155%, above the 1% limit. The fine residual falls to
**0.168%**, passing the energy-window check; its terminal-work relative error is
1.17e-9. This is a successful transient energy audit, not full-frame acceptance. Its terminal-work residual is
only 0.000647%, localizing the remaining discrepancy to numerical storage/work
integration. The final reports use net source delivery/absorption as their scale;
cancelling internal ideal-transformer transfers cannot inflate that denominator.

An earlier four-field fine solve produced duplicate timestamps with different
samples at 39 ms. Strict raw validation rejected it; it is not refinement
evidence. The terminal probes and single-field audits do not prove that this
multi-field issue is resolved. No timestamp or waveform was fabricated to make
it pass.

The exploratory outer feedback run was stopped after identifying the unlocked
input state; its initial collection is retained, and the interrupted coupled
solve is not acceptance evidence. The production feedback entry point now
requires a synchronized periodic input state before starting that iteration.

## Reproduce an energy window

From the repository root, with the pinned runtime installed:

```python
from pathlib import Path
import json, sys
sys.path.insert(0, 'verification/robotron-monitor')
import steady_supply, energy_ledger
source = Path('verification/robotron-monitor/examples/single-frame-accounting-audit/energy-coarse')
out = Path('build/monitor/reproduce-terminal-energy')
steady_supply.solve((source/'run.cir').read_text(), out,
                    Path('build/monitor/runtime-clean'), timeout_s=900)
metadata = json.loads((source/'metadata.json').read_text())
ledger = energy_ledger.assess(out/'trace.raw',
    json.loads((source/'inventory.json').read_text()), start_s=0, end_s=.0195,
    core=metadata['candidate']['numerical_parameters']['core'])
print(ledger['relative_error'], ledger['accepted'])
```

Use `energy-fine` and a fresh output directory for the refined audit. Exact decks
for all connected trim trials and isolated response perturbations are also
included. `audit.json` hashes the archived evidence. The broader acceptance
requirements and model limitations are documented in
[the acceptance description](../../single-frame-acceptance.md).
