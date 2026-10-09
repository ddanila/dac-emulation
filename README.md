# DAC Emulation

Portable emulation cores for [Danila’s Archive of Computing](https://github.com/ddanila/dac).

The goal is to run the same machine implementation in native verification tools and in browser museum exhibits. The first extracted core is the Juku E5104 from [8080-cosim](https://github.com/ddanila/8080-cosim). VJUGA and Robotron 1715M are planned consumers of a shared Z80 CPU dependency, with separate machine implementations.

## Status

Juku now builds as an instance-based C library and a native compatibility runner. Shared tracing and callback-backed media are implemented. Original consumers still use `8080-cosim`; switching them is a separate migration step. There is no browser bundle or portable Z80 machine core yet.

```sh
make -j4
make test
```

`make test` is the fast intermediate check: no Verilog, firmware downloads, PTYs, or full-system boot. Extended comparisons are explicitly opt-in. See [extraction and validation](docs/juku-extraction.md) for results and outstanding upstream failures.

## Layout

| Path | Responsibility |
| --- | --- |
| `common/trace/` | Shared trace events and diagnostic output interfaces |
| `common/media/` | Disk-image storage and sector metadata, independent of controllers |
| `machines/juku/` | Juku machine core and machine-specific devices |
| `machines/vjuga/` | Existing HDL reference and future portable Z80 machine |
| `machines/robotron1715m/` | Future Robotron 1715M machine core and machine-specific devices |
| `third_party/cpu/` | Pinned CPU dependencies with their original notices |
| `runners/native/` | Native CLI, files, terminal transport, and host pacing |
| `runners/browser/` | WebAssembly integration, browser input, scheduling, and output |
| `tests/differential/` | Comparisons with independent implementations |
| `tests/integration/` | Complete boot and interaction scenarios |

## Repository boundaries

- **dac:** museum UI, exhibits, 3D interactions, and asset references.
- **dac-emulation:** portable cores, shared utilities, runners, and behavioral tests.
- **8080-cosim:** Juku hardware reconstruction, HDL, physical evidence, and co-simulation harnesses. It will eventually pin the extracted core here.
- **juku-common:** shared guest software that runs on Juku, including assembly diagnostics, console, and boot/transport routines.
- **cpmish / cpm-plus-juku:** their operating-system implementations and integration tests.

See the [architecture and interface proposal](docs/architecture.md) and [migration sequence](docs/migration.md). The architecture distinguishes implemented foundations from the proposed museum interface.

## License

Original project code and documentation are licensed under the [MIT License](LICENSE).

Imported dependencies and adapted code retain their original licenses and notices. Do not relabel third-party code as MIT. Firmware, disk images, and other historical media are separate from the emulator code; none are included here.
