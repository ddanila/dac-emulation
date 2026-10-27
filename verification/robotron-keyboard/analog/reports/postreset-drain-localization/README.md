# Drain refinement localization

The existing event and peak extractors processed the complete coarse, fine and finest drain captures. Extraction verified the complete decompressed logs and waveforms against their capture receipts. Retained excerpts reproduce all ten failing-node maxima on absolute time. Replay of both retained assessments passes.

All three logs contain the same 633-port sequence. Coarse/fine changes 326 event timing records (25 actual, 326 target, 222 base); fine/finest changes 316 (19 actual, 316 target, 205 base). Times are retained as logged strings.

At the eight failing data-line peaks, the nearby bus-low base-time offsets have the same sign and approximately the same magnitude as the interpolated 1.4/2.5/3.5-V crossing offsets: about 0.88–0.99 ps. For example, fine/finest D3 has a 0.987557-ps base offset and a 0.987092-ps 2.5-V crossing offset. This supports investigating bridge delivery timing. It does not establish causality: the audit omits output values and input-threshold history. The WR peak window contains no crossings at these thresholds.

The unchanged full-window non-growth gate remains failed. No time alignment, tolerance change, new capture or convergence waiver was applied. Excerpt replay does not independently repeat the full-waveform search or prove unsampled behavior.

Replay from the repository root:

```sh
python3 verification/robotron-keyboard/analog/postreset_tick_events.py --check verification/robotron-keyboard/analog/reports/postreset-drain-localization/events
python3 verification/robotron-keyboard/analog/postreset_tick_peaks.py --check verification/robotron-keyboard/analog/reports/postreset-drain-localization/peaks
```
