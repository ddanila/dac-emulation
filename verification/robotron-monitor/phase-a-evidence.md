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

The first operating-manual vision pass exposed a TP17 transcription error:
page 21 shows **80 Vpp** at V14's cathode, not the earlier register's 90 Vpp.
Direct inspection of the page image, an independent classic OCR crop and the
second and third vision passes all read 80 Vpp; the first vision pass read
60 Vpp. The second pass read point 13 as 5.4 Vpp, but the source crop, first
and third vision passes and classic OCR read 6.4 Vpp, matching the register.
The third pass omits most numeric amplitudes on page 20, illustrating why a
text-only pass is insufficient for waveform figures. Further passes remain
in progress. Page 20 also has a handwritten `9a` waveform below the
printed 1–8 set,
annotated 22 and 10 Vpp at V22's collector. The register preserves it as an
auxiliary observation. Its converter node is excluded from Phase B's ideal-rail
stages, so it is not silently treated as one of the numbered 1–17 score points.
The point-8 figure additionally labels R48/V20 and approximately 10 Vpp below
zero; its relationship to X2:3 is left for schematic review.
The point-7 figure marks a 1 ms rise interval; it is retained as a rise-time
annotation rather than misclassified as pulse width.
The fourth text pass reads point 13 as 6.4 Vpp but moves decimal points on
page 21: it reports 7.0, 4.5 and 8.0 Vpp for points 14, 15 and 17 where the
source image prints 70, 45 and 80 Vpp. It also collapses point 16's 8–25 Vpp
range into 8.25 Vpp, misreads point 5's 19 ms period as 15 ms, and reads the
handwritten auxiliary 22 Vpp as 2.2 Vpp. Direct image review retains the
source values; these OCR disagreements are not averaged into new targets.
The same pass invents a beam-current procedure on page 30 involving 7.5–7.9
J/kg and a 2.4 V 1 kByte T1 setting. Neither appears on the source page: it
prints the 0.1 mV and 3.6 mV meter sequence and a 2.2 ± 0.2 V 1 kByte T1
setting. The fabricated text is not used to revise the register or settle a
source-review mark; the raw OCR output remains available for audit.
On page 32 the pass also reads both vertical-linearity controls as R59;
the source image and the other text passes distinguish R60 and R59. This
remains a source conflict about their screen regions, not about their labels.

The first text pass of manual pages 17 and 30–32 added two setup constraints
that the earlier register missed: page 17 prints a horizontal-generator control
range of 14.338–16.338 kHz, and page 30 limits the just-visible raster meter
rise to 0.1 mV above darkness before the 3.6 mV maximum-beam setting. The
register now records both and the full meter sequence. Page 15's explanation
swaps the upper/lower roles of R59 and R60 relative to page 32's adjustment
instructions and carries a handwritten correction mark. That conflict is
explicitly left for schematic and control review. The printed upper frequency
bound is about 2.1% above 16 kHz, narrower than Phase B's proposed +3% margin;
the B2 criterion needs reconciliation with the source, not an invented pass.
The third manual text pass confirms the 14.338–16.338 kHz range and page 32's
R60/R59 adjustment labels; it also confirms the page 30 meter sequence and
page 31's separate R4 and R5 geometry controls.
Page 10 also states approximate cathode levels of 35 V for VID=0 (dark) and
15 V for VID=1 (normally bright), with INTENS able to lower the bright level.
These are operating levels in the text, not DC means supplied for the 17
waveform figures; the register keeps that distinction.
Page 32 prints two 2 kByte vertical grid-spacing ranges, 25–30 mm and
28–33.5 mm, without labelling them as upper or lower screen positions. The
register preserves their printed order and leaves that spatial mapping open.

Stage runs on the vertical and horizontal profiles write `service-score.json`
automatically. Every completed connected candidate now writes the same score
for its final simulated field; the coupled and refinement/initialisation
validation traces do so as well. Each connected-run report links to its trial's
score and records the 17 point statuses. A missing probe stays `missing-probe`,
so this output is a stage diagnostic, not an automatic acceptance. For an
archived connected trace or a specific Phase B stage:

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
must name an actual hash-matched synthetic grid or crosshatch capture. The
freeze checks its repeated complete fields, full-screen VIDEO coverage and
16 kHz/19.5 ms S550 timing before recording the pattern identity. No rendered
image may select settings; all other service points remain held out. No valid
calibration freeze exists yet, because the horizontal output has not passed
those targets.
The connected-run path accepts a verified `--calibration-freeze` record and
archives its hash. Before a frozen run starts solving, it checks that the
selected T3 candidate, magnetic-parameter file, yoke profile, L4 coupling and
horizontal tank value match the frozen assumptions. With `candidate=auto`, the
frozen candidate is selected. Without a freeze it can continue electrical
screening but stops before rendering a native image. Manual trim settings are
recorded in the freeze; their physical-to-model application still needs the
synthetic-grid calibration run.
The freeze requires records for the full manual setup sequence: 5 V R9,
vertical sync R22, T1, horizontal hold R24, dark-raster R28, maximum-beam R4
on 012-6921, horizontal linearity L3, width R5, horizontal centring R4 on
012-6931, height R35, linearity R59/R60, vertical shift R58, and the focus,
brightness and contrast controls. The two R4 keys identify their boards.
The linearity keys identify R59 and R60 by part number without assigning upper
or lower screen regions: manual pages 15 and 32 disagree about those roles.
The conflict must be resolved before model application is claimed.

A fresh `steady_supply.assemble()` export shows neither 012-6931:R4 nor
012-6931:R5 in the connected assembly; the latter is currently confined to
the converter sheet, which this path excludes. Both appear in the inventory
and manual geometry procedure. Their connections and control effects need
schematic review before a B6 trim setting can be claimed as applied to the
simulated monitor. The other trim settings are recorded, but a future grid
calibration must verify their actual physical-to-model application.

`phase_a_gates.py` implements the ordered G1–G8 frame gate policy and fails
closed on absent evidence. Its G1/G1b input can come from the connected
`native_sync_lock` report, which now counts extra flybacks and adjacent-line
jitter. Its G2 input can come from the existing three-field settling report.
The gate report checks that the service score belongs to the final electrical
trace, uses the current service register, contains each of the 17 points once,
and that readability uses the selected native capture. The gate command
recomputes the saved score from the electrical trace before evaluating it.
G3 now requires measured high voltage and retrace time tied to that electrical
trace, plus picture dimensions from the frozen synthetic-grid capture. Frozen
target values alone cannot pass G3. Those measured evidence fields still need
Phase B producers; the contract does not turn absent measurements into a pass.
G3/G4 also require
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
cross-hatch sources are generated by `robotron-signal-pattern grid` and
`robotron-signal-pattern crosshatch` using the same 16 kHz, 19.5 ms connector
timing as the native S550 mode. Both remain explicitly synthetic for
calibration and electrical gates. The logical preview is a scoring reference
only; it does not drive the CRT renderer.
Four-field fixtures were generated under `build/monitor/phase-a/patterns/`:
the grid has 22,089 output events (SHA-256
`9b1dd5fae555028824f1ea89ea9c08eb64342a3c107da99ffab9cffbbc969598`)
and the cross-hatch 38,345 (SHA-256
`3f88051b8894d8d9858ec2ea3c8f7f7c4f061dffc1abb2f306def0181cf712a0`).

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

`phase_a_review.py` turns the remaining entries into a blank human-review
template and evaluates the A1 source gate against fresh OCR and the current
inventory. The template is created once and cannot overwrite existing marks:

```sh
python3.14 verification/robotron-monitor/phase_a_review.py \
  --ocr-root build/monitor/phase-a/ocr-workflow/outputs/k7222-list \
  --source-pdf build/monitor/phase-a/sources/older.pdf \
  --template build/monitor/phase-a/source-review-template.json
python3.14 verification/robotron-monitor/phase_a_review.py \
  --ocr-root build/monitor/phase-a/ocr-workflow/outputs/k7222-list \
  --source-pdf build/monitor/phase-a/sources/older.pdf \
  --marks build/monitor/phase-a/source-review-template.json \
  --output build/monitor/phase-a/source-review-gate.json
```

Each blank part mark includes the current inventory value and independent OCR
readings as review context. Each human mark needs a source reading, disposition,
reason, reviewer and date.
An `unresolved` mark is valid only after the inventory entry itself is marked
unresolved. Schematic marks cover pages 3–4, 9–10, 16 and 18 and must record
KiCad connectivity, diode direction and winding polarity review. Marks bind to
the inventory entry, source PDF and current KiCad tree hashes; edits invalidate
stale marks. The blank template currently fails the gate with 33 open parts and
six open schematic pages, as intended. No human marks have been entered.

After the third full-page vision pass and both crop passes on 2026-11-18, 227
entries had three agreeing readings per applicable table cell and matched the
inventory's value or type. The other 33 remain open: page 6 C11/C18, page 8
T1, page 12 L4/L5/L6, page 14 R26, 19 grouped device/fuse entries on page 15,
and seven entries found only on schematics. The local
`build/monitor/phase-a/inventory-audit.json` names every open entry and its
individual OCR readings; the completed parts-list crop passes are included in
`build/monitor/phase-a/ocr-workflow/review.zip`. These are review aids, not
human review marks. The manual text passes and high-zoom schematic vision scan
are still pending.
On page 15, the source spans the 1 AE 15 diode designator list over four lines
and leaves its quantity cell blank; the vision passes split and reassign parts
of that group differently. They also disagree around V3/V15 and the following
transistor rows. Those entries need direct source inspection rather than a
parser rule that would convert an OCR grouping guess into agreement.

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
