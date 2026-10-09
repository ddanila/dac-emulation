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
