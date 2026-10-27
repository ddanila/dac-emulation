# PC1715 component-fault experiments against MB001

This uses the existing `machines/robotron1715` motherboard, shared Z80 CPU,
normal instruction execution and actual modeled RAM writes. A verification-only
bus wrapper injects explicit faults. Normal emulation is unchanged.

**Status: partial behavioral reproduction, not a diagnosed physical fault.**
No tested hypothesis reproduces a complete captured startup. The first campaign
contains 2466 configurations and compares each against seven physical traces.
The best prefix is eleven fetches in one trace, including duration and additional
read counts. The ROM-controls capture matches only five initial fetches before
its observed `F7` differs. See [results.json](results.json) and
[the complete compressed campaign](campaign.json.gz).

## Inputs and reproducibility

```sh
make build/pc1715-fault-probe test-pc1715-faults
python3 verification/pc1715-faults/campaign.py \
  --rom /path/to/r1715bt.bin --output build/mb001-fault-campaign.json
```

The campaign requires the recorded 2048-byte ROM with SHA-256
`51cb80639b5667f2611da71ce7305061566cf3474bda7db6fc82709d08e46d01`.
It is not redistributed. The healthy baseline starts `21 11 01 18 ED B0 ...`
with the expected operand reads and instruction durations.

[mb001.json](mb001.json) contains the first 128 complete fetch intervals of each
physical capture, its raw decompressed capture hash, and extraction method.
The source is the owner's
[MB001 inventory evidence](https://github.com/ddanila/vintage-computer-inventory/tree/main/items/MB001-robotron-pc1715/evidence),
through inventory commit `e9348ea`. Only the final capture includes ROM pin18 and
pin20 controls. The historical CH13/CH24 mix-up is excluded from these fixtures.

To regenerate the fixture:

```sh
python3 verification/pc1715-faults/extract.py \
  ../vintage-computer-inventory/items/MB001-robotron-pc1715/evidence \
  verification/pc1715-faults/mb001.json
```

The comparator begins at the first fetch. It compares data, clock-edge count to
the next fetch, extra CPU /RD pulses, and ROM controls where measured. It does
not search for a favorable alignment or equate byte-only matches with execution
matches. A short simulated trace cannot pass. The final simulated interval is
excluded because it may be incomplete. Rejecting a candidate within the initial
128 windows also rejects full-trace reproduction; a future candidate passing
this screening still needs comparison against the entire captured window.

No hardware byte stream enters the native model. RAM begins as zero, FF,
deterministic xorshift32 data, or a documented uniform stripe pattern. The
parameters were selected during investigation, so a matching prefix is a fitted
hypothesis, not independent validation. No individual RAM cells are initialized
from observed opcodes.

## Fault boundaries

| Experiment | Intervention |
| --- | --- |
| `rom-oe-high` | Only ROM output inhibited; normal overlay still inhibits low RAM reads |
| `rom-ce-high` | ROM chip input forced inactive; logical overlay unchanged |
| `rd-buffer-high` | ROM and RAM read drivers unavailable; CPU writes still work |
| `address-mask` | Specified external address bits tied on both reads and writes; changes decode and physical RAM address |
| `data-mask`, `rom-data-mask` | Specified read-data bits clamped; the latter affects ROM-driven data only |
| `data-buffer-open` | CPU and connector data separated; RAM reads/writes cannot cross the buffer; CPU-side ROM remains accessible |
| `ram-contention` | RAM drives during ROM reads; explicitly assumed low-dominant resolution |
| `decoder-ram-alias` | ROM decoder output inactive, RAM admitted, plus specified RAM-address aliasing |
| `decoder-ram-alias-d3-high` | Above, plus D3 forced high on RAM reads |

These are functional failure boundaries, not a transistor-level netlist.
`decoder-ram-alias` combines two hypotheses; its D3 variant combines three.
An address-mask affecting multiple chips is not evidence of a single failed IC.

Floating reads can return a fixed bias, retain the last driven byte, or retain
it until a specified number of CPU clocks and then settle to a bias. CPU stack
writes update that history. Initial bus value is explicit. These policies bracket
unknown electrical behavior; none claims measured capacitance or threshold.
The core samples at whole CPU clocks and cannot reproduce sub-clock settling.

The ROM control outputs in the experiment are logical values at memory-read
transactions, not continuous pin waveforms. Reset is CPU-core initialization;
absolute reset-release-to-first-fetch timing is not predicted. ROM addresses,
driver voltages, CPU-side data, RAM startup state, display DMA and bus contention
were not measured sufficiently to qualify an electrical reproduction.

## Results that change the next investigation

1. **ROM output disabled alone is insufficient under the tested bus policies.**
   FF bias produces repeated eleven-clock RST 38h; 08 bias produces four-clock
   EX AF,AF'. A decaying bus can produce `08 FF` but fails the third fetch.
   The best prefix among those cases is two, despite matching `/CE=0,/OE=1`.
2. **Aliased stack writes naturally generate the later `3A`.** With alternate
   RAM bytes 08/FF and RAM reduced to a repeating low-address window, execution
   begins `08 FF 08 FF 08 FF 08 3A`. Three RSTs push return addresses; the last
   low-byte write aliases onto the instruction at logical 0039. No code byte is
   injected at that moment. Subsequent reads and timing also arise from the CPU.
3. **High address-driver faults can combine missing ROM selection with RAM
   aliasing.** For example, tying A6–A15 high maps logical 0000 to FFC0, misses
   ROM decode and makes stack writes overlap the same 64-byte RAM window. It
   reproduces the eight-byte prefix with the same alternating RAM hypothesis.
   This is an example parameter set, not identification of those ten real lines
   as faulty. Several alias widths are indistinguishable over the early prefix.
4. **Constant D3 faults extend some prefixes, but do not explain the traces.**
   They cannot reproduce the later changing D3 values or the newest run's first
   `FF -> F7` difference. The fit breaks by fetch 12 even in the best case.

The failed hypotheses are retained alongside the partial matches. In particular,
simulating a disconnected ROM as “read FF” is not sufficient to explain this
board. The next model work is to constrain address-driver/DRAM-multiplexer faults
from actual connectivity and test time-dependent RAM/data-path behavior, without
introducing a prescribed instruction stream. Hardware observation of the ROM's
address inputs at the first fetch would sharply distinguish wrong-address
decode from a decoder/control failure with the correct address present.

## Circuit evidence

The [ZRE schematic, sheet 1](https://www.sax.de/~zander/pc1715/pc_zres.pdf)
places boot ROM A25.3 on CPU data D, with A22.3 between D and connector DB. The
redraw shows A10.2 output0 feeding ROM pin20 and the distributed /PROMCS path;
pin18 is associated with the boot-enable latch. The
[service manual](https://xepb.org/robotron/docs/pc_serv.pdf), sections 1.2.5/1.2.6,
describes the decoder output inhibiting RAM and controlling bus direction during
ROM reads. The manual calls the PROM input CE; this report uses physical pin
numbers and the redraw rather than conflating the naming.

Thus a disconnected ROM pin20 and an inactive shared decoder output need not
have the same RAM/buffer consequences. The logical experiment represents that
distinction, but full gate timing and every interconnect remain unmodeled.

## Validation

`make test-pc1715-faults` uses original synthetic ROMs and independently expected
CPU/program outcomes, including stack-write feedback, address aliasing, control
levels, comparison rejection and malformed inputs. It needs no historical ROM.
The existing plain-PC1715 and full native test suite also passed. The fault probe
was additionally run with address/undefined-behavior sanitizers. Results record
ROM, hardware-fixture and model-source hashes for reproducibility.
