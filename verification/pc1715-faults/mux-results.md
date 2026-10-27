# MB001 address-multiplexer faults

The preceding [retention experiment](retention-results.md) reached83 matching
intervals but did not reproduce a complete capture. This follow-up tests the
address multiplexers directly, rather than replacing their behavior with a
contiguous address mask.

## Schematic-derived behavior

The [Zander PC1715 schematic](https://www.sax.de/~zander/pc1715/pc_zres.pdf),
sheet2, shows two DL257/K531KP11 multiplexers:

- A28.1 selects AB0–AB3 versus AB7–AB10, feeding DRAM address pinsA0–A3.
- A28.2 selects AB4–AB6 versus AB11–AB13, feeding pinsA4–A6.
- A28.2's fourth channel selects a pulled-high inputA3 (R8.20) versus groundB3.
  Its output feeds the /CAS delay/decoder path; it is not another address bit.
- AB14/AB15 select the bank through A10.1.

Consequently, a select stuck low on A28.1 duplicates the low address bits into
both row and column; stuck high duplicates the corresponding high bits instead.
The same applies to A28.2's three address channels. However, A28.2 select stuck
low also holds /CAS inactive, suppressing RAM reads and writes. A global WS
stuck-low case must not be treated as a working RAM with a duplicated address.

This is an idealized functional latch model. A select held high can assert /CAS
at abnormal times; gate delays and DRAM timing violations are not simulated.
No exact MB001 component fault is diagnosed from the redraw.

## Experiment

`mux_campaign.py` builds a temporary instrumented native probe; the production
probe is unchanged. All nine combinations of normal/low/high select on the two
packages are tested. The sweep also covers:

- no extra address mask, bank bits clamped low, or the earlier32/64-byte aliases;
- six regular startup patterns along either the row or column address bits;
- five D3 write behaviors: normal, disabled, low, high or inverted.

The existing inactive-ROM-decoder hypothesis remains in every case. Undriven
RAM reads use the existing fixed-FF policy; alternative floating-bus policies
were explored separately in the original campaign. No captured byte stream is
supplied to the CPU. All1080 configurations run12000 clocks and are compared
against all seven observations, including additional read bytes and timing.

An exhaustive pin-level check verifies every16-bit address in all nine mux
settings, independently assembling the expected row/column bits. A second
check verifies that A28.2 stuck low prevents writes and leaves reads undriven.
Normal mux operation must reproduce the entire previously qualified native
simulation exactly. All these checks passed.

## Results

No case reproduces a complete capture. Run4's best strict prefix by mux setting:

| A28.1 select | A28.2 normal | A28.2 low | A28.2 high |
| --- | ---: | ---: | ---: |
| Normal | 82 | 0 | 12 |
| Low | 82 | 0 | 12 |
| High | 1 | 0 | 1 |

The unchanged82-fetch result still requires the earlier shared alias and D3
write fault. A28.1 held low can preserve that prefix, but does not solve its
first divergence. This family does not improve on the retention model's83.
A zero score for suppressed /CAS reflects the selected fixed-FF undriven
policy, not proof that a real undriven bus must read FF.

[bit-results/mux.json.gz](bit-results/mux.json.gz) archives every configuration
and score, the best forward run for each observation, and source/fixture/ROM
hashes. Reproduce with:

```sh
make build/pc1715-fault-probe
python3 verification/pc1715-faults/mux_campaign.py --rom /path/to/ROM \
  --output verification/pc1715-faults/bit-results/mux.json.gz
```

## Evidence needed before further fitting

The bounded component families tested so far do not reproduce the complete
hardware behavior. The next defensible step is to constrain the real memory
accesses, rather than add arbitrary per-cell state or time parameters:

- Address bits during the early RST/stack sequence would test whether inferred
  CPU addresses and the shared alias are valid.
- /WR together with RAM /RAS and the relevant bank /CAS would test whether
  writes and row/column selection actually reach RAM.
- CPU-side data versus buffered X2 data would test the assumption that sampled
  connector bytes are exactly the bytes consumed by the CPU.

These signals are absent from the present observations. The notes describe
measurement objectives, not verified clip locations or a rewiring instruction.
Hardware remains off. No complete reproduction or physical diagnosis is claimed.

The earlier October22 four-address-line capture was subsequently located and
archived in the inventory's
[unattributed evidence](https://github.com/ddanila/vintage-computer-inventory/tree/main/evidence/unattributed-pc1715/20261022-address-low).
It has1159 complete M1 intervals, but lacks simultaneous data and strobes,
has no verified reset-start anchor, and cannot be reliably assigned to the
current MB001 board/ROM/CPU configuration. It is excluded from this model's
comparison fixture. Checking the historical archive did not close the evidence
gap; further model discrimination needs a new measurement under the known setup.
