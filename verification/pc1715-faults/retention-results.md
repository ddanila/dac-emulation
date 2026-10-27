# MB001 row-retention experiment

This experiment follows the static D3-state contradiction in
[bit-results.md](bit-results.md). It tests a bounded, deterministic weak-row
hypothesis; it is not an analog DRAM model or identification of a failed chip.

## Circuit constraints

The [PC1715 service manual](https://xepb.org/robotron/docs/pc_serv.pdf),
section 1.2.6, printed pages19–20, describes 16K×1 DRAMs arranged in four banks:

- AB0–AB6 are the row address, captured on falling /RAS.
- AB7–AB13 are the column address, captured on falling /CAS.
- A28.1/A28.2 multiplex the two address halves; A33.1 generates their WS select.
- A10.1 decodes AB14/AB15 into four bank /CAS signals.
- /RAS reaches every DRAM; a RAS-only cycle needs only a row address to refresh.
- Read, write and refresh cycles restore rows. All128 rows must be visited
  within2ms for the memory types listed in that manual.

The [Zander schematic redraw](https://www.sax.de/~zander/pc1715/pc_zres.pdf),
sheet2, corroborates the address multiplexers, bank decoder and shared /RAS.
The manual lists U256/K565RU4A/K565RU3G and equivalents; the owner reported RU6
on MB001. This experiment follows the documented board organization. It does
not establish the precise retention characteristics or revision of MB001's ICs.

Local source hashes (SHA-256):

- Service manual: `c356e50a5499a0fb9a0a204e833eb47406dd5f2d0246c26e27320eec6b8b1d49`
- Schematic redraw: `d96efdeeefcf214c7f5044c03ff5165203bc7781afd0852e8de94b623c5b5c63`

## Model and limits

`retention_campaign.py` instruments a temporary native-probe build. On a row
access, if more than the selected retention limit has elapsed since that row
was restored, D3 is cleared throughout its columns and banks. The row is then
restored. Other data bits are unaffected. This assumes one uniform decay time
and polarity for the selected bit plane; real weak cells need not behave so.

Memory reads and writes restore rows. CPU /MREQ+/RFSH bus cycles optionally
restore rows too, at their actual native-Z80 timing and row address. The same
common RAM address fault applies to refresh addresses. There is no invented
refresh timer. This wrapper does not model analog strobes, WS propagation,
per-cell leakage, or display DMA refresh. Every row starts freshly restored at
model cycle0; actual power-on charge ages are unmeasured. The initial RAM byte
pattern remains the existing regular pattern, never captured opcodes.

Tests verify that restoring one row preserves it before the deadline, expiration
clears D3 across columns/banks, and a different row is unchanged. Disabled decay
and a long retention limit preserve the entire previously qualified simulation,
with CPU refresh either enabled or suppressed. The production probe is unchanged.

The sweep covers 32/64-byte common aliasing, the E7/EF startup patterns, CPU
refresh enabled/suppressed, and limits1–640 clocks plus4916 clocks (2ms at the
model's2.458MHz). D3 writes remain disabled as in the original candidate.
All5128 cases run12000 clocks and compare all seven observations, including
additional read data and timing. No capture bytes enter the forward model.

Reproduce:

```sh
make build/pc1715-fault-probe
python3 verification/pc1715-faults/retention_campaign.py --rom /path/to/ROM \
  --output verification/pc1715-faults/bit-results/retention.json.gz
```

## Results

No configuration reproduces a complete capture. Best strict prefixes by capture:

| Capture | CPU refresh suppressed | CPU refresh active |
| --- | ---: | ---: |
| Reset1 | 12 | 12 |
| Reset2 | 10 | 10 |
| Reset3 | 12 | 12 |
| Reset4 | **83** | 82 |
| Reset5 | 7 | 7 |
| Restored wiring | 5 | 5 |
| ROM controls | 5 | 5 |

The best run4 candidate uses the32-byte alias, E7 pattern and retention480–486
clocks (about195–198µs) with CPU refresh suppressed. It matches83 complete
intervals over589 clocks, then produces`08` at inferred address0058 where the
capture has`00`. Normal row reads keep that cell restored; shortening a uniform
retention threshold enough to clear it damages earlier matches. No case with
CPU refresh active exceeds82 intervals. The nominal2ms control retains the
original82-interval prefix for the best startup pattern.

The slight improvement is a fitted weak-row hypothesis, not proof of DRAM decay.
It still needs the earlier decoder/address/write faults and an unmeasured
startup pattern, and cannot explain the full run. Arbitrarily assigning each
cell a different retention time would add unconstrained fitting parameters.
The archived [retention.json.gz](bit-results/retention.json.gz) contains all case
parameters/scores and the best complete forward simulation per capture, plus
source/fixture/ROM hashes. The row-state tests and all four nondecaying controls
passed; the existing20 fault tests and native plain-PC1715 suite also pass.

The next physically constrained alternative is the address multiplexer itself:
a stuck WS select repeats one address half in both row and column, rather than
simply clamping a contiguous set of CPU address bits. That mapping has not yet
been tested by the existing alias sweeps.

The follow-up [multiplexer experiment](mux-results.md) tests these select faults,
including A28.2's effect on /CAS; it does not improve the prefix.
