# Native full-text source for the planned frame

The archived `capture.json.gz` is a logical VIDEO/BSYN/INTENS capture from the
native Robotron 1715M core with S550, CAS and TOS/M 1.0 media. After
150,000,000 CPU ticks, the TOS/M FKEY configuration screen occupies 154 of 312
scan lines, from line 26 through 299. Two adjacent selected fields are
byte-identical. The [logical preview](logical-reference.png) shows substantially
more screen content than the earlier two-line loader banner. It is a reference
for later image scoring, not CRT render input or an accepted monitor frame.

The original ROM and disk files are not included. Their SHA-256 identities,
the executable identity, selected-field identity and output hashes are in
[`manifest.json`](manifest.json). Reproduce the capture with locally held media:

```sh
make build/robotron-monitor-capture
python3 verification/robotron-monitor/capture.py \
  --rom ../dac/public/media/robotron/s550.bin \
  --prom ../dac/public/media/robotron/cas.bin \
  --disk ../dac/public/media/robotron/tosm10.img \
  --boot-ticks 150000000 --dot-ticks 13824000 \
  --output build/monitor/phase-a/native-full-text.json
```

Use `gzip -dc capture.json.gz > build/monitor/phase-a/native-full-text.json` to
feed the archived capture to `full_path.py`. The source is labelled native
firmware timing. Synthetic grid and cross-hatch captures remain calibration
fixtures and must retain their synthetic labels.
