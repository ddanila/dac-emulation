# Shared runtime and verification

Juku and Robotron 1715M now use one session runtime and one native scenario
runner. The existing DAC browser ABI and native replay format remain compatible.
This is the next verification layer after extracting the machine cores; it does
not replace CPU/device models or assert that two different machines behave alike.

## Ownership

- `common/runtime/session.[ch]` owns sessions, firmware/media copies, lifecycle,
  input, bounded stepping, video and existing same-build snapshots. Native replay
  and WASM compile this same source. `runners/browser/dac.[ch]` are forwarding
  compatibility paths; never link the forwarding C file and canonical C file
  together. Snapshot compatibility still requires the original core build.
- `common/runtime/observe.h` adds verification ABI 1: side-effect-free backing
  memory inspection, CPU observation and optional trace sinks. The browser does
  not need to export these functions. Callbacks must not reenter/mutate sessions.
- `verification/` supplies a standard-library Python native binding, versioned
  scenario runner and trace comparator. It contains no CPU/peripheral emulation.
- `machines/*` own mapping, devices, interrupt wiring and fault behavior.
  Machine HDL adapters and physical evidence stay in `8080-cosim`.

There is no plugin loader or new universal bus model. Existing Juku native
PTY, fault-injection, pacing and checkpoint workflows retain their entry points.
Their specialized controls have not been silently mapped to Robotron.

## Run a scenario

Python 3.10+ and a C11 compiler on Linux/macOS suffice. No external firmware,
HDL tool or Python dependency is needed for the examples or fast tests.

```sh
make -j4 test
python3 -m verification.scenario examples/scenarios/juku-memory.json --output out/juku-a
python3 -m verification.scenario examples/scenarios/juku-memory.json --output out/juku-b
python3 -m verification.compare out/juku-a/trace.jsonl out/juku-b/trace.jsonl
python3 -m verification.scenario examples/scenarios/robotron-memory.json --output out/1715m
```

Output directories must be new. Reports record the exact scenario hash, loaded
firmware/media byte hashes, runtime binary hash, compiled source identity,
profile, actual clocks advanced, stop reason, observations and trace hash.
Failures write an error and completed/partial step evidence with a nonzero exit.
Dirty builds are identified as such; the binary hash remains authoritative.
An existing library is not relabeled with the current checkout's revision.

The example ROM bytes are original tiny 8080/Z80-compatible programs:
`MVI A,42h; STA 8000h; HLT`. They exercise the real CPU cores. Both scenarios
wait for the write, assert it, advance through HALT, reset, check cleared RAM
and wait again. The Robotron CAS bytes are synthetic and used with bank zero;
they are not a physical board's PROM dump.

### Scenario version 1

The JSON object requires `schema: "dac-scenario-1"`, `machine` (`juku` or
`robotron1715m`), `firmware` and `steps`. It optionally accepts `disks` and
`trace_limit`. Unknown fields/operations fail instead of being ignored.

Firmware maps string slots to either `{"path": "relative/to/scenario.bin"}`
or `{"hex": "3e4232008076", "size": 16384}`. Inline bytes are zero-padded to
size; external images must have the exact size accepted by the runtime.
Slots retain the existing session contract: boot ROM 0, Robotron CAS PROM 1,
character data 2 and optional keyboard ROM 3. Historical images remain external.
Disk entries are `{ "unit": 0, "path": "disk.img", "writable": false }`.
Writes affect only the session copy; this runner does not export/overwrite disks.

Each step contains exactly one operation:

| Operation | Argument / meaning |
| --- | --- |
| `run` | Positive CPU-clock budget; report actual clocks advanced |
| `until` | `{space, address, hex, limit}`; stop at a matching memory condition or fail at the emulated limit |
| `expect` | `{space, address, hex}`; immediate memory assertion |
| `key` | `{code, down}` using the existing machine-specific key contract |
| `reset` | `true`; existing session reset, retaining mounted session media |

`space` is `ram`, `rom` or `video`. Addresses are offsets into physical backing
arrays: Robotron RAM bank N starts at `N*65536`. Reads do not perform bus
transactions, refresh RAM, consume I/O or emit traces. No guessed common register
set, debugger I/O reads or arbitrary memory writes are exposed. CPU observations
report clocks, PC, SP, HALT and the machine's bank/mode selector. A Z80 PC sampled
mid-instruction is not claimed to be an instruction-retirement address.

Juku steps at instruction boundaries and may overshoot a budget by its last
instruction/interrupt effects. Robotron steps in clocks. An `until` predicate is
checked after each such machine step, including the final step's possible
overshoot. It can match immediately with zero advancement. The runner records
actual advancement and never pretends the stepping granularities are equal.
Reset starts a new trace epoch, making clock resets explicit.

Native run slices are bounded, and `--wall-timeout` (default 30 seconds) is
checked between slices/steps. This is a cooperative deadline, not a subprocess
watchdog for a hung C function. Each step has at most 10^9 clocks, scenarios at
most 10,000 steps, and a trace at most 10^6 events. Trace overflow fails the run
and marks the artifact incomplete; it cannot silently pass a comparison.

## Trace contract and comparison

`dac_trace_event` retains kind/address/data/cycle/source and adds master, backing
space and offset. Source identifies the machine; master distinguishes CPU and
DMA. Existing Juku text output is unchanged. Juku still supplies logical bus
addresses without mapped-space assertions. Robotron emits MR/MW/IR/IW/IA,
including distinct physical read/write banks and DMA attribution. Unmapped
accesses explicitly have unknown backing space. Offsets identify storage,
not a second guest address. Events describe core access callbacks, not sampled
physical pin edges or a promise of peripheral cycle accuracy.

The JSONL header identifies `dac-trace-1`, machine, inputs, stepping/timing
profile, whether capture was enabled and whether it is complete. Comparisons
require nonempty complete captures from the same machine and input identities.
They report the first differing event (zero-based) and neighboring context;
length differences fail too. Independent adapters must supply equivalent
identities deliberately, never discard mismatch data to force agreement.

- `ordered` compares epoch, kind, source/master, logical address and data.
  Interrupt-acknowledge addresses are ignored; their data still matters.
- `mapped` additionally compares resolved memory space and offset, rejecting
  memory events without mapping information.
- `timed` additionally compares clocks and requires matching nonempty clock/
  stepping contracts. Imported untimed HDL/native text cannot claim timed parity.

Replaying one core twice proves determinism, not independent correctness. The
Juku HDL adapter in `8080-cosim` also feeds independently produced C/Verilog
captures to this comparator. That remains functional event-order comparison.
No independent Robotron emulator/HDL differential or physical timing comparison
is claimed by these tests.

## Acceptance and next targets

`make test` covers existing core/peripheral tests plus both scenario profiles,
reset/instance isolation, snapshots retaining live observers, budget precision,
read-only probes, malformed requests, incomplete traces and deliberate comparison
mismatches. `make test-runtime-sanitize` checks the shared C boundary with ASan
and UBSan. Native CI runs these on Linux and macOS; existing WASM tests guard
browser API, replay-related behavior and same-build snapshots.

A plain 1715 must be a separate profile with its actual firmware regions, memory
map, devices and qualified I/O. Do not alias it to `robotron1715m`. Add its session
adapter, declare supported observations, then run the same contracts and its own
machine-specific ROM/peripheral fixtures. VJUGA retains its existing runtime but
is not yet advertised as a scenario profile because it lacks the same trace
coverage. Serial endpoint unification, advanced fault descriptions, independent
Robotron differential tests and portable cross-build save states remain separate
work. The repository name need not change to establish these boundaries.
