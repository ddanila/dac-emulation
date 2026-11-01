# MB001 fault-mechanism comparison, 2026-11-01

**Result:** two later, bounded capture windows are reproduced by forward fault
models. No fixed tested configuration explains all18 recordings. This supports
mechanisms, not calibrated probabilities for individual physical components.

## Evidence and method

The existing ordinary-PC1715 native CPU/memory model and fault probe were used
unchanged. Pico1715 firmware/adapter tests and the PC1715M model are not substituted
for this board. `hypothesis_campaign.py` compares438 configurations in14 families
against22852 complete fetch intervals from18 valid recordings:

- Seven October27 captures from the previous campaign.
- Eleven October28–31 captures, excluding the invalid all-zero acquisition and
  the aborted acquisition without raw data.

Every comparison begins at the first qualified fetch, and checks all available
intervals: connector byte, clocks to next fetch, additional read count and bytes,
and ROM CE/OE where recorded. No favorable alignment search is used. Each model
runs12000 clocks. The last incomplete fetch interval is excluded from both
comparison boundaries as appropriate to the extractor/comparator.

**All channels15 and higher are excluded**, including the inconsistent CPU/latch
A15 and control readings. They are not scored, used to select candidates, or
used to reject an otherwise matching model. The continuing reliance on CH1–14
is explicit: the data, clock, reset, M1/RD and ROM-control observations must be
usable for this analysis to apply. A second comparison removes ROM CE/OE too.
It leaves the main family ranking and the two full-window matches unchanged.

RAM initial states are zero, FF, two deterministic pseudorandom seeds, and four
regular striped/four-byte patterns. These are hypotheses, not measured RAM
contents or a calibrated distribution of DRAM power-on states. The short
`00 FF` trace motivated including that regular pattern; its fit is retrospective.
No captured instruction stream is fed to the CPU and no individual cells are
loaded with captured bytes.

## Compatibility results

Prefixes below require data, operands, timing and available ROM controls.
Per-family maxima may select different parameters for different runs; they are
**not** a single jointly successful explanation. Medians describe prefixes over
18 recordings and are not probabilities or independent-trial success rates.

| Family | Configurations | Median best prefix | Maximum best prefix | Entire bounded capture matched |
| --- | ---: | ---: | ---: | --- |
| Healthy / RAM startup state only | 8 | 0 | 0 | None |
| RAM driving alongside ROM, low-dominant resolution | 8 | 0 | 0 | None |
| ROM decoder inactive, RAM admitted | 8 | 7 | 261 | Oct31 reseated |
| AB15 forced high | 8 | 7 | 261 | Oct31 reseated |
| One of AB11–AB14 forced high | 32 | 7 | 261 | Oct31 reseated |
| High address byte frozen | 32 | 7 | 199 | None |
| Multiple high address bits forced high | 24 | 7 | 71 | None |
| Inactive ROM decoder plus RAM alias | 24 | 7 | 71 | None |
| Above plus ineffective D3 writes | 24 | 9 | 358 | Oct31 decoder comparison |
| ROM output disabled only, RAM still inhibited | 63 | 2 | 2 | None |
| Buffered RD missing / undriven reads | 63 | 2 | 2 | None |
| ROM CE inactive | 63 | 0 | 2 | None |
| CPU/connector data path open | 63 | 0 | 0 | None |
| ROM read-data bits clamped | 18 | 0 | 0 | None |

No decoder/control-fault family in this table models analog contention voltages,
complete display DMA timing, or individual IC leakage. An address forced high
is a functional effect that could arise at a latch, another bus driver, a short,
or elsewhere. The table cannot distinguish those physical locations.

### Simple capture: ROM not selected, RAM visible

`20261031-a15-reseated` contains262 fetch windows, yielding261 complete intervals
and261 read bytes over1954 clocks. The entire bounded observation is reproduced
with regular initial RAM `00 FF 00 FF ...` by each of six alternatives:

- ROM decoder inactive, no extra RAM alias.
- Any one of AB11, AB12, AB13, AB14 or AB15 forced high.

The healthy CPU executes NOP/RST instructions from RAM. A single forced high
address bit is enough to bypass ROM; no defective CPU or special RAM read fault
is required for this recording. The matching alternatives remain indistinguishable
on the scored signals. Specifically, AB15 cannot be singled out when disputed
address probes are excluded. This repetitive two-opcode trace is less discriminating
than the next result, despite its length.

### Richer capture: frozen earlier candidate predicts a later window

`20261031-a15-decoder-compare` contains359 fetch windows and358 complete intervals:
**471 read bytes over1958 clocks**, about0.8ms. The model reproduces every complete
interval, including ROM CE=0/OE=1, with:

- inactive ROM decoder admitting RAM;
-32-byte RAM alias;
- regular initial pattern `08 FF EF 18`;
- D3 writes disabled.

The parameters **and entire12000-clock forward simulation are exactly identical**
to the archived October27 qualification. The script asserts that identity.
This is a retrospective evaluation on a later recording using an already frozen
candidate, not a newly fitted cell image. It is stronger evidence for the
stack-write/self-modifying-RAM mechanism than the earlier82-fetch prefix.
It is not an independent bench validation of the assumed initial RAM contents,
a demonstration of one failed IC, or reproduction beyond the measured window.

The same fixed candidate still fails most other runs early: at prefixes0–15 in
16 recordings,82 in the earlier run4, and358 in this later recording. The other
full match (the `00 FF` trace) uses a different candidate. Thus variable startup
state, additional/unmodeled circuit behavior or residual observation limitations
remain necessary to explain the collection; they have not been solved here.

## What probabilities can and cannot be inferred

A posterior component probability requires a prior failure rate and a likelihood
that integrates over unknown RAM state, analog bus behavior, timing, noise and
fault severity. None is calibrated here. Parameter counts, matching-prefix
fractions, and arbitrary scoring formulas must not be relabeled as
hardware probabilities. A noiseless likelihood for each fixed tested model on
all18 full observations would be zero: normalizing those zeros cannot rank the
physical causes. Adding an arbitrary noise penalty would manufacture a result.

The defensible relative assessment is:

1. **Strongest support: failed ROM selection with RAM responding.** This explains
   complete bounded observations and is consistent with ROM controls. Address
   buffering/latching, competing address drivers and decoder logic remain tied
   as possible physical causes where they produce the same observable bus state.
2. **Additional support, but more assumptions: RAM addressing/write effects.**
   Ordinary stack writes into aliased RAM explain the richer sequence, with a
   previously frozen candidate now matching a later whole short window. That
   supports this functional mechanism without proving failed RAM chips.
3. **Weak support as a complete explanation: only ROM output/CE failure or
   missing buffered RD with a floating bus.** Fixed/held/decaying policies tested
   here fail within two complete intervals. Untested analog behavior is not ruled out.
4. **Poor support in tested forms: RAM corruption alone, static ROM data clamps,
   or an open CPU-to-connector data path.** These do not explain the first
   observed intervals. A defective CPU is not required for the matched traces,
   but CPU defects were not exhaustively modeled and are not assigned a zero probability.

## Reproduce and inspect

```sh
make build/pc1715-fault-probe test-pc1715-faults test-pc1715
python3 verification/pc1715-faults/hypothesis_campaign.py \
  --rom /path/to/r1715bt.bin \
  --evidence ../vintage-computer-inventory/items/MB001-robotron-pc1715/evidence \
  --output verification/pc1715-faults/hypotheses-20261101
```

The ROM hash is enforced. [observations.json.gz](hypotheses-20261101/observations.json.gz)
retains each raw-capture hash and extracted intervals;
[campaign.json.gz](hypotheses-20261101/campaign.json.gz) preserves every case,
control-free sensitivity scores, each family's best full simulation per run,
source hashes, and the frozen-candidate check.
[summary.json](hypotheses-20261101/summary.json) provides per-run results.
The20 existing fault tests and native PC1715 suite pass. No hardware operations
or new measurements were performed for this analysis.
