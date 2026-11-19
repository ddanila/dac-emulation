# Phase A evidence and method status

> **Superseded in part (2026-11-19).** The revised [plan](PLAN.md) removes
> every human-review requirement and every stop-for-decision point. Where this
> record says a reading, connection or waveform "needs human review" or
> "source review", read: to be closed by agent reads and functional checks
> under plan steps A1–A4. Where it declines to add damping or typical values
> because no document prints them, the plan's `class-typical` tier now allows
> them. The connected startup diagnostics below are kept as history and are
> not evidence about the sustained state. The facts recorded here stand.

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
The freeze also records the exact T3 winding-graph hash and every KiCad sheet
assembled into its synthetic-grid trial. Freeze creation checks these hashes
against the trial archive; subsequent verification checks them against the
current files. An A1 correction to the winding map or assembled schematics
therefore invalidates the old calibration before native rendering.

Before a grid trial can freeze, `calibration_contract.py` now reruns
`steady_supply.assess()` on its complete electrical trace and the selected
synthetic source. The last three fields must pass the existing flyback/sync
lock, waveform periodicity, core-flux, current, EHT and held-heater checks.
The settling report is included in the hashed freeze and checked again when
the freeze is read. A completed solver run that briefly matches TP14/15/17 or
11–12 kV during startup cannot be frozen as a sustained calibration.
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
width) are absent from the assembled sheets. Source schematic page 9 draws R4
in the L1/L2, R2 and E1–E4 horizontal-centring bridge, separate from the
page-10 R5 converter feedback branch. The R4 bridge might be added while
retaining ideal rails, but its X1 connector links and bridge position require
the A1 schematic review. Recording nominal settings for either absent control
cannot apply the manual's step 8. The separate brightness control is likewise
not bound to a model parameter; R28 is the dark-raster preset and is not a
substitute. The freeze refuses these three unbound controls rather than
recording their proposed settings as applied. The vertical linearity model
and trim bindings now use the printed R59/R60 designators
(`linearity_r59`/`linearity_r60`) rather than
assigning either to an upper or lower screen region. A fresh KiCad export
confirms R59 and R60 remain on separate `lin_r59` and `lin_r60` branches at
their original 47 kΩ values. Manual pages 15 and 32 still disagree about the
screen-region roles; schematic/source review must resolve that claim before
it is used in calibration.
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
Each trim record now names its actual numbered manual steps and includes an
observation, as well as the setting. The blank `trim_record_template()` supplies
the step numbers; arbitrary labels such as `"manual"` cannot pass the freeze.
R28 records steps 2 and 6, and the external brightness control records steps
2, 6 and 7 because the procedure revisits them. Focus has no numbered
adjustment step in pages 29–32, so its record cites the page-6 visibility
criterion. These fields document the operator's basis for a setting; they do
not verify a claimed physical meter reading or make an unbound control work.

The linearity keys and connected model parameters identify R59 and R60 by part
number without assigning upper or lower screen regions: manual pages 15 and 32
disagree about those roles. The physical setting can be applied by designator;
the conflicting screen-region interpretation still needs source review.

A fresh `steady_supply.assemble()` export shows neither 012-6931:R4 nor
012-6931:R5 in the connected assembly. The former is the unmodeled centring
bridge on source page 9; the latter is confined to the excluded converter
sheet on page 10. Both appear in the inventory and manual geometry procedure.
Their connections and control effects need schematic review before a B6 trim
setting can be claimed as applied to the simulated monitor. The other trim
settings are recorded, but a future grid calibration must verify their actual
physical-to-model application.
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

The same source page carries the auxiliary `SYNCH` output to BP3, whose
page-10 input uses R1 (100 kΩ), V1's clamp and V2's transistor stage. The
ideal-rail assembly omits that converter sync input. A controlled diagnostic
restored only the input branch as transcribed in
`k7222-11-converter.kicad_sch`: R800, D801, Q802, R803 and R804, using the
converter profile's nominal bounded device models and the assembly's ideal
12 V rail. The complete 4 ms run is archived outside version control at
`build/monitor/phase-a/converter-sync-load-4ms-20261118-run/` with deck hash
`f6997c61bcabe3e0d5e0a1b10aa675eb1f89ceb05ae03e035ec5fa4492330464`.
It differs from the stopped original deck only in this input branch and its
4 ms stop time. The source input limits the 3–4 ms TP17 peak from 611 to
339 V, but upward TP17 crossings through 100 V increase from 193 to 406,
and time-mean EHT falls from 3.36 to 2.85 kV. The preceding 0–1, 1–2 and
2–3 ms crossing counts are 12, 18 and 56 with the input, versus 8, 28 and
42 without it. The completed trial is still only a startup diagnostic; it
does not demonstrate periodic operation or the manual's 11–12 kV target.
The missing input load is not a sufficient explanation for the connected
run's failure, so it was not promoted into the calibration model. T3
connectivity, polarity and loading remain the priority for the A1 review.

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
Manual PDF page 19 identifies T3's high-voltage winding terminals as 1 and
16. On source schematic page 4, V21 appears between X1:1 and the X1:2 EHT
output, whereas the earlier unverified winding graph placed `X1_2` in its
`upper_taps` magnetic group and the KiCad transcription connected an external
V21 model to `X1_16`. This identified a specific A1 connector, diode and
return-path question; the scan does not establish every winding
connection or the physical polarity.

An [independent ÜHA78 repair account](https://www.sax.de/~zander/zubehoer/k7222/uha78rep.pdf)
describes a separate selenium rectifier rod and a two-lead high-voltage coil
in a K7222.25. It is firsthand evidence about that later repair, not a pinout
for the .11/.21 source design; no .11 T3 connection is inferred from it.

An isolated topology diagnostic removed `X1_2` from that magnetic group and
its matching X1136 port while retaining the original all-positive candidate's
remaining sections, parameters and external circuit. The ignored deck is
`build/monitor/phase-a/t3-x1-2-no-winding-1ms-20261118-run/run.cir` (SHA-256
`3c028dedb22648701ed1fb329eebf2099a8d153bf2819a79d07ba4808bfb7cc5`).
It was stopped after 0.934 ms and 423,984 complete rows; the solver receipt
marks the run failed, and the raw file ends with a partial row. EHT remained
effectively zero. Removing this port also disconnected the model's existing
return through the upper-tap group, so the trial is an open-circuit diagnostic,
not a valid alternative winding model or a candidate comparison. The review
must determine X1:1, X1:2 and X1:16 roles and preserve the real return path
before another connected calibration attempt.
An additional controlled startup diagnostic retains the `X1_2` removal but
connects `X1_3` to the existing `h_upper2`/`X2_3` node, preserving the
upper-tap return to `X1_7`. Only the X1136 port assignment changed relative
to the failed diagnostic above. The complete 1 ms run is under ignored
`build/monitor/phase-a/t3-x1-2-return-x1-3-1ms-20261118-run/`, with the
single-line change in `hypothesis.json` and checked hashes in
`diagnostic-receipt.json`. The deck SHA-256 is
`e0aea308bfff7d67b4827352aa33fd23349aa6f51506742d81b0266a1db45713`;
the trace SHA-256 is
`9d5ace7bdc8cd82507db2d9f0a65428ec5646cabe5dd99fdf2ab80afb082ba35`.
Its 182,115 complete samples end at 1 ms. Time-averaged EHT is 2.75 kV,
versus 2.85 kV for the original candidate's first millisecond; TP17 has 12
upward 100 V crossings and 152 V peak-to-peak, versus 8 crossings and 192 V
in that original startup window. The recovered EHT confirms that the prior
zero-EHT result was an open-return artifact. Neither startup run meets the
11–12 kV target or establishes periodic operation, and this hypothesized
`X1_3` connection is not a reviewed source correction. The source review must
still resolve the remaining T3 pin map and winding polarity before a candidate is frozen.

The source-supported terminal correction is now in the live ideal-rail model.
`reference/k7222-11/t3-hv-terminal-read.json` records the source PDF hashes,
two differently cropped/resolved page-4 image hashes, the independent manual
page-19 reading, and the three settled HV-path edges.
Manual page 19 identifies the HV winding as X1:1–X1:16; independent views of
schematic page 4 (the 600 dpi page and a terminal crop) put V21's anode at
X1:1 and its cathode at X1:2, the EHT output. The magnetic graph now excludes
X1:2. The external V21 model is connected from X1:1 to EHT, and X1:16 is the
other HV winding terminal. The magnetic wrapper has 19 ports and 14 sections;
both bounded parameter sets and the exported KiCad sheet agree with that
decomposition. The old 20-port startup traces above remain historical
diagnostics and must not be compared as if they used the corrected topology.

To keep the remaining upper-tap group connected, the candidate ties X1:3 to
the X2:3 `h_upper2` node. This is the earlier startup-tested return hypothesis,
not a confirmed source read. The rest of page 4 still needs an independent
pin-to-pin transcription; winding continuity and relative polarity remain
unverified, and the A1 page-4 check and A5 design point remain open.

The T3 inventory entry itself is now closed separately: two differently
resolved page-4 views label the part `T3 Zeilentrafo`, confirming its
line-output transformer identity. `source-review-decisions.json` records both
image hashes and the scope of that decision. A fresh current-inventory OCR
audit plus `phase_a_review.evaluate` reports 227 machine-confirmed entries,
26 agent-resolved frame-path entries, no open frame-path part entries, and all
six schematic pages still open. This part decision does not verify a winding
graph or promote the startup traces into an A5 design point.

The original incomplete run's partial-trace summary can be regenerated with:

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
The final acceptance command now also requires the A1 source review as a
separate prerequisite. Its `--source-review-ocr-root`, `--source-review-pdf`
and `--source-review-marks` inputs are checked against all five voting parts-list
passes, the classic table source, the current inventory, `sources.json` and
the current KiCad tree. It reruns the 260-entry audit and human-mark evaluator;
the resulting source-review certificate is included in the gate report.
Even if G1–G8 all pass, `accepted` remains false until A1 passes. The current
blank marks reproduce 227 machine-confirmed entries, 33 open entries and six
open schematic pages; this is not an accepted A1 review.
The gate report checks that the service score belongs to the final electrical
trace, uses the current service register, contains each of the 17 points once,
and that readability names the selected native capture. The gate command
recomputes the saved score and reported native-frame EHT/retrace measurements
from the electrical trace before evaluating it.
Before evaluating the gates, it also verifies the archived full-text capture and
logical preview against their manifest, reselects the repeated native field,
and checks that the electrical trial metadata names that capture and field.
This closes the route by which a reported G8 hash could refer to a different
source.
The final trial must also archive hashes of every ideal-rail assembly schematic
that match the current KiCad files. This binds its electrical circuit to the
same schematic tree evaluated by the A1 review gate; a source review of newer
KiCad files cannot qualify an older electrical trial.
The gate command now reruns the connected-run settling analyzer on that same
final `trace.raw`. G1/G1b lock and adjacent-line jitter and G2 three-field
periodicity come from the recomputed trace, and any separately reported values
must match it. A persuasive JSON report cannot substitute for measured sync
edges or repeating electrical waveforms.
For G6, `electrical_refinement.half_timestep_trace` and
`electrical_refinement.second_initialization_trace` point to the two completed
variant `trace.raw` files. The gate checks each variant's deck and solve
receipt, source identity, circuit parameters, timestep and initialization,
then recomputes the last-field waveform comparison against the scored native
trial. The largest relative RMS error across the monitored electrical probes
must be at most 1% for each variant. Reported G6 errors cannot override these
recomputed values. The variant runs themselves remain Phase B work.
For G7, `optical_refinement.base_archive`, `integration_archive` and
`spatial_archive` name the three `periodic_frame.py` output directories. The
gate re-exports the final field from the scored electrical `trace.raw`, checks
that its hash is the optical archive's electrical input, then reruns both
optical integration and 2× spatial comparisons. Both comparisons must pass;
the worse relative L2 error is the blocking G7 value. The native full-resolution
render and its refinement archives remain Phase B work.
G8 now regenerates the logical VIDEO bitmap from that verified native capture
and reads the unchanged base `frame.f32` archive used by G7. `readability_score.py`
fits one global, orientation-preserving affine transform from the two images'
intensity centroids and covariances, then computes Pearson correlation on a
216×156 area-sampled comparison grid. The fit is used only to sample pixels for
the score; it never alters the render or chooses a circuit parameter. The gate
recomputes the correlation and rejects a conflicting reported value. A shifted,
scaled synthetic copy of the archived full-text bitmap scores about 0.96 in the
regression test; a mirrored copy scores about 0.14. The actual connected native
frame and its G8 score remain to be produced in Phase B.
G3 now requires measured high voltage and retrace time tied to that electrical
trace, plus picture dimensions from the frozen synthetic-grid capture. G3 and
G5 require the supplied grid geometry to match the values computed and frozen
from that grid trial's electrical trace. Frozen target values alone cannot
pass G3. The native-frame measurement report still needs a Phase B producer;
the contract does not turn absent measurements into a pass.
G3/G4 also require
an identified reviewer to check each drawn waveform shape and the manual's
operating conditions; numeric agreement alone cannot pass them. Reviews now
bind to the exact service-score hash, its electrical trace and the current
manual register. Each point needs a dated reviewer and an observation note;
an old review cannot follow a changed trace, measurement window or register.
`waveform_review_template.py` makes blank, bound entries from a reproducible
score, without declaring any review complete:

```sh
python3.14 verification/robotron-monitor/waveform_review_template.py \
  --service-score build/monitor/example/service-score.json \
  --output build/monitor/example/waveform-review-template.json
```

The completed `waveform_reviews` object belongs in the final gate evidence.
These gates do not imply that Phase B measurements already pass.
`waveform_review_guide.py` builds a local visual aid from a reproducible,
bounded score. It plots all 17 mapped probes with min/max bins that retain
narrow flyback excursions, and links the hash-checked manual PDF pages 20–21.
The page images are previews; reviewers must use the original PDF and record
their own observations in the bound review bundle. For a diagnostic trace:

```sh
python3.14 verification/robotron-monitor/waveform_review_guide.py \
  --service-score build/monitor/example/service-score.json \
  --manual-pdf build/monitor/phase-a/sources/older-operation.pdf \
  --page-20-image build/monitor/phase-a/manual-text/page-20.png \
  --page-21-image build/monitor/phase-a/manual-text/page-21.png \
  --output build/monitor/example/waveform-review-guide.html
```

The first generated guide uses the completed but unsteady 1 ms T3-return
diagnostic and is stored under ignored
`build/monitor/phase-a/t3-x1-2-return-x1-3-1ms-20261118-run/`. It has no
review marks and cannot establish G3 or G4.

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
The schematic sections now call out the A3-critical T3/SYNCH path, R4
centring bridge, R5 converter feedback and external brightness wiring as
focused review questions; these prompts are not review marks.

Each blank part mark includes the current inventory value and independent OCR
readings as review context, with any excluded pass flagged as review-only.
Each human mark needs a source reading, disposition,
reason, reviewer and date.
An `unresolved` mark is valid only after the inventory entry itself is marked
unresolved. Schematic marks cover pages 3–4, 9–10, 16 and 18 and must record
KiCad connectivity, diode direction and winding polarity review. Marks bind to
the inventory entry, source PDF and current KiCad tree hashes; edits invalidate
stale marks. The current template from five voting vision passes, the page-15
source correction and the R59/R60 designator binding fails the gate with 33
open parts and six open schematic pages, as intended.
It is `build/monitor/phase-a/source-review-template-r59-r60-designators-20261118.json`;
the matching gate report is
`build/monitor/phase-a/source-review-gate-r59-r60-designators-20261118.json`. No human
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

### Agent-review gate migration (2026-11-19)

The revised PLAN removes the human-mark prerequisite. `phase_a_review.py` now
emits v2 agent-reading templates and requires either two agreeing independent
readings, each with a crop hash and method, or a bounded `class-typical` value
with a source and argument. The source PDF, inventory entry, and KiCad tree
hashes still bind decisions to the current artifacts. Its frame-path scope is
derived from the converter and power-input sheets excluded by the ideal-rail
assembly. On the saved audit, 227 entries are machine-confirmed, 26 open
entries remain in the frame path, and seven unresolved entries are confined to
the excluded supply sheets; all six schematic pages remain open. The latter
counts are diagnostics, not new source decisions or a passing A1 gate.

`phase_a_gates.py` accepts the v2 source report and no longer requires a named
reviewer or date. The prior v1 human-review template and report under ignored
`build/` are historical inputs, not evidence that the v2 gate passes.

### Machine waveform descriptors (2026-11-19)

Manual PDF pages 20–21 were read directly for all 17 test-point sketches.
`service-observations.json` now records the visible pulse polarity, sawtooth
direction or bipolar ramp class as `agent-read`, bound to the hashed manual.
Only point 5 has a numerical duty bound, from its printed 0.5 ms pulse in the
19.5 ms native field. Other sketches do not give a defensible numerical duty.

`service_score.py` now evaluates these descriptors from sampled traces. It
checks pulse sense and repetition, time-weighted duty where specified,
sampling resolution, sawtooth direction/reset and point 7's bipolar excursion.
Ramp features accept one complete final field because the connected runner
scores that field alone; G2 separately checks field-to-field periodicity.
G3 and G4 consume the computed shape result. The separate waveform-review
template and its gate requirement were removed; an unsupported assertion that
"shape agrees" can no longer pass either gate. G4 now applies the revised
PLAN's allowance of at most three explained held-out misses.

This does not finish A3. The score still uses raw trace amplitudes and has not
applied a class-typical EO2 bandwidth or single-probe loading. A
[manufacturer manual for the comparable RFT EO 203](https://www.mikrocontroller.net/attachment/269865/RFT_EO_203_Spec.pdf)
lists 10 MHz bandwidth and 1 MΩ/48 pF direct input, with a separate 10 MΩ/20 pF
accessory figure; it is a candidate range, not proof of the exact EO2 setup.
The source figure also leaves stimulus and trim settings unspecified, so the
grid choice must be recorded with each stage score.

### Initial design-point constraints (2026-11-19)

`reference/k7222-11/design-point.json` records a partial A5 derivation from
the 2 kByte timing, the C27/C30 values and the current source connectivity
candidate. Treating the 16 µs horizontal retrace as half an LC cycle gives
2.36 mH effective resonant inductance (2.14–2.62 mH from the printed capacitor
tolerances). An ideal lossless pulse formula gives about 228 V from 41 V alone,
or 334–390 V if the handwritten 60–70 V boost annotation is the trace supply.
The 11–12 kV anode target would require an effective high-voltage pulse ratio
of 28–36 in the boost case. These are design bounds, not a selected T3 winding
or a calibrated result; the original rectifier path and supply still need
source review. The pulse equation is consistent with the
[published horizontal-output derivation](https://patents.google.com/patent/JP2001313845A/en).

The page-21 service figure labels TP15 as the **V13 collector**, so its 45 Vpp
is a driver-stage check and cannot directly determine a T3 auxiliary winding
ratio. TP14's feedback path and TP17's rectified pulse likewise need their
source connections resolved before a turns ratio is claimed. This corrects
the overly broad inference suggested by the current A5 wording.

The existing assumed tube/yoke geometry also fails a design target before any
electrical calibration: with the current 10 mm neck radius, 11.5 kV anode and
the geometry-derived field-per-ampere, the trajectory reaches only 90.87 mm
half-width before neck clipping, against the manual's 105 mm half-width.
Halving the trajectory integration step twice did not change that result.
A 12 mm assumed neck radius can reach the target mathematically, but exceeds
the outside radius in a scanned [M31-120/B31-G family outline](https://www.elektroncso.hu/cikkek/crt_m31.gif)
(SHA-256 `edf8c17c807b174e3f90e2a24946fd7e5342fcd9c3448e4788d9c7f0848ea35d`)
draws a 20 mm outside neck diameter with +0.8/-0.5 mm tolerance. Even its
maximum outside radius is 10.4 mm; the glass thickness makes the inner beam
aperture smaller. This drawing is family geometry, not a measurement of the
installed B31G22 or its inner aperture.

One bounded design probe shortens the assumed cosine-sheet field from 40 to
34.7 mm without enlarging the 10 mm internal aperture. Re-derived horizontal
inductance is 3.995 mH, field factor 8.555 mT/A, and ideal sheet packing is
0.648 against a 0.65 ceiling. At 11.5 kV, 350 V G2 and 4 kV focus, the
reduced trajectory reaches the documented 105 mm half-width at about 0.63245 A;
the neck-clip threshold is 0.63538 A and 105.575 mm half-width. Three
integration steps (0.2, 0.1 and 0.05 mm) agree to sub-nanometre half-width.
This is a narrow mathematical feasibility result, not a selected yoke design:
the assumed 10 mm internal radius, 280 mm beam-origin-to-screen distance,
active yoke length and winding packing have no specimen measurement. The A5
peak current remains open.

### First agent source decisions (2026-11-19)

`reference/k7222-11/source-review-decisions.json` records 19 A1 readings
against the hashed `older.pdf` and inventory entries. Each decision has two
image hashes from different crops or resolutions and an explicit argument.
Direct reads of parts-list page 6 confirm C11 as 0.33 µF/20% and C18 as
10 µF/20%; page 8 confirms T1's `Spule VST` identity and stock number; page 14
confirms R26 as 130 Ω/2%. The R26 stock-number cell appears malformed, so the
decision claims only its electrical value. Page 15 confirms the printed
identities of eleven frame-path `1 AE 15` diodes, V3 and V15 zeners, and V5/V11
transistors. The handwritten alternative over the V5/V11 row is not promoted
to the printed type. None of these identity decisions supplies the A2 device
parameters. The V22 parts-list/schematic conflict remains separate.

A fresh audit and `phase_a_review.evaluate` accept all 19 decisions: 227 entries
remain machine-confirmed, seven frame-path parts and all six schematic pages
remain open. The seven are `012-6921:R41`, `V18`, `V21`, `T3`, and
`012-6931:V27`, `V28`, `V4`. Seven converter-only entries remain outside the
ideal-rail A1 gate. The source image paths in the decision file are local
derivatives under ignored `build/`; their SHA-256 values and the source PDF
hash identify the inspected evidence. The gate still fails, as it should.

### Comparable service-instrument bandwidth (2026-11-19)

`reference/k7222-11/service-instrument.json` records a bounded
`class-typical` observation model based on the
[RFT EO 203 manufacturer manual](https://www.mikrocontroller.net/attachment/269865/RFT_EO_203_Spec.pdf),
not an EO2 specification. The manual lists a 10 MHz vertical channel (5 MHz
for high-voltage attenuator settings), 1 MΩ/48 pF direct input and a
10 MΩ/20 pF accessory. `service_score.py` now applies a single-pole 10 MHz
response to the trace before scoring amplitudes and shapes, and reports raw
amplitudes alongside the filtered ones. A 10 MHz sine test checks the expected
approximately 3 dB response. The instrument file is copied into assembly
provenance.

`service_probe.py` now performs the dedicated circuit solves: it generates one
deck per selected test point with only that point shunted by the bounded
1 MΩ/48 pF direct-input equivalent, runs ngspice, and records hashes of the
base deck, base trace, loaded decks, loaded traces, logs and instrument model.
`service_score.py --probe-manifest` checks those artifacts before using each
loaded trace for amplitude and shape scoring. It retains the unprobed raw
measurement, reports the loaded unfiltered measurement, then applies the 10 MHz
bandwidth model. A high-impedance pulse-circuit test confirms the loaded solve
changes the amplitude and that a modified deck is rejected. Missing loaded
points remain explicitly diagnostic.

The manual figures do not identify an input picture or control settings. The
service register now records that omission and names the synthetic grid as the
comparison input; the scorer records `--stimulus grid` explicitly. Connected
stage scores still need actual per-point loaded solves and a recorded trim
configuration before the A3 comparison can be claimed for the frame. The EO
203 direct input remains a bounded `class-typical` stand-in for the unspecified
EO2 arrangement, so probe sensitivity must accompany a final comparison.

### R5 width-control equivalent (2026-11-19)

The page-10 converter drawing and a fresh KiCad netlist export agree that
`012-6931:R7` (30 kΩ) feeds the top of `R5` (1 kΩ), whose bottom reaches
ground through `R6` (2.4 kΩ). Its wiper goes to the TDA1060 feedback input.
At a fixed feedback voltage, the output ratio between two R5 settings is the
inverse ratio of `R6 + R5_bottom`; the common R7 and total R5 terms cancel.
The existing converter profile uses 0.63 as its uncalibrated nominal wiper
position. Anchoring the ideal 41 V output there gives a rail scale of
`(2400 + 1000 × 0.63)/(2400 + 1000 × position)`, bounded by 0.8912–1.2625
over the physical 0–1 travel.

`steady_supply.py` now applies that one scale to the 41 V, 22 V and −16 V
converter outputs, while the 12 V converter input remains fixed. The deck
declares `width_r5_position`, records the calculated rails in metadata, and
captures the rail voltages for later checks. `calibration_contract.py` binds
the manual's `picture_width_r5` trim to this actual parameter. A full assembly
deck generated at both ends and at 0.63 gives 41 V, 22 V and −16 V only at
the nominal point, with all three outputs changing together. This is a
design-derived equivalent based on the provisional page-10 topology, not a
calibrated width result; the A1 independent netlist and B6 grid adjustment
remain necessary.

### R4 horizontal-centring equivalent (2026-11-19)

Source schematic page 9 draws `012-6931:R4` (1 kΩ) in the L1/L2 centring
bridge with `R2` (150 Ω) and selectable E1–E4 links. The bridge's X1 links
still need the A1 independent netlist review, so the connected assembly uses
the fallback prescribed by PLAN.md: a DC current source across the horizontal
yoke, from `hy2` to `hy1`. The source's positive current returns through the
yoke from `hy1` to `hy2`. Its `centering_horizontal_r4_position` is bounded
to physical travel 0–1, with neutral 0.5. The source current is
`0.08 × (2 × position − 1)` A. The ±80 mA ceiling is the nominal
short-circuit limit from the page-9 12 V feed divided by the documented
150 Ω R2; it is a broad bound, not a prediction of the bridge's usable range.
Topology and neutral setting are labelled `class-typical` in deck metadata.

The manual's `centering_horizontal_r4_0126931` trim is bound to that position.
Full assembled decks at both endpoints and the midpoint show −80 mA, 0 and
+80 mA in the actual source. An ngspice DC operating-point solve of each deck
reports the same three values for `i(Lhorizontal)`, in order, with no other
trim changed. The logs are under ignored `build/monitor/phase-a/r4-check/`.
This establishes a connected electrical control, not a calibrated
picture-centre result. The A1 bridge review may replace this equivalent, and
B6 must still measure the grid and select a setting.

### External brightness R1 binding (2026-11-19)

The page-18 interconnection drawing assigns panel R1 terminals E, S and A to
35P, HRS and HRA on main-board connector X1; page 3 draws the same pot and
page 4 continues HRS/HRA into the V1 bias network. Their KiCad assembly nodes
are `p35`, `collector_i` and `contrast_adjust`, respectively. The panel pot's
bottom-to-wiper segment is in parallel with the board's R1 (2.7 kΩ). The
handwritten page-18 10 kΩ value, with 5 kΩ alternative, is carried as a
bounded `class-typical` `brightness_pot_r` rather than a factory specification.
The deck uses `brightness_position` from 0 at HRA to 1 at 35P and a 1 Ω
contact floor at either stop. The calibration contract binds the external
`brightness` trim to this position, separately from board R28's dark-raster
preset.

Neck-board X3:1 and X3:2 are the service-meter terminals across its 390 Ω
cathode resistor, not the panel pot; page 16 and the manual's beam-current
procedure confirm that role. Three DC operating-point trials of the assembled
deck with the 10 kΩ pot at positions 0, 0.5 and 1 change `v(collector_i)`
from 11.70 V to 12.68 V to 12.88 V. This proves the trim reaches the modeled
V1 bias node. At the top endpoint the provisional 35P source falls to about
20 V under load, a stage-model limitation to recheck in Phase B. Neither
these DC trials nor the terminal reading close A1's independent page-3/4/18
netlist review or demonstrate calibrated brightness on a sustained grid.

### V4 source identity and R41 discrepancy (2026-11-19)

Two page-15 views, the full parts-list image and a separate device crop,
independently print `012-6931:V4` as **Transistor SF 1260 TGL
200-8439**. `source-review-decisions.json` now records that identity with both
image hashes. Re-evaluating the saved 260-entry audit accepts 20 agent source
decisions and leaves six frame-path parts open; all six schematic pages still
need independent netlists. V4's electrical model remains A2 work.

Manual page 17 calls `R41` a thermistor that compensates the horizontal
generator and output transistor. Page-3 source crops at 300, 600 and 900 dpi
show the upper thermistor symbol **labelled R43** in series between R25 and
the R24 trim; no numeric value is printed. The page-8 board parts list skips
R41 between R40 and R42. The inventory had misclassified manual R41 as a
potentiometer, and the KiCad oscillator omitted this series element. The
inventory now identifies R41 as a thermistor, while its correspondence to
the annotated R43 is explicitly provisional. The oscillator netlist exports
R25 → provisional R41/R43 → R24. The fixed-temperature equivalent is
`horizontal_r41_r = 470 Ω`, bounded 100–2000 Ω, based on the documented
470 Ω R13 thermistor in the same chain. This is a `class-typical` decision,
not a recovered factory R41 value, designator map or temperature curve.

Isolated 0.4 ms oscillator bench runs at 100, 470 and 2000 Ω all completed.
Over their final quarter, `v(h_control)` averages 1.0532, 1.0183 and
0.9014 V; `v(h_reactbase)` averages 0.9994, 0.9661 and 0.8627 V; and
`v(h_outputbase)` averages 0.3686, 0.3300 and 0.3239 V. Relative to the
nominal, the low bound moves the secondary by 11.7%, and the high bound moves
the control/reactance nodes by about 11%. Thus the unknown R41 value is
material to the stage, so its bounds remain exposed to later analysis. The
KiCad export and 49 affected tests pass. The saved A1 audit accepts 21
agent-resolved decisions and leaves five frame-path parts plus all six
schematic pages open. This source correction does not itself settle the
page-3 A1 netlist check or establish a temperature response.

### Page-18 interconnection source transcription (2026-11-19)

`reference/k7222-11/page18-interconnect-transcription.json` records the
printed pin labels for the main board (012-6921), vertical board (012-6931),
neck board (012-6891), panel controls and yoke. It identifies four numbered
board-to-board cables and 18 signal-matched pin pairs from the page-18 drawing.
The source PDF and the 300-dpi page render are SHA-256 identified in that
file. This is a separate source transcription, not a completed A1 page mark.

Mechanical checks of the transcription find that every recorded cable pin
pair carries the same printed signal label at both ends. The X9 external
input labels and all eight page-18-labelled neck X1 pins agree with
`assembly.json`; neck X1:4 is unlabelled on page 18 and retains its separate
page-16 reading. The current assembly reference now points to the new
interconnect file. Page 18 still needs a KiCad-export comparison and
functional settlement of any differences before the A1 netlist gate can
close. This transcription also cannot settle T3's internal winding order.

`page18_frame_compare.py` compares the two frame-path neck cables against
freshly exported ideal-rail KiCad components and the neck pin map. The saved
`reference/k7222-11/page18-frame-comparison.json` records all eight pin pairs:
six signal nets occur on both board sheets. `INTENS` is absent on the main-board
KiCad sheet because its contrast path is assembled outside that sheet;
`10.7P` is absent on the neck sheet because the held heater branch is assembled
outside it. This is a semantic comparison, not the independent pin-to-pin
KiCad diff required by A1: the main-board sheet still lacks physical connector
pins. The other ten cable pairs, panel controls and yoke connections
also remain to be compared. The page-18 gate therefore stays open.

### Independent page-16 neck-board pin transcription (2026-11-19)

`reference/k7222-11/page16-neck-source-netlist.json` is a source-first read of
the 012-6891 neck-board drawing from the hashed `older.pdf` page 16, using a
600-dpi render and a separate lower-resolution render. It records 17 named
nets, all 39 terminals of the 19 discrete board parts, 17 physical connector
pins across X1/X2/X3, V1 collector/base/emitter, C1 polarity, and the anode and
cathode of all six V2 diode sections. Undotted wire crossings and the drawn
tube-electrode couplings are kept distinct from DC junctions.

`page16_neck_compare.py` exports the current KiCad neck sheet afresh and
compares every component pin by source part ID, pin number and net. The sheet
now includes three physical connector symbols, marked audit-only so they do
not enter the SPICE component list. The electrical reader validates their
pin-to-net map before omitting them. All 39 component pins and all 17 physical
connector pins match the independent page-16 read, including six diode
directions. A changed diode or connector pin is rejected in tests. The saved
comparison contains source, sheet and assembly hashes. This closes the
pin-representation gap on page 16; the remaining function evidence is
described below.

`page16_neck_static.py` now recomputes the saved pin comparison, checks that
all 17 source nets have a DC route through their external inputs, resistors or
possible diode conduction, and solves the isolated neck bench at its four
settled input states. The report records exact source/model/deck hashes and
node voltages. With video low, V1 collector is 34.34 V and base is near zero;
with video high, collector is 0.72 V and base is 0.78 V. Raising the intensity
input while video is high moves the cathode output from 0.27 V to 4.39 V. C1's
source polarity puts its positive terminal on 41P and negative terminal on OO.
All declared static/function checks pass; a disconnected source net is caught
by the path test.

This isolated bench uses ideal external rails and a fixed 20 µA beam-current
load. It has no CRT emission response and cannot reproduce page 16's C15
measuring-cable dark/bright millivolt note. That missing source observation
keeps the A1 page-16 function check open despite the complete pin comparison
and plausible transistor operating points.

### Vertical output transistor model bounds (2026-11-19)

The printed page-10 vertical output is provisionally modeled as upper NPN
V27 and lower PNP V28. Handwritten notes put `BD140` beside V27 and `BD139`
beside V28; the [ST BD139/BD140 data sheet](https://www.st.com/resource/en/datasheet/bd139.pdf)
identifies BD139 as NPN and BD140 as PNP. Those annotations therefore conflict
with the present printed-stage polarity interpretation and are not promoted to
factory identities. Manual page 14 identifies the V18/V27 and V26/V28
Darlington pairs but supplies no external output transistor type. The page-10
A1 netlist and polarity check remains open.

The new partial `reference/k7222-11/device-model-register.json` records a
BD139-class NPN candidate for V27 and BD140-class PNP candidate for V28, with
the conflict and remaining model work explicit. The shared `output_bf` bound
is now 25–250 at nominal 60, following ST's 40–250 at 150 mA and minimum 25
at 5 mA and 500 mA. Separate forward transit-time bounds are exposed for the
two polarities. Their nominal 0.7 ns NPN and 2 ns PNP values come from a
bounded `1/(2πfT)` estimate using the [Philips 1985 data book](https://bitsavers.trailing-edge.com/components/philips/_dataBooks/1986_S04a_Philips_Low-Frequency_Power_Transistors_and_Hybrid_Modules.pdf),
which lists typical 250 MHz and 75 MHz respectively at 50 mA and 5 V. Junction
capacitance means these transit times are not by themselves a verified model
fT. Saturation and the other fixed model parameters remain A2 work. The
isolated vertical-output stage completes with the revised models; no sustained
grid or factory transistor identification is inferred.

### EHT rectifier class and model bound (2026-11-19)

The `.11` board inventory has no factory type for assembly V21. Source
schematic page 4 draws V21 as the EHT rectifier from T3 X1:1 to X1:2, and
operating-manual page 19 says it charges the tube to 11–12 kV. The A1 part
review now assigns only a bounded `class-typical` 12–16 kV reverse-voltage
class, nominal 15 kV. This resolves the missing *part identity decision* by
the plan's fallback without claiming a historical type or closing page-4
connectivity. At that review point the audit reported 22 agent-resolved
frame-path entries and four open parts: V18, T3, V27 and V28.

The [Rectron R12000H data sheet](https://www.rectron.com/public/product_datasheets/r12000h.pdf)
describes a 12 kV fast CRT/FBT rectifier with maximum 100 ns reverse recovery
and 1 pF zero-bias junction capacitance. The
[Semtech SDH15K data-book pages 348–349](https://www.semtech.com/uploads/design-support/SG-SEMTECH-PD-DATABOOK.pdf)
give 15 kV working reverse voltage, 2 µA maximum reverse leakage at 25 °C,
and 2.5 µs maximum recovery under a different test current. The partial A2
register records these as alternative class limits. `HOR_HV_RECT` now states
the 15 kV breakdown and 2 µA knee current explicitly, alongside its existing
1 pF capacitance and 100 ns transit-time proxy. SPICE `TT` is not the measured
reverse-recovery time; IS, N and RS still need review before this model can
satisfy A2. The X1:1-to-X1:2 V21 path was later corrected in the live model;
the remaining T3 winding return and polarity are still open for A5.

### Horizontal output transistor class (2026-11-19)

The `.11` board BOM does not print a type for assembly V18. The page-4
schematic and operating-manual page 19 place it at the 16 kHz T3 output stage;
`SU165` on the scan is handwritten and remains an annotation. The
[ST BU508AF data sheet](https://www.st.com/resource/en/datasheet/bu508af.pdf)
provides a comparable CRT horizontal-output NPN class, not a historical part
identification. It gives hFE 10–30 at 0.1 A and a minimum 5 at 4.5 A, both at
5 V collector-emitter bias. The existing `HOR_OUTPUT_N` BF=20 lies in that
5–30 class bound, so the A1 part entry is closed as `class-typical`. At that
review point the audit had 23 resolved frame-path entries and three open:
T3, V27 and V28.

ST also specifies at most 1 V saturation at 4.5 A/1.6 A base drive and
typical 2.5 µs storage plus 0.2 µs fall time in an inductive 16 kHz test.
Those are recorded as A2 comparison targets, not claimed properties of the
current SPICE model. Its fixed IS, VAF, junction capacitances and transit
times remain unbounded, and the T3 stage still lacks a verified topology.

### Vertical output part-identity decisions (2026-11-19)

The A1 part entries for V27 and V28 now use the bounded `class-typical`
hFE=60 candidate with 25–250 bounds described above. The contradictory
handwritten labels are not treated as factory types. The page-10 independent
netlist and transistor-arrow check still must settle the actual upper/lower
connection. The current A1 audit has 25 resolved frame-path entries and only
T3 open as a part entry. A2 remains partial for these devices.

### Partial class-typical register (2026-11-19)

`reference/k7222-11/class-typical-register.json` consolidates 16 currently
cited bounded entries: the V18/V21/V27/V28 and neck V1 semiconductor
candidates, comparable service-scope values, a B31-G family neck outside
diameter, the provisional
R41 value and the external brightness-pot range. Each entry identifies its
stage, source, bounds and model location. The file stays `partial`: fixed SPICE
parameters, tube emission/heater properties, T3 parasitics, yoke sensitivity
and other assembly assumptions still lack appropriate class sources or
design-derived bounds. Its proxy transit-time rows do not establish measured
recovery or transistor switching times. A6 is therefore not closed, and B8
cannot treat the register as a complete sensitivity basis.

### Neck SSY20A data-sheet DC comparison (2026-11-19)

The page-16 inventory prints `SSY20A` for neck-board V1. The
[SSY20 data sheet archived in DDR-Halbleiter](https://www.tiffe.de/robotron/Bausteinuebersicht/DDR-Halbleiter.pdf)
gives group-A h21E 18–35 at 500 mA/1.3 V, VCEsat at most 1 V at 500 mA/50 mA
base current, and 50 ns turn-on and 100 ns turn-off maxima under a specified
80-ohm switching test. Mapping the printed `A` suffix to group A is an
inference. A [period DDR transistor list](https://www.alphacron.de/download/hardware/ddr_si_transistoren.pdf)
names BSY34 as the SSY20 comparison type; the archived BSY34 data sheet gives
fT at least 250 MHz at 30 mA/10 V. That fT value is a comparison target, not
a direct SSY20 specification.

`neck_transistor_check.py` solves the live neck-model transistor with ngspice
at the SSY20 gain and saturation biases. Its saved
`reference/k7222-11/ssy20-model-dc-check.json` records h21E 18.14, 26.21 and
34.98 for the lower, nominal and upper BF candidates (18, 26 and 34.7),
respectively. At 50 mA base drive with a 40 V/80-ohm load, the same cases carry
about 499 mA collector current and 0.085, 0.077 and 0.073 V collector voltage.
The upper BF was reduced from the data-sheet h21E upper endpoint of 35 because
BF is a low-injection model parameter: BF=35 produced h21E 35.28 at the stated
bias. These DC checks justify only the bounded BF proxy and saturation response
of this model; switching times, fT and the other assumed transistor parameters
still need A2 review. The page-16 isolated stage check was regenerated with
BF=26 and still passes; bright-video collector voltage changes from about
0.72 V to 0.77 V. The CRT emission and C15 observation gap remains open in A1.
