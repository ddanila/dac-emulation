# Robotron loader: current optical render

![CRT render](frame.png)

A fresh 960×720 render made on 2026-11-19 with the current compiled beam
trajectory and periodic phosphor renderer. Input is the saved final electrical
field of the [geometry-connected diagnostic](../geometry-connected-diagnostic/README.md),
containing native S550 loader text. This reuses that historical electrical
experiment; it does not rerun the latest circuit transcription. No display gain,
cropping, registration or image-based geometry fitting was applied.

The faint, distorted picture remains an experimental diagnostic. The electrical
trace is not settled; preceding identical fields are assumed for phosphor
initialization. It is not a qualified K7222 monitor simulation.

Reproduce from the retained local trace:

```sh
python3 verification/robotron-monitor/periodic_frame.py \
  --trace build/monitor/geometry-connected-audit/chord-full/input.csv \
  --output build/monitor/user-render-20261119 \
  --assume-periodic --width 960 --height 720 \
  --field-parameters verification/robotron-monitor/examples/geometry-connected-diagnostic/field-parameters.json
```

Use a new output directory when repeating the command. The linked original
diagnostic documents how to regenerate its electrical trace. `frame.json`
records input/model hashes, output hashes, numerical settings and the energy
ledger. The complete optical archive, including `input.csv`, linear `frame.f32`,
model snapshots and `periodic-state.json`, remains in the ignored local output
directory above. This compact repository example contains only the PNG and
report, so it is not a standalone optical cache.
