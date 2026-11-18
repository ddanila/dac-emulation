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
text-only pass is insufficient for waveform figures. All five manual vision
passes are now complete. Page 20 also has a handwritten `9a` waveform below the
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
The fifth, high-resolution pass reads points 13–17 as 6.4, 70, 45, 8–25 and
80 Vpp, and point 5's period as 19 ms, confirming the source-based register.
It omits the point-7 1 ms rise annotation and shifts the second 2 kByte
grid-spacing range into the 1 kByte column on page 32. The original page image
and the other passes support the register's printed-order 2 kByte ranges.

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
The same page gives the converter's free-running frequency as approximately
20–25 kHz, dependent on C9/R15, and says it is forced by SYNC through V2 pin 9.
The register stores that as a converter condition, distinct from the native
S550 line frequency and from a measured converter result.
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
calibration freeze exists yet: the connected output has not passed those
targets, and three manual controls lack model bindings.
The connected-run path now accepts a labelled synthetic grid or crosshatch
without a freeze. A synchronized, settled synthetic run may proceed through
electrical and optical screening while remaining a calibration diagnostic;
native rendering still requires the freeze. A calibration score may be frozen
only from that run's final complete field in `trace.raw`: the archived deck,
metadata and successful solver receipt must agree with one another, with the
exact hashed synthetic capture, and with the proposed T3, magnetic, yoke, L4
and tank assumptions. A hand-written CSV cannot establish a
calibration freeze. This is a provenance gate, not evidence that the connected
monitor currently meets the calibration targets.
The freeze now integrates `v(eht)` over that final complete field and stores
the measured mean alongside the trace identity. It requires 11–12 kV and
rejects a proposed EHT value more than 1% away from the measured mean. It also
averages horizontal yoke current by line phase across the final field. The
shorter monotone excursion between its extrema measures electrical retrace;
flat, sinusoidal or strongly nonmonotone waveforms cannot establish it. The
freeze requires 12.8–19.2 µs and agreement with the proposed value within
5% or 1 µs, whichever is larger. This is a current-based electrical measure,
not an optical trace of beam position. `grid_geometry.py` now interpolates the
connected final-field electrode voltages and both yoke currents at the grid's
printed VIDEO marker times, then traces central rays through the bound yoke
field model. It measures the outer stripe width, top-to-bottom grid height,
and spacing error on both axes. A border ray that misses the screen fails the
measurement. The freeze requires width and height to meet Phase A's ±20%
calibration band around the manual nominals and to agree with the proposed
numbers within 5% or 5 mm. This is a
grid trajectory measurement, not a claim that a rendered image, spot size or
focus criterion has passed. The geometry producer now also requires modeled
post-grid beam launch above 0.01 µA for at least 0.5% of the final field, with
a peak above 0.05 µA and launch at at least 10% of grid marker centers; a dark
grid cannot establish picture size. These are
engineering visibility witnesses, not manual beam-current calibration or
proof that every grid stroke is illuminated. G5 still applies its tighter 90–105% and ≤10%
geometry limits after the full grid stage.
The connected-run path accepts a verified `--calibration-freeze` record and
archives its hash. Before a frozen run starts solving, it checks that the
selected T3 candidate, magnetic-parameter file, yoke profile, L4 coupling and
horizontal tank value match the frozen assumptions. With `candidate=auto`, the
frozen candidate is selected. Without a freeze it can continue electrical
screening but stops before rendering a native image. The freeze now checks
thirteen trim settings mapped by the current KiCad transcription against both
the trial's parameter record and the deck's actual `.param` declarations. The
native run must keep those settings. It rejects settings outside model bounds.
This checks that a setting reached the circuit; it does not establish that the
manual's 5 V, beam-current, focus or geometry adjustment criteria were met.
The trim audit found a sharper gap in the current ideal-rail assembly:
012-6921:R4 has a parameterized `contrast_trim` branch, and the horizontal
hold, vertical sync, height, linearity, shift, brightness and focus controls
have model parameters. But 012-6931:R4 (horizontal centring) and R5 (picture
width) are absent from the assembled sheets; R5 lives in the excluded
converter path. Recording their nominal settings cannot apply the manual's
step 8. The separate brightness control is likewise not bound to a model
parameter; R28 is the dark-raster preset and is not a substitute. The freeze
now refuses these three unbound controls rather than recording their proposed
settings as applied. The vertical linearity profile also labels R59 lower and R60 upper,
while manual page 32 says R60 lower and R59 upper. The schematic/source review
must resolve that reversal before binding either setting to a frozen run.
Schematic PDF page 3 explicitly draws separate external `R1 Helligkeit` and
`R2 Kontrast` panel controls. Page 18 has a handwritten 10 kΩ/5 kΩ note, not
a factory value. Page 3's connector numbers have handwritten corrections, so
the external brightness-pot terminal map needs source review before it is
transcribed into the connected circuit.
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
Manual PDF page 31 explicitly places width R5 on BP3 (012-6931) and calls for
adjusting it to 210 mm. Source schematic PDF page 10 draws that R5 wiper into
the A1/TDA1060 operating-voltage circuit, with 41P and 22P outputs. The
current connected run supplies fixed ideal 41 V and 22 V rails and excludes
this circuit. Thus R5 cannot change width in the present model. An ideal-rail
value labeled `R5` would not reproduce the source adjustment path; the
conflict between the manual trim requirement and the ideal-rail simplification
needs an explicit circuit-scope decision before calibration can be frozen.

The isolated ngspice 47 runtime was built from the exact archived source hash
under ignored `build/monitor/runtime-phase-a-gcc16/`. On this machine the
build uses Homebrew GCC 16 for C and G++ 16 for C++; the runtime receipt now
records both actual compilers. `monitor_runtime.verify()` checked the installed
binary and code-model hashes, and all ten runtime provenance and native
code-model tests passed against that installed runtime. This validates the
solver build, not the monitor circuit or calibration.
The first connected synthetic-grid attempt, using the default sparse/Gear
settings and T3 candidate `t3-44fb6052dcdfdb29`, failed at 0.115 ms with a
Q203 timestep collapse. A second attempt on the same candidate with KLU,
50 ns maximum step, 0.001 relative tolerance and 1e-8 current tolerance
advanced beyond that point, but reached only 5.20 ms of the required 78 ms
after 324 seconds and was stopped. Its recent median accepted step was about
1.5 ns. A separate one-millisecond trapezoidal diagnostic completed in about
68 seconds, giving no useful speedup. The archived trial directories under
`build/monitor/phase-a/grid-connected-20261118/`,
`grid-connected-fine-20261118/` and `trap-diagnostic-20261118/` are diagnostic
only: no complete final field, service score or calibration freeze resulted.
The last 0.204 ms of the incomplete KLU trace has three `h_hot` rising
crossings near line rate, but 235 `h_sync` crossings above 100 V. Their median
separation is about 0.19 µs, and `h_sync` ranges from roughly −18 to 382 V
in that window. This points to fast ringing in the TP17/T3 path as the reason
for very small solver steps; it is a diagnostic inference from an unsteady,
truncated trace, not a calibrated TP17 result. The next circuit investigation
should inspect T3 winding parasitics, rectifier loading and the source
polarity review before changing bounded magnetic assumptions.
A longer single-candidate diagnostic reused the same KLU/Gear grid deck under
`build/monitor/phase-a/grid-long-diagnostic-20261118/`. It was ended after
13.964 ms of the required 78 ms; `solve.json` records a failed, manually
terminated process (`returncode=-15`), 1,523 s of solver elapsed time and no
completed field. The partial raw file holds 5,967,737 complete 42-vector rows
but has no finalized point count. In its last 250,000 rows (13.375–13.964 ms),
`h_sync` ranges from −36 to 636 V and crosses upward through 100 V 2,864
times with a 0.075 µs median separation. Mean EHT over that incomplete tail is
about 1.63 kV when integrated over time, while modeled launch, emission and beam currents are all zero
in the same sampled tail. These are unsteady diagnostic values, not a service score or a
calibration result. The extended run confirms that fast ringing persists and
that completing four fields with this candidate/deck is not a useful next
calibration step before the T3/TP17 source and loading investigation.
The archived deck connects the T3 auxiliary `h_sync` node to rectifier
`D1131` (source V14) and has no explicit resistive shunt on that node. Source
PDF page 4 shows V14 at the auxiliary winding and carries a handwritten
warning that the newer 012-6922 connector arrangement is incompatible. A
lightly loaded winding resonance is therefore a plausible explanation for
the observed high-frequency crossings, but the source does not establish a
missing damping resistor. The connector, diode direction and winding polarity
remain explicit human schematic-review questions; no damping element is
silently added to the calibration circuit.
`partial_trace_diagnostic.py` streams all 5,967,737 complete rows of this
unfinalized raw file, refuses malformed samples, and labels its output
diagnostic-only. It integrates EHT over elapsed time because adaptive solver
samples are unevenly spaced. The input SHA-256 is
`a048fbe2de8c8996bb5cabb14a68c5e2538648d0138f8d6aa508a30d902741ad`;
the ignored report is `grid-long-diagnostic-20261118/partial-evolution.json`.
In successive 1 ms
windows, upward `h_sync` crossings through 100 V climb from 193 at 3–4 ms to
8,635 at 7–8 ms and 13,897 at 9–10 ms. The 9–10 ms window's mean EHT is
about 1.70 kV and its peak modeled launch current is 3.71 µA; at 11–12 ms,
the time-mean EHT is about 1.53 kV and modeled launch current is zero throughout.
These counts cover an incomplete first field and do not establish a waveform
period or final TP17 amplitude. They do establish that the long run was moving
away from the 11–12 kV target while fast crossings consumed solver steps, so
it must not be used as a calibration freeze or a settled grid result.
In the 9–10 ms window, the horizontal drive collector and yoke current each
cross their own midrange about 16 times (near line rate), while `h_sync`
crosses 100 V upward 13,897 times. The `h_feedback` midrange has 530 upward
crossings. This localizes the excess high-frequency activity to flyback-derived
nodes rather than the drive collector, but does not distinguish a wrong
winding, diode direction, parasitic assumption or load.

Two controlled 1 ms experiments changed only one T3 winding-group polarity
at a time in the archived KLU/Gear deck; all numerical magnetic parameters,
external connections, 50 ns maximum step and input grid were retained. The
compiled original T3 subcircuit was checked byte-for-byte against the deck
before replacement. The alternate solver receipts both report complete runs
in ignored directories `t3-aux-reverse-1ms-20261118-run/` and
`t3-hv-reverse-1ms-20261118-run/`. The baseline values below use only the
first millisecond of the stopped original trace. EHT values are integrated
over elapsed time; TP17 counts are upward 100 V crossings.

| T3 polarity hypothesis | Mean EHT, first 1 ms | TP17 crossings | TP14 swing | TP15 swing | TP17 swing |
|---|---:|---:|---:|---:|---:|
| All positive, `t3-44fb6052dcdfdb29` | 2.85 kV | 8 | 48.2 V | 29.1 V | 191.6 V |
| Auxiliary reversed, `t3-22e62e4df5229e36` | 2.77 kV | 455 | 49.9 V | 29.1 V | 215.4 V |
| High-voltage reversed, `t3-cdfa114cc8dc83f4` | 1.15 kV | 1 | 68.2 V | 29.1 V | 120.2 V |

The manual's approximate calibration swings are 70, 45 and 80 V for TP14,
TP15 and TP17. Auxiliary reversal increases early TP17 crossing activity;
high-voltage reversal moves TP14 closer to its guide while reducing EHT even
further. All three have zero modeled beam launch during this first millisecond.
These startup results cannot prune a T3 candidate or establish G3: the manual
comparisons require a settled, complete field after source connectivity and
polarity review.
The diagnostic can be regenerated with:

```sh
python3.14 verification/robotron-monitor/partial_trace_diagnostic.py \
  build/monitor/phase-a/grid-long-diagnostic-20261118/trace.raw \
  --output build/monitor/phase-a/grid-long-diagnostic-20261118/partial-evolution.json
```

Synthetic deck titles and experiment metadata now state the source kind, and
the freeze verifies that it is synthetic.

`phase_a_gates.py` implements the ordered G1–G8 frame gate policy and fails
closed on absent evidence. Its G1/G1b input can come from the connected
`native_sync_lock` report, which now counts extra flybacks and adjacent-line
jitter. Its G2 input can come from the existing three-field settling report.
The gate report checks that the service score belongs to the final electrical
trace, uses the current service register, contains each of the 17 points once,
and that readability names the selected native capture. The gate command
recomputes the saved score and reported native-frame EHT/retrace measurements
from the electrical trace before evaluating it.
Before evaluating the gates, it also verifies the archived full-text capture and
logical preview against their manifest, reselects the repeated native field,
and checks that the electrical trial metadata names that capture and field.
This closes the route by which a reported G8 hash could refer to a different
source; the G8 correlation still needs a measured image-comparison producer in
Phase B.
The gate command now reruns the connected-run settling analyzer on that same
final `trace.raw`. G1/G1b lock and adjacent-line jitter and G2 three-field
periodicity come from the recomputed trace, and any separately reported values
must match it. A persuasive JSON report cannot substitute for measured sync
edges or repeating electrical waveforms.
G3 now requires measured high voltage and retrace time tied to that electrical
trace, plus picture dimensions from the frozen synthetic-grid capture. G3 and
G5 require the supplied grid geometry to match the values computed and frozen
from that grid trial's electrical trace. Frozen target values alone cannot
pass G3. The native-frame measurement report still needs a Phase B producer;
the contract does not turn absent measurements into a pass.
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

The five voting BOM and five manual text passes are complete. Per-entry
reconciliation has 33 open parts, and human schematic review has six open
pages. The gate contract exists, but the stage and
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
inventory. The template is created once and cannot overwrite existing marks;
choose a new output filename after each audit refresh:

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

`source_review_guide.py` builds a local visual guide from the current audit.
It groups all open entries by source page, shows the independent OCR readings,
and links to the original parts-list and schematic page images. It checks the
source PDF hash and refuses missing page images. The guide contains no review
decisions or approval marks:

```sh
python3.14 verification/robotron-monitor/source_review_guide.py \
  --audit build/monitor/phase-a/inventory-audit-after-page15-correction-v2.json \
  --source-pdf build/monitor/phase-a/sources/older.pdf \
  --parts-images build/monitor/phase-a/ocr-workflow/review/pages/k7222-list \
  --schematic-images build/monitor/phase-a/schematic-pages \
  --output build/monitor/phase-a/source-review-guide-20261118.html
```

The current guide covers 33 open inventory entries on eight source pages and
all six schematic pages. Its local image and PDF links refer to files under
`build/monitor/phase-a/`; the source artifacts remain uncommitted review inputs.

Each blank part mark includes the current inventory value and independent OCR
readings as review context, with any excluded pass flagged as review-only.
Each human mark needs a source reading, disposition,
reason, reviewer and date.
An `unresolved` mark is valid only after the inventory entry itself is marked
unresolved. Schematic marks cover pages 3–4, 9–10, 16 and 18 and must record
KiCad connectivity, diode direction and winding polarity review. Marks bind to
the inventory entry, source PDF and current KiCad tree hashes; edits invalidate
stale marks. The current template from five voting vision passes and the
page-15 source correction fails the gate with 33 open parts and six open
schematic pages, as intended.
It is `build/monitor/phase-a/source-review-template-page15-corrected-v2-20261118.json`;
the matching gate report is
`build/monitor/phase-a/source-review-gate-page15-corrected-v2-20261118.json`. No human
marks have been entered.

After the third full-page vision pass and both crop passes on 2026-11-18, 227
entries had three agreeing readings per applicable table cell, matched the
inventory's value or type and had no identified source conflict. The other 33
remain open: page 6 C11/C18, page 8 T1, page 12 L4/L5/L6, page 14 R26,
19 device/fuse entries on page 15, and seven entries found only on schematics. The local
`build/monitor/phase-a/inventory-audit-after-page15-correction-v2.json` names every open entry and its
individual OCR readings; the completed parts-list crop passes are included in
`build/monitor/phase-a/ocr-workflow/review.zip`. These are review aids, not
human review marks. The five manual text passes are complete. An extra
full-page parts-list pass was stopped after five of eight pages because it
fabricated values and the planned five voting vision passes were already
complete. All 36 high-zoom schematic tiles on pages 3–4, 9–10, 16 and 18
have independent RapidOCR readings under
`build/monitor/phase-a/ocr-workflow/outputs/k7222-schematic/tiled/`. A separate
vision-model trial was stopped after six tiles because it repeated connector
designators until the response limit and invented references such as `R0.3`.
Those trial readings remain raw review aids, never schematic confirmation.
The extra `alt2` full-page parts-list run is retained as review-only evidence,
not a machine vote. Its page-12 output repeats values from neighboring
capacitor rows and stops before the printed L4/L5/L6 row; page 8 also calls
the T1 coil a transistor. Direct page-image inspection confirms those are OCR
fabrications. The audit records any `alt2` reading under `review_only_passes`
without letting it create a third agreeing pass. The primary, 300 DPI,
alternate-model and two crop vision runs remain the five voting vision passes.
On page 15, the source spans the 1 AE 15 diode designator list over four lines
and prints `13` in its quantity column after V12. The vision passes split and reassign parts
of that group differently. They also disagree around V3/V15 and the following
transistor rows. Those entries need direct source inspection rather than a
parser rule that would convert an OCR grouping guess into agreement.
Direct magnification resolves the supposed V13 conflict: `13` is the diode
group quantity, not a designator. A separate row lists V13 with V26 as KFY 18
transistors, and the three agreeing OCR passes can now confirm V13. The diode group's
V19–V25 range includes V22, which appears as a converter power device in the
schematic and page-20 auxiliary waveform. The review must resolve these
V22 readings against the schematic; neither OCR nor the inventory can
adjudicate them on its own.
The same source page prints the fuse designator `P1`, also visible at the
series input fuse on schematic PDF page 9 and read by the 300 DPI vision pass,
the left-crop pass and classic table OCR. The inventory, KiCad
`SourceId` and unsupported atlas target previously called it `F1`; they now
use `012-6931:P1`. Two vision passes read `F1`, so P1 remains in source review
rather than being promoted by a simple majority. The audit's designator
matcher now includes `P`, exposing the 300 DPI, left-crop and classic OCR P1
readings to reviewers; their descriptions and stock numbers still lack three
complete agreeing votes.

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
