# MB001 per-chip RAM experiments

Continuation of the first component-fault campaign, 2026-10-27.
**The best result is an 82-fetch prefix, not a complete reproduction.**

## Stronger observations

[mb001-full-reads.json.gz](mb001-full-reads.json.gz) preserves all **13102 complete
fetch-to-fetch intervals** from the seven valid physical captures. Each interval
now includes the actual bytes of additional CPU /RD cycles, not merely their
count. Data is sampled two analyzer samples before the read ends. The earlier
end-minus-four value is retained for fetches to expose settling differences.
Capture SHA-256 values retain the connection to inventory evidence.

Regenerate with:

```sh
python3 verification/pc1715-faults/extract.py \
  ../vintage-computer-inventory/items/MB001-robotron-pc1715/evidence \
  verification/pc1715-faults/mb001-full-reads.json.gz --read-data --limit 0
```

The native probe now preserves operand, memory and I/O-read bytes too. Comparison
requires matching these bytes alongside fetch bytes, clocks and read counts.
ROM enable levels additionally constrain only the last physical capture, where
they were measured. Several earlier opcode-only prefixes fail this stricter
comparison sooner. The original campaign remains archived at commit `d3047c88`;
its model/source hashes refer to that version, not the extended probe.

## New fault models

The eight RAM data bits are independently stored for the selected faulted bit.
Its address can alias differently on reads, writes or both. Its write input can
be normal, disabled, held low/high or inverted; its read sense can be inverted.
The other seven bits retain ordinary RAM write data and the common address map.
An optional single transition between write-fault modes is specified in CPU
clocks, independently of fetch count or captured data.

These are functional abstractions of per-chip address/data/write-path failure,
not claims that a particular real IC has those faults. Read-only and write-only
address transformations stand for asymmetric address capture; they do not
describe a simple physical pin short that would necessarily affect both.
The current per-bit address transform follows the common RAM alias transform.
It cannot yet represent one RAM chip retaining address bits already lost by
the other seven; this is an explicit modeling limitation.

The new regular startup pattern is:

```
RAM[a] = (a & 1 ? FF : 08) XOR (a & 2 ? E7 : 00)
```

This repeats `08 FF EF 18` throughout RAM. The related EF XOR case changes D3
in alternate pairs. The campaign also tries inverted D3 read sense with the
corresponding regular initial pattern. These are unmeasured initial-state
hypotheses, selected using the early trace evidence. No RAM location is filled
with a captured opcode, and no timed opcode/data stream is supplied to the CPU.
Nevertheless, this is parameter fitting to the same captures, not independent
validation of real power-on RAM contents.

## Results

Three sweeps each tested **22260 configurations**, totaling **66780**. A
256-clock screen promotes any candidate matching at least 16 intervals to a
12000-clock run compared against the entire supplied capture. A guard verifies
that the first 16 observed intervals fit inside the screen. No candidate passed
the complete observation.

| Physical run | Original striped RAM, strict read-byte comparison | Regular E7 XOR pattern | Regular EF XOR pattern |
| --- | ---: | ---: | ---: |
| Reset run 1 | 9 | 11 | 11 |
| Reset run 2 | 9 | 11 | 10 |
| Reset run 3 | 9 | 11 | 11 |
| Reset run 4 | 9 | **82** | **82** |
| Reset run 5 | 7 | 7 | 7 |
| Restored-CH10 run | 7 | 7 | 7 |
| ROM-control run | 7 | 7 | 7 |

Numbers are consecutive complete intervals from the first fetch, including all
recorded read bytes. They are not totals of scattered matching samples. Models
were ranked separately for each run; this table does not establish that one
unchanged fault reproduces all power cycles.

### The simplest 82-fetch candidate

- ROM decoder remains inactive: ROM outputs disabled and underlying RAM admitted.
- Common RAM addresses alias to the low five bits (32-byte repetition).
- Startup RAM repeats `08 FF EF 18`.
- The D3 chip's writes never take effect; its initial bits remain.

The ordinary CPU and stack writes generate **127 matching read bytes over 585
CPU clocks**, approximately 238 us at the measured clock rate. Fetches, operand
values, additional memory reads and durations all agree through interval 82 of
run 4. The first mismatch is interval 83: simulated `4A`, observed `42`. The next
is simulated `08`, observed `00`; these are D3 differences. The first model
address at divergence is logical 0057, but no hardware address was captured to
confirm that address.

This candidate predicts `/CE=0,/OE=1`; those levels were not measured during run
4, so they are a prediction, not part of that 82-interval verification. Against
the actual ROM-control capture, this same candidate matches only five intervals.
Other per-bit candidates reproduce seven intervals there, including the early
`F7`, but then fail. This distinction prevents treating a match from another
power-up as a reproduction of the latest measurement.

A further 601-case control changes the D3 write behavior from disabled to
stuck-low at one chosen CPU clock, 0 through 600. It does not extend the best
82-interval match. A single delayed write-path failure of that form is therefore
insufficient under this initialization/address model.

## Reproduce and inspect

```sh
make test-pc1715-faults
python3 verification/pc1715-faults/bit_campaign.py \
  --rom /path/to/r1715bt.bin \
  --hardware verification/pc1715-faults/mb001-full-reads.json.gz \
  --xor-mask 0xe7 --output build/mb001-xor-full-campaign.json.gz
python3 verification/pc1715-faults/qualify_bit_model.py \
  --rom /path/to/r1715bt.bin --output build/mb001-bit-qualification.json.gz
```

Omit `--xor-mask` for the original stripes; use `0xef` for the alternate pattern.
The historical ROM is not redistributed. Its required hash is unchanged.

Complete compressed results are in [bit-results/](bit-results/): three campaigns,
their readable summaries, and the qualification report containing the complete
forward simulation and the 601-case timed control. Source and fixture hashes
identify the inputs. The new tests cover bit isolation, asymmetric addressing,
startup patterns, clock-based transitions, operand-byte capture and rejection
of wrong operands despite matching fetches/timing. Address/undefined-behavior
sanitizer and existing plain-PC1715 tests also pass.

The next useful modeling change is to separate the per-chip address paths before
the common alias loses information, and then constrain those paths using the
actual DRAM address-multiplexer wiring. Repeating the same mask sweep cannot
resolve that missing behavior. Hardware address observations would also reduce
the number of plausible but unverified fault combinations.
