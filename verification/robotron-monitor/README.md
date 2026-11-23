# Robotron monitor circuit lab

A component-level circuit model of the Robotron K7222.11/.21 monitor, with a
beam and phosphor renderer. The aim is one frame of a native Robotron 1715
screen, solved by the circuit in a sustained warm state.

**Status: experimental. No qualified frame exists yet.** The method, the next
steps and the current state are in [PLAN.md](PLAN.md). Every result keeps
`full_monitor_qualified=false` and `specimen_validated=false`: the model is
built from documents only and is not a measurement of any physical monitor.

## Documents

| File | Content |
|---|---|
| [PLAN.md](PLAN.md) | Method, gates, steps and status |
| [reference-evidence.md](reference-evidence.md) | Source scans, page locations, revision boundaries |
| [single-frame-acceptance.md](single-frame-acceptance.md) | Charge, energy and lock accounting in the frame runner |
| [YOKE-GEOMETRY.md](YOKE-GEOMETRY.md) | The geometry-derived reduced yoke model |
| [devices/README.md](devices/README.md) | TDA1060 and P09A equivalent models |
| [reference/1715w/README.md](reference/1715w/README.md) | Computer-side video output and cable |
| `sources.json` | Source documents with SHA-256 identities. The PDFs are not redistributed; they are expected under `build/monitor/phase-a/sources/` |

## Layout

| Path | Content |
|---|---|
| `circuits/` | KiCad sheets and SPICE model cards, one sheet per stage |
| `profiles/` | Stage bench definitions: sheet, models, probes, parameter ranges |
| `devices/` | Device subcircuits and their bounds |
| `reference/k7222-11/` | Inventory, device and class-typical registers, service test points, design point, and every saved report |
| `examples/` | Archived runs with their decks, hashes and images |
| `tests/` | Tool tests and report-reproduction checks |

The circuit is read from KiCad on every run. `SourceId` keeps each part's
original board and designator. The reference boards are 012-6921
(horizontal/video), 012-6931 (vertical/power) and 012-6891 (neck); the tube
and yoke are B31G22 and AE9VT.

## Requirements

Python 3.10+, ngspice (tested with 45.2; the pinned runtime is ngspice 47) and
KiCad CLI (tested with 10.0.6). No Python dependencies.

```sh
make test-monitor
```

The tests need the pinned runtime (`MONITOR_RUNTIME`) and the source PDFs
under `build/`. Build the runtime from the ngspice 47 source archive:

```sh
python3 verification/robotron-monitor/monitor_runtime.py \
  --archive /tmp/ngspice-47.tar.gz --output build/monitor/runtime-new --jobs 4
```

## Main workflow

Capture native firmware output, or generate a synthetic pattern with the same
16 kHz / 19.5 ms timing:

```sh
make build/robotron-monitor-capture build/robotron-signal-pattern
python3 verification/robotron-monitor/capture.py --rom ROM2048 --prom CAS256 \
  --disk DISK --output capture.json
build/robotron-signal-pattern grid --fields 4 --line-characters 108 > grid.json
```

Captures hold `[tick, VIDEO, BSYN, INTENS]` edges on a 179.712 MHz integer
timebase, not pixels. Patterns are labelled `synthetic-test-pattern` and are
never accepted as a firmware frame.

Run one stage bench:

```sh
python3 verification/robotron-monitor/reference.py \
  --profile verification/robotron-monitor/profiles/k7222-11-vertical-output.json \
  --runtime build/monitor/runtime-new --output build/monitor/vertical-output \
  --stop .16 --step .00001
```

Run the connected monitor on ideal rails:

```sh
python3 verification/robotron-monitor/full_path.py \
  --mode steady-supply-frame --runtime build/monitor/runtime-new \
  --capture capture.json --candidate auto --output build/monitor/steady-screen
```

It exits 2 with a report while any gate fails. Output directories are never
overwritten, and a failed run publishes no image or replay.

Score a run against the manual's test points, and evaluate the gates:

| Tool | Purpose |
|---|---|
| `service_score.py` | Measures the 17 service test points in a stage `samples.txt` or a connected `trace.raw` |
| `calibration_contract.py` | Freezes the calibration set, separately from the held-out points |
| `phase_a_gates.py` | Evaluates the blocking frame gates G1–G8 |
| `sync_lock.py`, `lock_scan.py` | Horizontal lock check and bounded R24 trim search |
| `scan_diagnostics.py` | Raster extent and timing of a solved field |

Render a solved electrical trace:

```sh
python3 verification/robotron-monitor/steady_trace.py --raw trace.raw \
  --start .0585 --end .078 --output field.csv
python3 verification/robotron-monitor/periodic_frame.py \
  --trace field.csv --output build/monitor/optical
```

`beam_render.py` and `stream_render.py` render longer traces. Their input
columns are `time,anode_v,grid2_v,focus_v,cathode_v,horizontal_a,vertical_a,beam_a`.
There are no framebuffer pixels or prescribed beam coordinates in this path.
`image_acceptance.py` compares a render with a refined one in linear
irradiance, with a 2% limit and no registration or exposure fitting.

## Other benches

| Tool | Purpose |
|---|---|
| `lab.py` | The 30-component driven flyback fixture. It is a pipeline test, not the K7222 circuit |
| `signal_path.py`, `verify_signal_path.py`, `export_signal_path.py` | Computer output, cable and monitor input, with numerical refinement |
| `lifecycle.py` | Neck board with heater and emission from cold to 300 s |
| `atlas.py` | Fault atlas development package. Not release-eligible until the whole monitor is connected |
| `horizontal_isolation.py`, `loop_response.py` | Horizontal oscillator tuning and loop response on an isolated bench |
| `transformer_candidates.py`, `magnetics.py` | T3 winding candidates and the shared-core transformer model |
| `solver_profile.py` | Accepted-step density and step audits of a solver run |

The switching converter bench (`profiles/k7222-11-converter.json`) covers
early startup only and is outside the frame path.

## Replay files

`.mcrt` files carry recordings for the museum's `monitor.html` viewer. All
versions share one framing: a magic line, a little-endian uint32 JSON header
length, UTF-8 metadata, then binary chunks with offset, length and SHA-256.

| Magic | Written by | Content |
|---|---|---|
| `DACCRT1` | `lab.py` | Fixture: 160×112 phosphor frames and one float64 trace (time, collector V, anode V, focus V, horizontal A, vertical A, cathode V, beam A, x m, y m, spot sigma m, landing-valid) |
| `DACCRT2` | `reference.py` | Stage traces with named fields, units and source identifiers. No phosphor frames |
| `DACCRT3` | `beam_render.py`, `stream_render.py` | Optical bench: frames of 8–2048 pixels per side, named traces, sparse ray paths, at most 120 frames |

Viewer limits: 64 MiB per file, 1 MiB metadata, 250,001 trace rows. Hashes
detect corruption, not authenticity. The parser rejects overlap, truncation,
non-finite samples and unsupported versions.
