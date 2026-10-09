# DAC Emulation

Portable emulation cores for [Danila’s Archive of Computing](https://github.com/ddanila/dac).

The goal is to run the same machine implementation in native verification tools and in browser museum exhibits. The first planned cores are the Juku E5104, extracted from [8080-cosim](https://github.com/ddanila/8080-cosim), and the Robotron 1715M.

## Status

Repository scaffold only. No machine core, native executable, browser bundle, or build system has been implemented yet. Juku remains maintained in `8080-cosim` until its extraction passes the existing regressions.

## Layout

| Path | Responsibility |
| --- | --- |
| `common/trace/` | Shared trace events and diagnostic output interfaces |
| `common/media/` | Disk-image storage and sector metadata, independent of controllers |
| `machines/juku/` | Future Juku machine core and machine-specific devices |
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

See the [architecture and interface proposal](docs/architecture.md) and [migration sequence](docs/migration.md). These describe intended behavior, not implemented capabilities.

## License

Original project code and documentation are licensed under the [MIT License](LICENSE).

Imported dependencies and adapted code retain their original licenses and notices. Do not relabel third-party code as MIT. Firmware, disk images, and other historical media are separate from the emulator code; none are included in this scaffold.
