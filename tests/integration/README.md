# Integration tests

`make test` runs fast C checks for independent machine instances, bounded execution, ROM loading, tracing, media bounds/write policy, and memory-backed FDC attachment. No HDL or external images are required.

Optional inherited native regressions use the pinned source checkout:

```sh
python3 tests/integration/upstream_checks.py ../8080-cosim
```

These include CPU conformance, disk/FDC, PIT, checkpoints, pacing, and ROMBIOS disk/console fixtures. `--serial` enables PTY tests; `--hdl` enables slower Verilog comparisons. Neither is an intermediate default. Known inherited failures are recorded in [validation](../../docs/juku-extraction.md).

Robotron peripheral checks run as part of `make test` without historical media.
For create/read/copy/reboot/delete and native/WASM disk parity, use the optional
`--file-operations` flag on `robotron_boot.py` / `wasm_parity.mjs` with a raw disk
decoded from the original TeleDisk image. See the
[Robotron media instructions](../../machines/robotron1715m/README.md).

## Custom 1715W ROM peer

`make build/robotron-rom-monitor` builds an offline process peer for Ravi's W1
ROM qualification. Invoke it with a 2048-byte ROM, a 256-byte CAS PROM and an
optional `no-ram,no-display` mode. It executes the actual Z80 instructions with
the modeled CTC/SIO and an independent 9600 8N1 serial peer; no guest-PC traps
or host execution shortcuts are used.

Each stdin command produces one stdout line of received hexadecimal bytes:
`T hex` sends bytes, `S ticks` advances time, `F physical mask value` injects a
read fault (hex arguments), `A mask` aliases CPU address bits, `U 1/0` stalls or
releases TX, `P format` changes peer framing, `V path` writes a PPM display,
`D` reports access counters to stderr, and `Q` exits. Startup also emits one
line. Main-RAM accesses in `no-ram` mode make the process fail. Display writes
are discarded in `no-display` mode.

Ravi's `tools/qualify_robotron1715w.py` pins this emulator and drives firmware
fault/recovery tests. This fixture does not qualify physical clock routing,
DRAM retention, specimen PROM contents, or recovery from an arbitrary CPU hang.

`Z` resets CPU/devices while retaining RAM and ROM/PROM, then runs startup.
It is a controlled reset injection, not a power-cycle or analog reset model.

The W2 fixture allows two million startup ticks for the ROM CRC sweep. `F`
accepts an optional decimal read count; omitting it keeps a permanent fault.
`first_tx_display_writes` records how many display writes preceded the first
serial byte, allowing independent validation of serial-first startup.
