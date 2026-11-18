# Phase A evidence and method status

The two original .11/.21 PDFs were freshly downloaded into ignored `build/`
storage on 2026-11-18. Their byte counts and SHA-256 digests match
[`sources.json`](sources.json): `older.pdf` is 769,720 bytes with digest
`3c435063815af483a0fa98823a8a95a4178359e64f759344ee03cc0300e292dd`,
and `older-operation.pdf` is 1,146,242 bytes with digest
`7506b2fcf81bcc31ba3f6d27832b5295324bdd6cd91c459f3e7adb3701a67f21`.
The source scans remain outside version control.

## Reference register

[`service-observations.json`](reference/k7222-11/service-observations.json)
now distinguishes printed amplitude guidelines from inferred timing and absent
numeric information. Manual PDF page 21 has **test point 16**, which the former
register omitted: X13:4, 8–25 V peak to peak. Pages 20–21 show the 17 waveform
shapes and identify their test nodes. The 0 V baselines in some drawings do not
specify mean DC voltage. Only point 5 prints a 0.5 ms pulse width; other pulse
widths remain null. The page 20 note calls the voltage values *Richtwerte*
measured with a service oscilloscope EO2.

Operating-manual PDF page 5 prints the 1/2 kByte horizontal retrace times
(17.2/16.0 µs), vertical retrace times (2.08/1.5 ms) and picture size
(210 ± 20 by 145 ± 15 mm). Page 6 gives a qualitative focus criterion under
20 µA unblanked beam, 40 cm viewing distance and 500 lx ambient light; it does
not give a spot diameter. Pages 30–32 give the adjustment sequence, including
5 V, synchronization, T1, R24, beam current and iterative geometry trims. The
register preserves these targets and steps with page addresses.

Every printed point has a proposed named circuit node. The mapping comes from
the .11/.21 schematic pages 3–4 and 9–10 plus the current KiCad transcription;
the A1 human connectivity review is still needed before treating a mapping as
historically confirmed. `service_score.py` reads a stage `samples.txt`, CSV or
connected `trace.raw` and measures available points. A missing required probe
fails the requested point set. It reports approximate amplitude, inferred
period, numeric pulse width where printed, measured DC and a polarity hint;
drawn waveform shape still requires visual review. The scorer never fits model
parameters.

Stage runs on the vertical and horizontal profiles now write `service-score.json`
automatically. For an archived connected trace or a specific Phase B stage:

```sh
python3.14 verification/robotron-monitor/service_score.py \
  build/monitor/example/trace.raw --start 0.0585 --end 0.078 \
  --require 14,15,17 --output build/monitor/example/service-score.json
python3.14 verification/robotron-monitor/service_score.py \
  build/monitor/vertical-bench/samples.txt --require 1-8 \
  --output build/monitor/vertical-bench/service-score.json
```

`calibration_contract.py` freezes only points 14, 15 and 17, the documented
11–12 kV target, retrace and picture size. It checks bounded T3, yoke, L4 and
tank assumptions and records every manual trim setting. The proposed settings
must come from a labelled synthetic grid, with no rendered image used for
selection; all other service points remain held out. No valid calibration
freeze exists yet, because the horizontal output has not passed those targets.
The connected-run path accepts a verified `--calibration-freeze` record and
archives its hash; without one it can continue electrical screening but stops
before rendering a native image.

`phase_a_gates.py` implements the ordered G1–G8 frame gate policy and fails
closed on absent evidence. Its G1/G1b input can come from the connected
`native_sync_lock` report, which now counts extra flybacks and adjacent-line
jitter. Its G2 input can come from the existing three-field settling report.
The gate report checks that the service score belongs to the final electrical
trace and that readability uses the selected native capture. G3/G4 also require
an identified reviewer to check each drawn waveform shape and the manual's
operating conditions; numeric agreement alone cannot pass them. These gates do
not imply that Phase B measurements already pass.

The older connected-run electrical/optical checks now stop at `screen-passed`.
They cannot publish `accepted-experiment` or an accepted warmed frame on their
own; `phase_a_gates.py` is the documented-reference acceptance decision. This
prevents a lower-tier diagnostic image from bypassing G1–G8.

## B31G22 search

Searches on 2026-11-18 for `B31G22`, `B 31 G 22`, datasheet, heater and cutoff
voltage found no primary B31G22 data sheet. The [RFT tube archive](https://frank.pocnet.net/other/RFT/RFT_Spezialroehren_1961.pdf)
and [Toshiba CRT catalog](https://frank.pocnet.net/other/Toshiba/Toshiba_CathodeRayTubes%281974%29.pdf)
cover other tubes, so their heater, deflection and cutoff numbers are not
transferred to B31G22. The .11/.21 assembly drawing names B31G22; the manual
itself supplies the focus criterion above. Tube parameters remain assumed.

## Native test content

The [later S550/TOS/M capture](examples/phase-a-native-full-text/README.md)
has a full text screen, with active VIDEO on 154 scan lines. Its immutable
capture, input hashes and logical preview are archived there. Grid and
cross-hatch sources remain explicitly synthetic for calibration and electrical
gates. The logical preview is a scoring reference only; it does not drive the
CRT renderer.

## Open Phase A work

The multi-pass BOM and manual OCR, per-entry inventory reconciliation and human
schematic review are in progress. The gate contract exists, but the stage and
full-frame evidence producers for geometry, refinement and readability belong
to Phase B. This document does not assert Phase A completion or a qualified frame.

`inventory_audit.py` prepares a 260-entry review report from the independent
parts-list CSV passes. It checks grouped reference quantities, records the
reading from each pass and distinguishes exact machine agreement from source
review. It does not declare a part confirmed merely because three OCR passes
agree: the printed value must also be compared with the inventory. For example:

```sh
python3.14 verification/robotron-monitor/inventory_audit.py \
  --ocr-root build/monitor/phase-a/ocr-workflow/outputs/k7222-list \
  --output build/monitor/phase-a/inventory-audit.json
```

After the third full-page vision pass available on 2026-11-18, 227 entries had
three agreeing readings per applicable table cell and matched the inventory's
value or type; 26 parts-list entries still needed more source
evidence or review, and seven schematic-only entries needed schematic review.
These counts are interim and will change as the crop passes finish.

The first direct source correction is V14 on board 012-6921: the printed
page-8 type is `1 YL1/2`, correcting the inventory's earlier `1YL/2` spelling.
The page-12 C26 label `EDVU-N470-220/10-63` has also been checked against its
source image; `N470` is part of the printed type code, so the 220 pF inventory
value is not treated as an OCR disagreement.

The audit found a material board-value error on page 14: R30 on 012-6931 is
100 Ω, not the inventory's 10 Ω. The inventory and KiCad converter part R819
now use 100 Ω. The old `converter-step-audit-decks` are archived experiments
with 10 Ω, not current reference-model results; they require a new converter
run before their numerical behavior is reused. Page-12 L4/L5/L6 remain in the
source-review queue because the scanned microhenry glyph is consistently read
as `M` by OCR; machine agreement does not settle the unit.
The C30 stock-number cell on page 6 is genuinely blank and is counted as a
three-pass blank-cell agreement. The malformed R26 stock number on page 14 is
kept in source review despite three matching OCR strings.
