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
The point-8 figure additionally labels R48/V20. A later 400 dpi source reread
found that its approximately 17 V arrow ends at the drawn zero line, while a
separate approximately 10 V arrow spans a shoulder above zero to the negative
trough. Neither is a full-trace peak-to-peak value. Page 10 places R48/V20 on
a distinct bias net from X2:3; the figure does not settle which node owns the
second arrow. The [source reread](reference/k7222-11/tp8-waveform-source-read.json)
records the image hashes and keeps that attribution open.
The [dual-node loaded diagnostic](reference/k7222-11/tp8-dual-node-loaded-diagnostic.json)
adds R48/V20 as a recorded stage probe and compares independent EO 203-equivalent
loads on it and X2:3. Their final-field waveforms differ by at most 0.768 V.
The exploratory post-step descent estimates span 6.49–6.83 V at X2:3 and
7.41–7.75 V at R48/V20 over 128/256 phase bins. The R48/V20 estimate crosses
the ±25% lower bound of the 10 V annotation as resolution changes; 64 bins
also merge the reset into the descent. This does not identify the annotation
or justify a numeric pass. A qualified reset-excluding feature and source
attribution remain A3 work.
The [long-line fit check](reference/k7222-11/tp8-ramp-feature-sensitivity.json)
adds a reproducible reset-excluding diagnostic and synthetic tests. It is
stable across 64–256 bins at a 2% fit-error allowance, but R48/V20 crosses
the 7.5 V lower target when that allowance is tightened to 1%. No source
defines the allowance; picking the passing value would turn the check into a
fit. The score therefore still treats the 10 V arrow as unresolved.
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

`page4_t3_hv_compare.py` now exports the live horizontal-output KiCad sheet
and checks these three source-read HV edges against its T3 and V21 pins and
the winding-wrapper port list. The saved
`reference/k7222-11/page4-t3-hv-comparison.json` passes seven structural
checks: X1:1 meets V21's anode, its cathode is the EHT net, X1:16 remains a
distinct winding terminal, X1:2 is absent from the magnetic ports, and the
pins are complete. A reversed V21 pin assignment fails the test. This is a
machine-checked partial page-4 comparison, not an internal winding read.

`reference/k7222-11/t3-drive-polarity-source-read.json` records a further
page-4 re-read at 300 dpi and a separate 600 dpi primary-stage crop. It places
T3 X2:7 on V18's collector and V17's cathode, with V17's anode at 0 V. The
fresh KiCad export matches those edges. This re-read followed model inspection,
so it is a functional source check, not the independent whole-page A1 netlist.
The source HV read puts V21's anode at X1:1 and EHT at its cathode. During a
positive collector flyback pulse, that rectifier needs X1:1 above X1:16.

`t3_flyback_sign.py` applies an isolated 1 V positive pulse from X2:7 to
X2:4, shunts each other T3 terminal by 1 GΩ, and samples
`V(X1:1)-V(X1:16)` near 80 ns for all sixteen existing relative-polarity
candidates. The XSPICE and flux backends agree on sign for all sixteen; the
eight with negative relative HV winding polarity yield a positive secondary
pulse. The eight with positive polarity, including the all-positive startup
candidate, yield a negative one and are rejected by this conditional
flyback-phase rule. `design-point.json` lists the eight retained IDs and
`reference/k7222-11/t3-flyback-sign-filter.json` records the source pins,
both backend results and rejection reason. This test establishes neither EHT
amplitude nor sustained operation. If the assumed tap order or X1:3-to-X2:3
return changes, the filter must be recalculated.

To keep the remaining upper-tap group connected, the candidate ties X1:3 to
the X2:3 `h_upper2` node. This is the earlier startup-tested return hypothesis,
not a confirmed source read. The rest of page 4 still needs an independent
pin-to-pin transcription; winding continuity and historical polarity remain
unverified despite the conditional HV-sign filter, and the A1 page-4 check and
A5 design point remain open.

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
itself supplies the focus criterion above. Its exact tube parameters remain
unverified.

A further 2026-11-20 manufacturer-source check found the [RFT B 30 G 1 entry,
printed page 29](https://frank.pocnet.net/other/RFT/RFT_Spezialroehren_1959.pdf):
its 30 cm monochrome tube specifies a 6.3 V, approximately 0.47 A heater.
This is a *comparator*, not a B31G22 identification. The active nominal
electrothermal model, solved behind the documented 12 V rail and 15 ohm R22,
settles at about 10.989 V, 0.0674 A and 0.741 W in the heater. Independently,
the B30G1 operating point would need 6.3 + 0.47 × 15 = 13.35 V upstream of
R22, above the model's 12 V rail. Thus the B30G1 values cannot be transferred
as bounds or used to tune the installed heater. The
[class-typical register](reference/k7222-11/class-typical-register.json)
records this rejected comparator; the B31G22 heater and emission bounds remain
open. The numerical model check is reproducible with `steady_supply.heater_equilibrium()`
and `electrothermal.parameters()`.

A later [Tungsram 1976 M31-120 manufacturer page](https://frank.pocnet.net/other/Tungsram/Tungsram_ElectronTubes_Semiconductors_1976.pdf)
(PDF page 96, printed II-46; SHA-256 recorded in the
[heater class check](reference/k7222-11/tube-heater-class-check.json)) provides
a much closer 31 cm, 110° monitor-tube comparator. It prints an 11 V, 68 mA
heater, 11 kV typical anode, 250 V G2 and 35–69 V grid-control cut-off.
This is primary data for the **M31-120**, not proof that the installed
B31G22 has the same gun. The independent page-image and text reads agree.
Its hot heater resistance is 161.765 Ω; with source R22 at 15 Ω, that exact
point needs 12.02 V ahead of R22. The active 12 V branch's 163.036 Ω
equilibrium resistance gives 10.989 V and 67.402 mA, 0.10% and 0.88% below
the comparator. A declared ±20% hot-resistance sensitivity produces
57.384–83.096 mA and 10.754–11.139 V in the same ideal-rail branch; this
spread is an engineering bound, not a Tungsram or B31G22 limit. The A6
register now records that operating point, while cold resistance,
temperature coefficient, thermal transfer and emission still need evidence.

The same Tungsram page prints G2 = 250 V, G4 = 0–350 V and a 35–69 V
grid-control cut-off. The [cut-off class check](reference/k7222-11/tube-cutoff-class-check.json)
compares that source with the active CRT law, whose effective G2/G1 factor
`grid2_mu` was 10. At cathode = 0, that law then cut off at 250/10 = 25 V,
outside the M31-120 comparator range. It also produced zero demand at the
manual's approximate 15 V normal-bright cathode under the isolated page-16
neck rails (G1 = −25 V, G2 = 350 V): its effective drive was −6.5 V.
The catalog range implies an effective factor of 3.62–7.14 for this law.
Under those same provisional neck rails, a 35 V dark cathode requires at
least 5.25 to cut off, and a 15 V bright cathode requires less than 8.375
to emit. Their conditional overlap is 5.25–7.14. The active nominal is now
6.5, giving a 38.46 V catalog-condition cut-off and, at the neck rails,
−11.54 V dark versus +11.54 V bright effective drive. An isolated held-warm
SPICE check confirms bright emission and dark cut-off. The broad 3.5–30
model bounds retain exploratory B31G22 uncertainty; values outside that
overlap are **not** qualified for the manual states. This model omits G4 and
the catalog characterizes a different tube, so the comparison is a bounded
nominal choice, not an installed-gun specification or a connected beam score.
The original B31G22 cut-off, G4 dependence, perveance and emission limit
remain open A6 work.

The A6 register also carries T3's active HV turns, HV resistance and
summed drive turns as three explicitly `assumed-bound` rows (204 total at
that update; 209 after later additions, including the CRT grid factor).
The register test checks those rows against the live winding hypothesis; their
presence records the gap and does not qualify the transformer.

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
page 4 continues HRS/HRA into the V1 bias network. The current deck maps them
to `p35`, `v1_base` and `contrast_adjust`, respectively; all six physical
X1 pins now match a fresh KiCad export. The panel pot's
bottom-to-wiper segment is in parallel with the board's R1 (2.7 kΩ). The
handwritten page-18 10 kΩ value, with 5 kΩ alternative, is carried as a
bounded `class-typical` `brightness_pot_r` rather than a factory specification.
The deck uses `brightness_position` from 0 at HRA to 1 at 35P and a 1 Ω
contact floor at either stop. The calibration contract binds the external
`brightness` trim to this position, separately from board R28's dark-raster
preset.

Neck-board X3:1 and X3:2 are the service-meter terminals across its 390 Ω
cathode resistor, not the panel pot; page 16 and the manual's beam-current
procedure confirm that role. The earlier DC voltage sequence attributed to
`collector_i` is superseded: that model net incorrectly joined V5's IS output
to the panel HRS wiper. The corrected wiper is `v1_base`; a fresh
source-addressed DC diagnostic confirms V1 responds to its controls, while
the tube response and service-meter transfer remain unqualified. This does
not close A1's independent page-3/4/18 netlist review or demonstrate
calibrated brightness on a sustained grid.

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
interconnect file. Page 18 still needs complete KiCad-export and functional
checks before the A1 netlist gate can close. This transcription cannot settle
T3's internal winding order.

`page18_frame_compare.py` now compares all four board-to-board cables against
freshly exported ideal-rail KiCad components and the neck pin map. The saved
`reference/k7222-11/page18-frame-comparison.json` records all 18 printed pin
pairs: 15 signal nets occur on both corresponding board exports. The V5
collector now represents neck `IS`; `10.7P` remains outside the held-heater
neck model. On the vertical cables, `41P` and `SYNCH` belong to the excluded
supply/converter path. The page-9 centring bridge now represents X1/X2
horizontal-yoke pass-throughs. These are model-scope explanations for the
three remaining gaps, not functional qualification. The separate physical-pin,
panel and yoke comparisons below check connector topology. The A1 page-18
gate stays open because its contrast/service response is unresolved.

The main-board X4 and vertical-board X3 sheets now expose audit-only six-pin
connector symbols. `page18_vertical_cable_compare.py` checks their fresh
KiCad XML exports against the source-first page-18 pin map and cable
1.11.017308.0 pairing. The saved
`reference/k7222-11/page18-vertical-cable-comparison.json` matches all 12
physical connector pins and all six 1-to-1 cable pairs: two 00 returns, 5P,
12P, 22P and SYN. The audit symbols are excluded from circuit assembly, and
`reference.py` rejects a changed pin map before assembling either sheet.
This six-wire receipt verifies only that cable's represented physical pins.

`page18_board_cable_pin_compare.py` now covers all four board-to-board cables.
Audit-only symbols on the main-board X3, X5 and X6 sheets and vertical-board
X1 sheet expose the other source-labelled pins; the page-16 neck X1 audit
symbol supplies the neck ends. Its fresh-export receipt,
`reference/k7222-11/page18-board-cable-pin-comparison.json`, matches all 18
printed cable pairs at both ends (36 labelled connector pins). Neck X1:4 is
unlabelled on page 18 and is separately checked as 0 against the page-16
assembly map. A changed X6 pin assignment fails both this comparison and
`reference.py`'s audit-symbol check. The physical symbols add no assembled
circuit elements. The receipt still exposes six functional board-net gaps;
panel controls and T3 windings remain outside this result. The yoke is checked
separately below.

`page18_yoke_pin_compare.py` checks the six labelled pins on vertical-board X2
against a fresh KiCad XML export and compares all four source yoke terminals
with the corresponding X2 pins: yoke 1→X2:6 (X1), 3→X2:5 (X2), 4→X2:4 (Y2),
and 6→X2:3 (Y1). An audit-only X2 symbol exposes the board pins without adding
circuit elements. The saved
`reference/k7222-11/page18-yoke-pin-comparison.json` also checks that the
assembled deck connects a resistor and inductor in series between each pair of
horizontal (`hy1`/`hy2`) and vertical (`y1`/`y2`) endpoints. Swapping X2:3/X2:4
or moving one deck endpoint fails the comparison. This verifies the represented
terminal map and yoke topology; it does not establish the yoke's historical
R/L values, field strength, or the omitted vertical-board horizontal pass-through.
Panel controls and six cable functional gaps keep the A1 page-18 check open.

`reference/k7222-11/page18-panel-source-read.json` records differently
cropped/resolved reads of schematic pages 3, 4 and 18 from the hashed source PDF.
Page 18 maps R1's E/S/A to 35P/HRS/HRA and R2's S/A to KRS/KRA through
main-board X1. Page 3 draws R1 as a three-terminal potentiometer and R2 as a
two-wire rheostat whose wiper joins its lower end. Handwritten control values
are excluded from this topology read. The KRA trace on page 3 at approximately
3783 px reaches the left, wiper-tied side of board R4 on page 4 at 3726 px;
the −57 px offset is consistent with the neighbouring traces across the page
split. Page 4 also labels V1's emitter path KRS. In the current KiCad export,
R4's left node is `reference9` and V1's emitter is `contrast_low`. An audit-only
X1 symbol now exposes the six main-board connector pins in a fresh KiCad export;
all six match the page-18 labels and the board-side node map.

The old assembled deck put `intens` between two contrast resistors, creating
a third terminal that the source R2 does not have. `steady_supply.py` and the
isolated `signal_path.py` bench now use one rheostat element between
`reference9` (KRA) and `contrast_low` (KRS). The existing `contrast_r` and
`contrast_position` bounds remain declared; the handwritten 5/10 kΩ note is
not promoted to a factory value. `page18_panel_compare.py` checks the panel
terminal labels, the two board-side component edges and the corrected deck
topology. Its saved
`reference/k7222-11/page18-panel-topology-comparison.json` matches R1 and R2
and finds no X1 pin mismatch; changing R2's deck endpoint to `intens` fails the
comparison.

Three assembled ngspice DC operating-point checks at contrast positions 0.05,
0.5 and 0.95 completed. `v(reference9)` was 9.207636, 9.132179 and
9.124684 V; `v(contrast_low)` was 11.96441, 11.98190 and 11.98321 V.
The control reaches V1's bias network, but this small DC shift is not a
connected waveform score or evidence of a calibrated image. The full page-3/4
second netlist remains open.

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
with video high, collector is 0.72 V and base is 0.78 V. The source annotation
says IS low is intensive and IS high is normal. Raising IS while video is high
moves the cathode output from 0.27 V to 4.39 V, the expected direction. C1's
source polarity puts its positive terminal on 41P and negative terminal on OO.
All declared static/function checks pass; a disconnected source net is caught
by the path test.

This isolated bench uses ideal external rails and a fixed 20 µA beam-current
load. It has no CRT emission response and cannot reproduce page 16's
measuring-cable dark/bright millivolt note. That missing source observation
keeps the A1 page-16 function check open despite the complete pin comparison
and plausible transistor operating points.

A later [meter-cable inset read](reference/k7222-11/page16-meter-cable-source-read.json)
adds a second, separate limitation: page 16 draws a series capacitor between
the source-side and meter-side upper terminals, with unvalued shunt elements
at each side. It does not print their values or a lower-terminal connection
inside the inset. The manual's 0.1 mV limit is a *rise above the dark meter
reading* during the just-visible setup; 3.6 mV is the full-bright setting
after R4 adjustment. They are not two DC cathode states. X3:1/X3:2 straddle
the documented 390 Ω neck-board R4, but the existing fixed-20 µA bench gives
7.8 mV directly across those pins in both VIDEO states. The service reading
passes through the unspecified cable and uses a native grid and trim sequence;
neither direct DC X3 value is a service-meter prediction. The A1 observation
check now has a precise missing model boundary: cable/meter transfer and
qualified tube response, followed by the prescribed dynamic setup.

### Vertical output transistor model bounds (2026-11-19)

The printed page-10 vertical output is provisionally modeled as upper NPN
V27 and lower PNP V28. Handwritten notes put `BD140` beside V27 and `BD139`
beside V28; the [ST BD139/BD140 data sheet](https://www.st.com/resource/en/datasheet/bd139.pdf)
identifies BD139 as NPN and BD140 as PNP. Those annotations therefore conflict
with the present printed-stage polarity interpretation and are not promoted to
factory identities. Manual page 14 identifies the V18/V27 and V26/V28
Darlington pairs but supplies no external output transistor type. The full
page-10 A1 netlist remains open; a later partial output-pair pin and polarity
check is recorded below.

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

`horizontal_output_transistor_check.py` now exports the live V18 KiCad symbol
and solves its selected `HOR_OUTPUT_N` model at the BU508AF comparison biases.
The saved `reference/k7222-11/horizontal-output-transistor-dc-check.json`
records hFE 20.89 at 0.1 A/5 V and 20.87 at 4.5 A/5 V, within the data-sheet
10–30 and at-least-5 limits. A current-fed 4.5 A/1.6 A base DC proxy gives
0.044 V collector-emitter saturation, below the data-sheet 1 V maximum. A
low-gain model mutation fails the check. The proxy is a steady-state solve,
so it does not establish the data-sheet's pulsed saturation, 2.5 µs storage
time, 0.2 µs fall time or safe operating area. A2 remains open.

`horizontal_output_switching_proxy.py` adds a separate 16 kHz current-fed
turn-off diagnostic for the same live model. It uses 4.5 A collector current,
about 0.5 A forward base current, a -2.7 V off rail and 4.5 µH series base
inductance. Its ideal collector-current source, 200 V diode clamp and 1 nF
snubber are declared assumptions; this is not the ST Figure 9 inductive-load
circuit. In the saved
`reference/k7222-11/horizontal-output-switching-proxy.json`, the nominal
model starts transferring current to the clamp 1.132 µs after the off command;
the clamp current rises from 10% to 90% in 0.517 µs. Sweeping model TF from
20 to 300 ns changes that transfer interval from 0.146 to 1.067 µs; sweeping
TR from 100 ns to 2 µs shifts the command-to-10% interval from 1.004 to
1.591 µs. These metrics identify model sensitivity; they are not measured
storage or fall times under ST's specified test, so A2 remains open.

### Vertical output part-identity decisions (2026-11-19)

The A1 part entries for V27 and V28 now use the bounded `class-typical`
hFE=60 candidate with 25–250 bounds described above. The contradictory
handwritten labels are not treated as factory types. A subsequent source-side
pin and transistor-arrow check settles the output pair's local connection,
as recorded below; the full page-10 netlist remains open. The current A1 audit
has 25 resolved frame-path entries and only
T3 open as a part entry. A2 remains partial for these devices.

### Partial class-typical register (2026-11-19)

`reference/k7222-11/class-typical-register.json` consolidates 43 currently
cited bounded entries: the V18/V21/V27/V28 and neck V1 semiconductor
candidates, comparable service-scope values, a B31-G family neck outside
diameter, the provisional R41 value, the external brightness-pot range, and
seven parameters each for the ten-member vertical 1AE15, four-member
input/sync 1AE15 and eight-member 1AD50 diode families, plus six explicit
parameters of the 5.1 V reference zener. The input/sync
1AE15 rows identify that their active profile parameters are shared with the
1AD50 model alias, so they are not independent sweep dimensions. Each entry
identifies its stage, source, bounds and model location. The file stays
`partial`: fixed SPICE parameters, tube emission/heater properties, T3
parasitics, yoke sensitivity
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
0.72 V to 0.77 V. The CRT emission and meter-cable observation gap remains open in A1.

### Frame-path A2 device coverage (2026-11-19)

`device_model_coverage.py` joins the 77 semiconductor and magnetic device
instances in the source inventory with the current ideal-rail assembly and
device-model register. The saved
`reference/k7222-11/device-model-coverage.json` accounts for 64 frame-path
instances in 30 printed-type families; 13 instances are converter-only under
the existing A1 scope rule. Fifty-four frame-path instances have provisional
A2 register coverage, eight assembled magnetics have active model names but
no register entry, and two appear in the source inventory but not in the
current assembled model: 012-6931 L1/L2. The page-3 V19 is now present in
the assembly. Assembly presence and a model name do not establish sourced
parameter bounds.

A 600 dpi reread corrected the initial R38/R39 terminal attribution in the
[page-4 V20 branch read](reference/k7222-11/page4-v20-source-read.json).
Horizontal R38's right end and a separate line from the page edge reach
V20's upper terminal. Vertical R39 joins R38's left side at its top and the
left side of parallel R40/C34 at its bottom; their right side feeds V20's
base. Page 8 lists V20 as `1 SA 20 C`; R38/R39 are 680 Ω and R40 is 1.1 kΩ,
while page 6 lists C34 as 470 pF. A separate page-edge view shows V20's
lower terminal continuing to the same local return line as R2's lower end,
correcting the interim open-terminal reading. The four distinct left-edge
lines have page-3 trace matches in independent 300 and 600 dpi renders. The
[page-3 R11/R37 source read](reference/k7222-11/page3-r11-r37-source-read.json)
now follows them to C17's lower feedback trace, the R11.2 `12P` side,
V19's upper-right symbol lead and the lower V6/V19 `00` return. The first
cropped R11/R37 read missed the no-dot crossing where R11.1 passes R37's
upper lead; a second read restored R11.2 on `[p12, sync_feed]`, R11.1 on
`[sync_feed, sync_c]`, R37 on `[p12, sync_c]` and C33 on
`[sync_feed, sync_c]`. A wider 600 dpi crop then exposed the right-hand
page-3 label as V19. Page-4 V1 is a separate contrast-control transistor,
confirmed by the earlier page-18 KRS/X1:5 read. The previous V10-to-`00`
and V1-to-`00` claims were cropped-label errors; actual V10 remains in the
upper oscillator with its distinct emitter network.

The fresh ideal-rail export now has V19 provisionally on
`[v19_out, sync_c, 0]`, with `v19_out` feeding R39 lower and parallel
R40/C34 left. R38/R39 upper are on `p12`, not `0`, and page-4 V1 is
`[p35, v1_base, contrast_low]` with R3 from `p35` to its base node.
R2 still shunts the KRS/`contrast_low` line to `0`. All five printed
`1SA20C` and both `1SC60A` instances are assembled; their C/E
assignment and connected stress remain provisional. An
[isolated DC polarity comparison](reference/k7222-11/page3-4-transistor-polarity-functional-check.json)
now tests the corrected V6/V19/V20 branch and the separate V1 contrast
branch against upper-emitter NPN and PNP alternatives. At BF=26, the
assembled lower-emitter NPN sync chain swings `h_feedback` from 12.0 V to
0.044 V as V6 base drive changes from 0 to 3 V; the reversed NPN and PNP
alternatives swing only 0.261 V and 0.569 V. This remains true across the
generic BF 18–34.7 range. V1's assembled NPN orientation moves KRS from
21.19 to 24.80 V across the R4 trim range, while the PNP interpretation
pins KRS near 35 V. The reversed NPN places V1's base roughly 13–15 V below
its emitter, a reverse-bias condition that the fixture does not qualify
because it omits breakdown. These functional results support the current
V1/V6/V19/V20 orientation, but do not read every printed arrow, qualify the
original 1SC60A/1SA20C devices, or settle V5 and the vertical-board peers.
The local stage, assembly, signal-path and connected-stage tests pass;
the native connected manual score and complete page-3/4 pin comparison remain
open, so A1, A2 and A3 cannot be claimed complete.

The seven printed `1SA20C`/`1SC60A` instances now select separate live
[BC546B-class NPN proxies](circuits/k7222-11-small-transistor-models.cir).
The [onsemi BC546B data sheet](https://www.onsemi.com/download/data-sheet/pdf/bc546-d.pdf)
gives 200–450 gain at 2 mA/5 V, at most 0.25 V saturation at 10 mA/0.5 mA
base drive, and at least 150 MHz transition frequency at 10 mA/5 V.
The [isolated model check](reference/k7222-11/small-transistor-class-check.json)
reports hFE 274, 0.094 V saturation and a 187 MHz transition-frequency
proxy for each alias. The A2 register bounds all nine explicit SPICE
parameters for both printed families, and A6 records 18 corresponding
class-typical values. This comparator does not identify either historical
part; connected current/voltage/thermal stress, joint bounds, switching
storage, implicit BJT defaults and the outstanding source-arrow reads remain
open. The affected input, vertical-sync, oscillator, integrator, output and
assembly tests pass at the new nominal models. The earlier BF=26 polarity
fixture is a functional orientation comparison under its recorded prior
generic model, not a class-model qualification.

The report also makes shared-family decisions visible. Fourteen frame-path
`1AE15` diode instances currently use two different model names.
Ten vertical 1AE15 instances have one provisional family entry. The other four
input/sync instances now have a separate entry for the shared `1AD50_BOUND`
model alias. The [Nexperia 1N4148/1N4448 data sheet](https://assets.nexperia.com/documents/data-sheet/1N4148_1N4448.pdf)
provides the same comparison limits for both entries: 1 V at 10 mA, 25 nA at
20 V, 4 pF at zero bias and 4 ns under its specified recovery test. The saved
`neck-diode-model-check.json` verifies this active model against those four
limits; it does not establish the installed 1AE15 ratings or the four devices'
in-circuit stress. The next A2 pass must check the remaining assignments
against source function and data-book bounds, then add coverage for each
frame-path device and validate the live model response. The page-4 T3 scan
still does not independently establish the proposed X1:3-to-X2:3 winding
return; its A1
and A5 status is unchanged.

The printed input-board A1 is T200. A separate Robotron PC1715 service-manual
comparison table maps T200/D2000 to the SN74H00 quad two-input NAND family.
The [Texas Instruments 1985 TTL Data Book](https://ftpmirror.your.org/pub/misc/bitsavers/components/ti/_dataBooks/1985_TI_The_TTL_Data_Book_Vol_2.pdf)
(printed pages 3-3 and 3-6) provides class limits for input and output levels,
input and supply currents, and loaded propagation delay. The previous live
behavioral NAND had zero supply current even while sourcing an output load.
The revised [live model](circuits/signal-path-models.cir) draws explicit
per-gate quiescent current and sources output current from the 5 V rail. The
[isolated check](reference/k7222-11/t200-class-check.json) passes all ten
nominal class and rail-accounting checks, including 3.91 V at a 0.5 mA high-output
load, 0.350 V at a 20 mA low-output load, and 3.91/4.93 ns rising/falling
propagation at 280 Ω/25 pF. Its 13 live gate parameters now have provisional
bounds in the A2 and A6 registers. This is a functional class model, not a
factory T200 curve; joint bounds and connected input/output loading remain
unqualified, so A2 and A6 remain open.

### Vertical 1AE15 class and period IC comparison (2026-11-19)

The 14 frame-path `1AE15` instances serve input protection, trigger, ramp,
bias and threshold roles. No original electrical data sheet for that printed
code was found in this pass. Ten instances use the same `VERTICAL_DIODE` model
in the vertical stages, so the device-model register now groups those ten
explicit IDs under a provisional fast silicon signal-diode class. The
[Nexperia 1N4148/1N4448 data sheet](https://assets.nexperia.com/documents/data-sheet/1N4148_1N4448.pdf)
is the comparator, not an identification of the installed 1AE15. It specifies
at most 1 V at 10 mA forward current, 25 nA reverse current at 20 V, 4 pF at
zero bias/1 MHz, and 4 ns recovery under its stated switching test. The
register and A6 class-typical register give bounds for all seven explicit
`VERTICAL_DIODE` SPICE parameters, including breakdown and knee values that
were previously left at simulator defaults.

`vertical_diode_check.py` measures the live model at the comparator DC and
capacitance biases and in a 100-ohm reverse-recovery test. The saved
`reference/k7222-11/vertical-diode-model-check.json` records 0.702 V at 10 mA,
1.69 nA at 20 V reverse bias, 2.00 pF at zero bias/1 MHz, and about 1.2 ns
from the current zero crossing to its return to 1 mA reverse current. The test
uses approximately 10 mA forward current and 60 mA peak reverse current,
matching the comparator's stated conditions within 5%; it meets that data
sheet's 4 ns limit. These are model-response checks, not measurements of the
original 1AE15 part. Original 1AE15 ratings and native connected-frame
sensitivity remain open. Four other 1AE15 instances use `1AD50_BOUND` and now
have a separate provisional A2 family entry; their part-specific stress remains
unchecked. The first diode-only checkpoint had 15 provisionally covered
frame-path instances, 45 assembled but unregistered, and four absent from the
ideal-rail assembly.

`vertical_diode_sensitivity.py` also varies each of the seven registered
parameters to its minimum and maximum in the connected vertical output stage.
The saved `reference/k7222-11/vertical-diode-stage-sensitivity.json` contains
all 14 runs, model/profile/register hashes and final-field metrics for the
20.8 ms bench stimulus. The largest one-at-a-time yoke-current span change is
0.02456 A, or 5.26% of its 0.46707 A baseline, with `IS` at its minimum. The
largest mean-yoke-current change is 0.00797 A, or 13.33% of its 0.05977 A
baseline. Ramp and trigger-pulse spans move by at most 0.092% and 0.0012%,
respectively. The 20.8 ms bench is not the native 19.5 ms mode, and this sweep
does not cover simultaneous extremes or establish the original 1AE15 ratings.
The baseline yoke-current span changed from 0.43353 A when the MAA723 proxy
had its former drive limit, so these new sensitivity numbers replace the old
receipt rather than extending a single fixed model.

A separately scanned [Robotron PC 1715 service manual](https://magentacloud.de/s/iNaPeeaM2m5TbHS)
has a comparison table on PDF page 119 (printed page 117) that pairs `MAA723H`
with `uA723` and `B260D` with `TDA1060`.
`reference/k7222-11/pc1715-ic-crossref.json` records the source and page
hashes. This independently supports the 723 functional family used for
K7222.11 `MAA723`, while its missing H suffix and electrical parameters remain
unverified. `B260D` is converter-only in the Phase A ideal-rail scope.

The active `MAA723_BOUND` functional subcircuit is now provisionally registered
for 012-6931:A2. The separate Robotron table establishes only a 723-family
comparison; it does not identify the K7222.11 part's missing H suffix. The
[TI µA723 data sheet](https://www.ti.com/lit/ds/symlink/ua723.pdf) gives a
6.8–7.5 V reference, 2.3 mA typical/4 mA maximum standby current at 30 V and
150 mA output capability for the comparable µA723C. The
[TI LM723 data sheet](https://www.ti.com/lit/ds/symlink/lm723.pdf) supplies the
10-pin can contract and a 0.2% maximum 1–50 mA load-regulation comparison at
5 V. The old functional proxy's 1 mS error transconductance and 200 µA
drive ceiling delivered only 2.31 V into a 100 Ω load in an isolated 5 V
regulator fixture. That conflicts with the 723 output-current class.

The revised proxy exposes bounded reference, standby, error-transconductance
and drive-limit parameters. Its saved
[isolated class check](reference/k7222-11/maa723-model-check.json) reports
7.150 V reference and 2.300 mA standby at 30 V. At 12 V input, the same
fixture gives 4.990 V at approximately 1 mA, 4.988 V at 50 mA and 4.985 V
at 150 mA; the 1–50 mA droop is 1.755 mV. These are behavioral comparisons,
not a fit to MAA723 internal silicon. A regression test demonstrates that the
former 1 mS/200 µA settings fail the 50 mA check. The existing connected
vertical-integrator and vertical-output tests still pass with the revised
model. Four matching A6 bounds bring the partial class-typical register to
144 entries. Its pole, internal BJT/diode curves, current-limit response, dynamic
behavior, joint bounds, and connected-stage electrical stress remain
unqualified, so A2 is still open. The preceding TP7/TP8 diagnostic used the
older model; the updated A3 diagnostic is recorded below.

### Independent page-9 regulator branch read (2026-11-19)

The source-side `reference/k7222-11/page9-reference-source-netlist.json` records
the seven-part 5.1 V branch from `older.pdf` page 9: R10, R9, V3, R11, V4,
C7 and C5. It was written from the 300 dpi full page and a 600 dpi branch
crop before the KiCad sheet was opened for comparison. The initial capacitor
labels were wrong: the source-ID check prompted enlarged crops, which resolve
the base capacitor as C7 and the output capacitor as C5; the feed also reads
12P, not 41P. The saved source file records the crop hashes and correction.

`page9_reference_compare.py` exports a fresh regulator KiCad netlist and checks
each source terminal, including V3 direction, V4 collector/base/emitter and
both electrolytic polarities. The saved
`reference/k7222-11/page9-reference-comparison.json` reports 16 of 16 pins
matched with no extra pins in this seven-component sheet. At nominal input,
the regulator stage bench retains a 4.8–5.3 V output at its sampled load
steps and after time-step refinement. This comparison covers only the page-9
reference branch; the rest of pages 9–10 and the whole-page A1 gate remain open.

### 5.1 V reference-zener model comparison (2026-11-19)

The source-first page-9 read places V3's cathode at `ZENER_REF` and anode at
0 V. The active `REG5_ZENER` model is now compared with the
[Nexperia BZX84-C5V1 data sheet](https://assets.nexperia.com/documents/data-sheet/BZX84_SER.pdf)
as a 5.1 V class device, not as an identification of the printed `ZC5.1`.
At 25 °C that comparator specifies 4.8–5.4 V and at most 60 Ω differential
resistance at 5 mA. `regulator5_zener_check.py` solves the live model at
4.9, 5 and 5.1 mA reverse current; the saved
`reference/k7222-11/regulator5-zener-model-check.json` records 5.125 V at
5 mA and 12.72 Ω across the 4.9–5.1 mA interval. Changing the model breakdown
voltage to 6.2 V fails the comparison. The A2 and A6 registers now bound its
six explicit SPICE parameters. The original part rating, connected-stage
current/voltage stress, joint-bound response and omitted TT parameter remain
open, so this is provisional A2 coverage.

### 1AD50 clamp-diode model comparison (2026-11-19)

Eight frame-path instances printed `1AD50` use the shared `1AD50_BOUND`
model: six neck-board V2 diodes and horizontal-input V2/V3. The source
inventory supplies a type name, but no original 1AD50 electrical rating is
established here. Their signal and clamp roles motivate a provisional
comparison with the [Nexperia 1N4148 data sheet](https://assets.nexperia.com/documents/data-sheet/1N4148_1N4448.pdf);
the comparator is not an identification of the installed diodes. The model
now sets `BV` and `IBV` explicitly in addition to the five existing bounded
profile parameters. The A2 device register records all eight IDs and seven
parameter bounds, and the A6 register records the same seven class-typical
proxies. Broad capacitance and transit-time bounds retain uncertainty about
the original 1AD50 rather than implying 1N4148 ratings for it.

`neck_diode_check.py` measures the live nominal neck model against the
comparator's 25 °C conditions. The saved
`reference/k7222-11/neck-diode-model-check.json` records 0.639 V at 10 mA,
0.834 nA reverse current at 20 V, 3.00 pF zero-bias capacitance at 1 MHz,
and 1.24 ns recovery to 1 mA reverse current. Its switching stimulus reaches
9.999 mA forward and 60.17 mA peak reverse current through 100 Ω. All four
nominal checks pass the comparator limits; original part ratings, per-device
stress and connected native-mode bound sensitivity are still open.
Current regenerated A2 coverage is 28 of 64 provisionally registered frame-path
instances, 32 assembled but unregistered, and four absent from the assembly.

### Independent page-9 vertical sync input read (2026-11-19)

The source-side `reference/k7222-11/page9-sync-input-source-netlist.json` was
written from `older.pdf` page 9 at 300 dpi and a separate 600 dpi crop before
opening the KiCad sync-filter sheet. It covers R3, C2, C1 and R20. The first
read incorrectly joined the incoming SYNC line to the vertical 0 V return
bus, which made C2 and R20 appear to connect to SYNC. The exported netlist
exposed the discrepancy. A tighter 600 dpi crossing view shows no junction
dot where those lines cross, while C2 and R20 visibly join the bus that
continues to 0 V. The saved source file records the view hashes and the
corrected graph: R3 is SYNC-to-TP2, C2 is TP2-to-0, C1 is TP2-to-the second
integration node, and R20 is that node-to-0.

`page9_sync_input_compare.py` exports a fresh KiCad netlist and compares the
two endpoint nets of each unpolarized passive. The scan does not number
their leads, so the check does not invent a physical pin orientation. The
saved `reference/k7222-11/page9-sync-input-comparison.json` matches all eight
endpoints; the regression test fails if C2 is moved back to the mistaken
SYNC net. This is a separate partial A1 comparison from the 5.1 V branch.
The oscillator remainder and the page-9 whole-sheet mark stay open.

### Remaining active zener class checks (2026-11-19)

The [Nexperia BZX84 series data sheet](https://assets.nexperia.com/documents/data-sheet/BZX84_SER.pdf)
gives 25 °C, 5 mA working-voltage ranges and maximum differential resistances
for C6V2, C9V1 and C16. These are class comparators, not identifications of
the three printed parts. In particular, the inventory OCR for horizontal V11
reads `Z 86.2`; treating the active model as a 6.2 V zener remains provisional.
The live `HOR_Z6`, `Z9_BOUND` and `VERT_Z16` models now explicitly set CJO and
TT as well as IS, N, RS, BV and IBV. The source bounds capacitance but gives no
SPICE transit-time or recovery limit, so TT is a declared proxy awaiting a
connected-stage sensitivity check.

| Inventory part | Comparator | Data-sheet VZ range / max rdif | Live model at 5 mA / near-5 mA rdif |
| --- | --- | --- | --- |
| 012-6921:V4 | C9V1 | 8.5–9.6 V / 15 Ω | 9.187 V / 12.70 Ω |
| 012-6921:V11 | C6V2 | 5.8–6.6 V / 10 Ω | 6.272 V / 8.83 Ω |
| 012-6931:V15 | C16 | 15.3–17.1 V / 40 Ω | 16.072 V / 9.70 Ω |

`frame_zener_check.py` measures each live model at 4.9, 5 and 5.1 mA; its
saved report is `reference/k7222-11/frame-zener-class-check.json`. A deliberately
wrong 12 V breakdown value fails the C9V1 voltage check. The A2 register adds
three provisional device rows and the A6 register adds 21 bounded parameter
entries. Regenerated A2 coverage is 31 of 64 frame-path instances: 29 assembled
instances remain unregistered and four remain absent from the ideal-rail
assembly. Source-first direction checks, per-device stress and connected-stage
bound sensitivity remain open, so none of these rows closes A2.

The service register already has `agent-read` shape descriptors for all 17
manual test points. A3 remains open because the descriptors have not yet been
scored on connected stages with all required loaded probes and recorded trims.

### Horizontal diode class checks (2026-11-19)

The active `HOR_D` model serves the two printed 1AL25 horizontal timing diodes.
The [Nexperia 1N4148 data sheet](https://assets.nexperia.com/documents/data-sheet/1N4148_1N4448.pdf)
is a provisional high-speed signal-diode comparator, not a 1AL25 identity.
The active `HOR_RECT` model serves four printed 1YL1/2, 1YL1/4 and 1YL1/8
flyback rectifiers. The [Vishay UF4007 data sheet](https://www.vishay.com/docs/88755/uf4001.pdf)
is a provisional 1000 V ultrafast class comparator; the printed suffixes may
represent different original ratings, which this shared model does not yet
resolve. Both models now set BV and IBV explicitly. `HOR_RECT` also has revised
CJO and TT to place its nominal 4 V capacitance and reverse recovery within
the comparator's test range.

`horizontal_diode_check.py` solves both live models at 25 °C. For `HOR_D`, it
reports 0.649 V at 10 mA, 0.834 nA leakage at 20 V, 2.00 pF at zero bias and
1 MHz, and 1.23 ns recovery at 10.48 mA forward, 60.09 mA peak reverse through
100 Ω. For `HOR_RECT`, it reports 0.918 V at 1 A, 9.14 nA at 1000 V, 17.88 pF
at 4 V and 1 MHz, and 8.16 ns recovery at 0.504 A forward, 1.041 A peak
reverse to the 0.25 A return threshold. These nominal values pass the stated
class comparisons. The recovery stimulus matches the comparator currents but
is an approximate fixture, not a reproduction of the manufacturer's switching
test. Changing the rectifier CJO to 200 pF fails its capacitance
check. The saved report is
`reference/k7222-11/horizontal-diode-class-check.json`.

The A2 register adds four printed-type families covering six instances; A6
adds 28 bounded rows, with shared-model references for the three 1YL1 suffixes.
Regenerated provisional A2 coverage is 37 of 64 frame-path instances, leaving
23 assembled but unregistered and four absent from the ideal-rail assembly.
Original ratings, individual diode directions, 1YL1 suffix differences,
in-circuit voltage/current stress and joint-bound connected sensitivity remain
open. The nominal comparator checks do not close A2 or A6.

### Conditional vertical design point (2026-11-19)

`vertical_design_point.py` solves the current needed to land the reduced-model
beam at half the manual's 145 mm picture height. It uses the documented 2 kByte
18 ms trace and 1.5 ms retrace, the documented 11–12 kV EHT range, and the
existing assumed 40 mm cosine-sheet yoke and CRT trajectory. The yoke model
derives 644 effective vertical turns, 19.987 mH, 10 Ω and 12.196 mT/A; the
40 mm field, 10 mm internal neck aperture, winding target and gun geometry are
not physical measurements of the installed tube or yoke. The saved
`reference/k7222-11/vertical-design-point.json` records the source/profile
hashes, all input conditions and the following conditional results:

| Condition | Required peak vertical yoke current |
| --- | ---: |
| 145 mm height, 11.5 kV | 0.28055 A |
| 130–160 mm documented height tolerance at 11.5 kV | 0.25353–0.30691 A |
| 145 mm height across 11–12 kV | 0.27433–0.28665 A |

For a linear -I-to-+I trace followed by a 1.5 ms retrace, `V=RI+L dI/dt`
requires 31.17 A/s during trace and -374.07 A/s during retrace. The ideal
terminal differential ranges from -10.28 to +3.43 V, a 13.71 Vpp swing.
Manual test points 7 and 8 are separate yoke-terminal waveforms. TP7 has a
2.5 Vpp guideline, but page 20's 17 V TP8 arrow runs from the positive crest
to zero rather than across the full trace. Its separate 10 V shoulder-to-trough
arrow has unresolved node attribution. The earlier nominal 14.5–19.5 Vpp and
toleranced 9.625–24.375 Vpp possible differential-swing intervals were derived
from the mistaken 17 Vpp interpretation and have been withdrawn. The 13.71 Vpp
ideal calculation remains a conditional model result, not a connected-stage
pass or a document contradiction.
The nominal current is stable within 2 nA across 0.2, 0.1 and 0.05 mm
trajectory steps.

`design-point.json` now links and summarizes the calculation. Its geometry
remains provisional, while test points 1–6 constrain upstream vertical-stage
waveforms rather than yoke current directly. A source-bounded inner neck
aperture/yoke extent and connected TP7/TP8 differential waveform are still
needed before the vertical operating point can be frozen. The T3 tap and
return-path questions remain separate A1/A5 work.

### A2: V13 horizontal-driver transistor class check

The original 012-6921 parts-list scan on PDF page 8 prints V13 as `SF1280`.
The historical [DDR semiconductor data book](https://www.tiffe.de/Robotron/Bausteinuebersicht/DDR-Halbleiter.pdf)
has a common SF126–129 section: at 2 V/50 mA its h21E groups A–F span 18–1120;
at 150 mA collector and 15 mA base drive it specifies VCEsat at most 0.5 V;
at 10 V/10 mA and 15 MHz it specifies fT at least 60 MHz. The available
section does not identify the `0` suffix, so the whole family range is only
a class comparator for this printed part.

The previously active `HOR_DRIVER_N` charge/capacitance terms gave about
7.7 MHz at the unity-current-gain crossing in an isolated AC diagnostic,
below the family's 60 MHz minimum. With `CJE=20p`, `CJC=8p` and `TF=1n`,
the live model checked at the data-book biases gives hFE 61.0, a 0.069 V
current-fed DC saturation proxy, and a 145.1 MHz 15 MHz gain-bandwidth
proxy. The [saved model check](reference/k7222-11/horizontal-driver-transistor-class-check.json)
records the KiCad-exported Q1036 identity, live model and register hashes,
each bias and result. Its test also confirms the old slow model falls below
the family fT floor.

This adds one provisional A2 register instance and seven A6 bounded parameter
rows: 38/64 frame-path instances now have register coverage, 22 assembled
instances remain uncovered, and four remain absent from the ideal-rail
assembly. The class check does not identify the SF1280 gain group or validate
inductive storage and fall, joint parameter bounds, connected-stage stress or
the remaining implicit BJT simulator defaults. A2 and A6 remain open.

### A2: V10/V12 horizontal small-transistor classes

The 012-6921 parts list prints V10 as SC237E and V12 as SF1260. The
[historical DDR semiconductor data book](https://www.tiffe.de/Robotron/Bausteinuebersicht/DDR-Halbleiter.pdf)
gives SC237 group E h21e 224–560 at 6 V/2 mA, typical fT 170 MHz at
6 V/10 mA/20 MHz, and typical pulsed VCEsat 210 mV at 100 mA collector with
5 mA base drive. It lists 7.7 pF and 3.8 pF junction-capacitance readings
at their stated biases; those are not direct zero-bias SPICE CJE/CJC values.
The same book gives the SF126–129 family gain groups, a 0.5 V maximum
saturation voltage at 150 mA/15 mA, and a 60 MHz minimum fT at
10 V/10 mA/15 MHz. It does not resolve the printed `SF1260` suffix.

The prior shared `HOR_N` BF=100 could not represent the SC237E group-E
gain. The authored Q1034 now selects `SC237E_N` with BF=300 and charge terms
chosen for the historical typical AC point; explicit RC=1 Ω and RE=0.25 Ω
bring its current-fed saturation proxy near the documented typical value.
The [live V10/V12 check](reference/k7222-11/horizontal-small-transistor-class-check.json)
records V10 hFE 320.0, 0.208 V saturation and 169.3 MHz fT proxy, and V12
hFE 101.6, 0.067 V saturation and 76.0 MHz fT proxy. The test rejects the
old BF=100 for V10 group E and a 20 ns forward transit time for V12's
family fT floor. Both authored horizontal-oscillator export and ideal-rail
assembly tests still pass after the model split.

This adds two provisional A2 instances and sixteen bounded A6 rows, bringing
coverage to 40/64; twenty assembled instances remain unregistered and four
are absent from the assembly. V12's `HOR_N` check does not qualify the
separate `REG5_NPN` model used by the other SF1260 instance on page 9.
The V10 typical-value comparison is not a manufacturer limit, and neither
model is yet validated for part-specific switching, connected stress, joint
bounds or every implicit simulator default. A2 and A6 remain open.

### A2: page-9 V4 SF1260 regulator transistor

The V4 in the source-checked 5.1 V reference branch uses a separate active
`REG5_NPN` model. Its old 20 ns TF and 40/15 pF junction terms gave a
sub-60 MHz transition-frequency proxy, inconsistent with the
[historical SF126–129 family sheet](https://www.tiffe.de/Robotron/Bausteinuebersicht/DDR-Halbleiter.pdf)
at 10 V/10 mA/15 MHz. The live alias now uses 1 ns TF and 20/8 pF depletion
terms. At the manufacturer's stated test biases, the
[saved V4 check](reference/k7222-11/regulator5-transistor-class-check.json)
records hFE 61.2 at 2 V/50 mA, 0.069 V current-fed saturation at
150 mA/15 mA, and a 144.3 MHz 15 MHz gain-bandwidth proxy. The previous
charge terms fail the family frequency floor in the regression check.

The gain profile now spans the full base-family A–F range, 18–1120, because
the printed `SF1260` suffix is not resolved by that table. This is a broad
provisional class bound, not an identified gain bin. The model and profile
changes preserve the loaded reference-stage tests and the independent
page-9 pin comparison; the adjacent zener report was refreshed for the model
file hash. This adds one A2 instance and seven A6 rows: 41/64 instances have
provisional coverage, nineteen assembled instances remain unregistered,
and four are absent from the current assembly. V4 still needs connected
current/voltage stress, joint-bound sensitivity and examination of implicit
BJT defaults. A2 and A6 remain open.

### A2: two KFY18 vertical PNP instances

The 012-6931 inventory prints KFY18 at V13 and V26, and the live vertical
KiCad sheets select the same `VERTICAL_PNP_BOUND` alias for both. The original
[1987 Tesla Katalog 2](https://teslakatalog.cz/download/tesla_katalog_2_1987_bw.pdf)
(SHA-256 `fa340fb7a38b8a21091882d4fb3968297e669005c5601f1606fe17960accdc4b`,
printed pages 221–223) identifies KFY18 as a silicon PNP. Its stated tests
include h21e 50–250 at 1 mA/5 V and h21E 90–300 at 10 mA/10 V; saturation
typically 0.6 V and at most 1 V at 150 mA/15 mA; fT typically 100 MHz and at
least 60 MHz at 50 mA/10 V with a 30 MHz test frequency; collector-base
capacitance typically 19 pF and at most 30 pF at 10 V reverse bias; and
emitter-base capacitance typically 55 pF and at most 80 pF at 0.5 V reverse
bias. Its 45 V collector-emitter, 600 mA collector-current and 0.8 W
uncooled power ratings have not yet been checked against connected operation.

The former live 5 ns forward transit time yielded only about 31 MHz in an
isolated 50 mA gain-bandwidth proxy. The revised shared model uses 1.5 ns,
65/45 pF zero-bias junction terms and explicit 3/0.25 Ω collector/emitter
resistances. The [saved catalog comparison](reference/k7222-11/kfy18-model-check.json)
checks both live KiCad selections and records hFE 107.2 at 1 mA, 115.4 at
10 mA, 0.558 V saturation, a 97.7 MHz frequency proxy, and 54.9/18.7 pF
reverse-bias emitter/collector capacitances. All seven nominal checks pass;
the vertical-stage regression tests also pass. These are model responses at
specified biases, not measured KFY18 curves.

The family adds two provisional A2 instances and nine A6 bounded parameter
rows: coverage is now 43/64, with 17 assembled instances unregistered and
four absent from the ideal-rail assembly; the A6 register has 131 partial
entries. Connected V13/V26 stress, joint parameter bounds, original switching
time and implicit SPICE defaults remain open, so A2 and A6 are not complete.

### A2: vertical V18 SF127C group-C transistor

The 012-6931 page-10 parts list prints V18 as `SF127C`. Its authored vertical
output sheet formerly assigned `VERTICAL_NPN_BOUND`, the same generic alias
used by two unresolved `1SA20C` oscillator transistors. V18 now selects a
separate `SF127C_N` NPN alias so its documented type can be checked without
asserting that the oscillator parts share its electrical class.

The historical [DDR SF126–129 sheet](https://www.tiffe.de/Robotron/Bausteinuebersicht/DDR-Halbleiter.pdf)
(SHA-256 `247cd6d8e45ef1ebb953ab0eeb77a7cc0f90f5e1d5ea4d45c72f8b8599926e43`)
specifies group-C h21E 56–140 at 50 mA/2 V, VCEsat at most 0.5 V at
150 mA/15 mA, and fT at least 60 MHz at 10 mA/10 V with a 15 MHz test
frequency. The [saved V18 check](reference/k7222-11/sf127c-vertical-model-check.json)
reads the KiCad-exported Q723 model and reports hFE 91.8, a 0.258 V isolated
DC saturation proxy and a 75.8 MHz 15 MHz gain-bandwidth proxy. All nine
explicit model parameters have bounds in the A2 and A6 registers. These
measurements establish nominal class response, not a fitted factory curve.

At this V18 checkpoint, the row raised provisional A2 coverage to 44/64; 16
assembled instances remained unregistered and four were absent from the
ideal-rail assembly. The A6
register now has 140 partial entries. The remaining page-10 netlist review,
connected V18 voltage/current/thermal stress against the historical
30 V/500 mA/600 mW ratings, joint parameter bounds and implicit simulator
defaults remain open. A2 and A6 are not complete.

### A1: page-10 vertical driver, bias and output source check

The [source-side page-10 read](reference/k7222-11/page10-output-pair-source-netlist.json)
records the V18/V27 upper and V26/V28 lower rail and driver connections from
300 dpi full-page and separate 600 dpi views of `older.pdf`. The printed arrows
show upper V27 as NPN and lower V28 as PNP; both emitters join the Y1 output.
V19/V20/V21 point down the series bias chain between the driver bases, while
R48 feeds its V20/V21 junction from A3. The handwritten `BD140`/`BD139`
labels conflict with the printed transistor polarities and remain unverified
replacement notes, not factory part identities.

The [fresh KiCad-export comparison](reference/k7222-11/page10-output-pair-comparison.json)
matches all 20 transcribed transistor, diode and R48 terminals, including all
six output-pair terminals and three diode directions. The authored model
aliases have the same NPN/PNP assignment. A regression check reverses V20 and
confirms that the comparison fails. This closes these local pin and polarity
comparisons only. At this checkpoint, driver collector-feed and emitter
resistors, A3's other pins, feedback, the remaining page-10 connections and
the connected-stage function check remained in A1. The A2 parameter and stress
checks remain open.

The subsequent [A3 source-side read](reference/k7222-11/page10-a3-source-netlist.json)
records all eight active physical amplifier pins, C26/R54's series input
compensation path, C27's output compensation path and R48's amplifier end.
Its 300 and 600 dpi crops agree on the physical pin functions; the KiCad
functional symbol renumbers physical 3, 4, 5, 6, 9, 10, 11, 12 as model pins
1 through 8. A [fresh export comparison](reference/k7222-11/page10-a3-comparison.json)
matches all 15 scoped terminals, and a reversed R54 compensation connection
fails the comparison. This closes the local A3 pin and compensation connection
check. It does not establish P09A's electrical identity. The former
`LM709_FAMILY` substitute fails an
[isolated DC follower check](reference/k7222-11/lm709-dc-follower-check.json): it
produces 12.54258 V at the output for a +1 V input under ±15 V rails and a
2 kΩ load, while −1 V and 0 V inputs track. It was removed from the live
assembly in favour of a labelled equivalent described below. The remaining
page-10 feedback and supply paths, connected-stage function, and A2 model
qualification still need work.

### A3: loaded vertical-stage waveform diagnostic

The connected vertical stage was solved with a 19.5 ms synthetic field-sync
period through 0.2535 s, retaining the profile's nominal 50 kΩ vertical trim,
11 kΩ height trim, 0.5 symmetry fraction, 23.5 kΩ R59/R60 settings and
20 mH/10 Ω hypothetical vertical yoke. This run predates the revised MAA723
proxy above and does not describe its current-stage response. The
[saved diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic.json)
records every parameter, the deck and trace hashes, both probe-solve hashes,
and the final-field score. `service_probe.py` now accepts the stage deck's
ngspice `wrdata samples.txt` output when no raw trace is emitted; a regression
test checks that the scorer consumes this independently loaded result.

The two late fields at 0.2145–0.234 s and 0.234–0.2535 s were compared at
9,750 matching 2 µs samples. The vertical ramp differs by at most 0.39% of
its swing and yoke current by 0.42%, but Y1 still differs by 2.29 V, or 12.5%
of its swing, briefly near reset. Periodic steady state is not established.
For the final field, the separate EO 203-equivalent loaded solves give TP7
1.740 Vpp against the manual's 2.5 V ±25% guideline (numeric fail) and TP8
18.307 Vpp against the then-registered 17 Vpp target (archived numeric pass;
that full-swing target was later corrected). Both registered shape checks pass.
The probe loading changes these low-impedance nodes by less than 0.00001 Vpp.

The scorer labels this result `diagnostic-only; grid stimulus not established`.
The stage bench uses synthetic sync and has no native grid input, so it cannot
close A3. TP7's amplitude, the residual Y1 reset difference, the remaining
test points and a connected grid-stimulus score remain to be resolved; the
nominal trims were recorded, not fitted to the manual values.

After the MAA723 proxy revision, the same 19.5 ms synthetic field period and
nominal trims were solved again through 0.2535 s. The new
[loaded diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic-maa723.json)
records the then-current model parameters and hashes of its stage deck, raw trace,
independent TP7/TP8 probe solves and score. In the final field, TP7 is
1.8718 Vpp after probe loading. It misses the 1.875 Vpp lower bound of the
2.5 V ±25% guideline by 0.0032 V; the archived scorer passes TP8 at 18.7763
Vpp against the former, misread 17 Vpp target. Both shape checks pass. Across
9,750 paired samples from the
two final fields, the vertical ramp differs by at most 0.38% of its swing and
yoke current by 0.39%, but Y1 differs by 2.61 V (13.9% of its swing) near
reset. The stage is still not proved periodic, and the stimulus remains a
synthetic field pulse rather than native grid input. No A3 completion claim
follows from this narrower result.

### A2/A3: labelled P09A equivalent and connected-stage result

After checking the LM709 transistor-topology proxy and sweeping its broad
generic NPN/PNP gain and Early-voltage choices without finding a valid DC
follower, A3 now uses the explicitly labelled `P09A_EQUIV` functional stage.
The [isolated class check](reference/k7222-11/p09a-equivalent-class-check.json)
passes eight nominal LM709C-class checks: ±10 V follower tracking into 2 kΩ,
an 11.79 V open-loop output swing in either direction, about 40,890 V/V
small-signal gain, 2.60 mA quiescent current, 300 nA input bias, a 0.250 V/µs
post-step slew proxy, slower response with fourfold external input
compensation, and rail-current accounting. This is not a P09A identity or
large-signal manufacturer test. Twelve equivalent parameters have explicit
provisional bounds in the A2/A6 registers; their joint bounds and the
page-10 loaded output current remain unchecked.

The archived [native-period diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic-p09a-equivalent.json)
uses the same nominal trims, 19.5 ms synthetic field pulse and separate
EO 203-equivalent probe solves. Loaded TP7 now passes at 2.1594 Vpp against
its 2.5 V ±25% guideline. The archived scorer marked TP8's 25.7674 Vpp as
failing a 17 Vpp target, now corrected because 17 V is crest-to-zero; both
shape checks pass. The late-field Y1 maximum difference is
0.5972 V, or 2.32% of its 25.768 V swing, concentrated near reset. This is
still not periodic steady state, and the bench does not use the native grid
input. This run predates the new BC546B-class transistor proxies, so its TP8
failure is historical evidence, not a current connected-stage score. The
current small-transistor-model rerun gives 25.7855 Vpp full swing at TP8 but
does not establish a manual full-swing target. The
[corrected loaded score](reference/k7222-11/vertical-a3-tp8-source-corrected-diagnostic.json)
checks the 17 V positive crest: 14.5803 V is within ±25%, while the separate
10 V annotation remains unresolved. A source-first
review of the remaining page-10 feedback/output path is still needed before
parameters are changed to match TP8.

### A1: page-10 feedback branch and cross-page R44 identity

The 300 dpi page-10 view, enlarged 600 dpi feedback crop and page-14 parts
list support a [scoped source read](reference/k7222-11/page10-feedback-source-netlist.json)
of A3's inverting input, R43, R45/R46/R47 and the Y2 return. A
[fresh KiCad export comparison](reference/k7222-11/page10-feedback-comparison.json)
matches all ten selected terminals and the printed 5.6 kΩ, 5.6 kΩ and
1.5 kΩ values. A mutation moving R46's Y2 end to the inverting input fails
the comparison. This is a partial cross-check, not the independent full
page-9/10 netlist required by A1.

The nearby printed label is R46. Page 9 already places R44 in the A2
ramp-output divider, where the live integrator assembles it as R613 with
R40 to ground. A temporary second R44 on page 10 caused the source-coverage
validator to reject the duplicate identity and was removed before changing
the live assembly. The checked feedback branch therefore does not explain
the TP8 failure. The rest of page 10 and A3's connected function remain open.

### A1/A5: page-10 Y2 sense return and TP7 current constraint

The enlarged page-10 schematic shows R29 between Y1 and Y2 and R27 from Y2
to 0 V. X2:3 and X2:4 carry Y1 and Y2 respectively. The source label for the
small shunt resistor is supported by the page-14 parts list, which gives R29
as 430 Ω ±5% and R27 as 3.9 Ω ±2%. The extended
[page-10 source read](reference/k7222-11/page10-output-pair-source-netlist.json)
and [fresh KiCad comparison](reference/k7222-11/page10-output-pair-comparison.json)
now match 26/26 local terminals. A regression check moving R27's ground end
onto Y2 fails the comparison. The other page-10 feedback connections remain
outside this partial A1 read.

The regenerated [vertical design point](reference/k7222-11/vertical-design-point.json)
uses Ohm's law only for R27's *total* sense current. TP7's 2.5 Vpp guideline
implies 0.641 App nominal, or 0.471–0.818 App with its ±25% guideline tolerance
and R27's ±2% part tolerance. The reduced-geometry yoke estimate is 0.561 App,
which lies inside this broad range; if it were the only R27 current, it would
give 2.188 Vpp. R29 and other feedback branches also carry current into Y2,
so the TP7 value does not by itself fix the yoke current or its waveform.

The connected stage's loaded TP7 result of 1.740 Vpp corresponds to about
0.446 App through R27 at nominal resistance; the same run's yoke-current
swing is about 0.423 App. This is consistent with other Y2 branches carrying
some current, but the stage still misses the manual TP7 guideline. A5 remains
conditional on the tube/yoke geometry, circuit model and full connection
review; this calculation does not freeze a trim or an operating point.

### A1: page-9 V12 oscillator-to-ramp diode bridge

An independent 600 dpi full-branch crop and a separate 1200 dpi diode crop
support the [source-side read](reference/k7222-11/page9-v12-source-read.json):
V12's cathode is on the left oscillator pulse branch, and its anode is on the
right trace toward A2's marked positive input. Fresh exports of the oscillator
and integrator sheets pass the [cross-sheet comparison](reference/k7222-11/page9-v12-bridge-comparison.json):
V11's collector and V12's cathode share `vertical_pulse`; V12's anode and A2
pin 3 share `ramp_noninv`. A subsequent 1200 dpi source crop rechecks V11's
collector, base and emitter assignment: its lower-right emitter returns to
00 and its left base meets the timing network. Reversed V12 and V11 C/E
assignments both fail the regression check. This closes the local polarity
and endpoint comparison only. Other
oscillator and amplifier connections, their operating points, and the full
independent page-9 netlist remain open.

### A1/A2: page-9 centring bridge replaces the DC source equivalent

The earlier `Icentering` midpoint-neutral current source described above is
superseded. Independent 600 and 1200 dpi reads of source page 9 now resolve
the [local bridge netlist](reference/k7222-11/page9-centering-source-netlist.json):
X1:5/X2 goes through L1 to R4 end A, X1:6/X1 goes through L2 to R4's wiper,
and R4 end B goes through R2 to the second link bank. Each choke symbol labels
the X-side as pins 1/3 and the R4-side as pins 2/4; the paired pins are joined
externally on the drawing. E1 joins R4 end A to 00, E2 joins the R2 end to
12P, E3 joins the R2 end to 00, and E4 joins R4 end A to 12P. The 00 and 12P
verticals cross the yoke lines without junctions. The drawing leaves all four
links open; E1+E2 and E3+E4 are opposite-polarity functional alternatives,
not evidence of the installed pair. The source also does not reveal each
choke's internal winding/coupling construction.

The new [KiCad bridge sheet](circuits/k7222-11-centering.kicad_sch) contains
the four inventoried components R2, R4, L1 and L2. A
[fresh source-to-export comparison](reference/k7222-11/page9-centering-comparison.json)
matches all nine selected component terminals. The E links remain conditional
in the ideal-rail adapter, whose default E1+E2 setting is explicitly a
scenario. R4 is a two-segment 1 kΩ potentiometer; R2 is 150 Ω. L1/L2 each
use a series RL subcircuit and are now source-addressed in the assembled
deck. The former `Icentering` element is gone.

The choke parts list gives only type `1.11.017324.0/01`, with no electrical
rating. The provisional 80 mH nominal is a **design-derived operating
candidate**: at 16 kHz its reactance is about 8.04 kΩ versus about 402 Ω
for the nominal 4 mH yoke. The [isolated bridge check](reference/k7222-11/centering-bridge-check.json)
finds 2.50% incremental AC source current at 80 mH, 9.97% at 20 mH and
0.625% at 320 mH. The 5 Ω nominal / 0.5–15 Ω copper-resistance range is a
DC-drop budget against the documented 150 Ω R2, not a winding measurement.
Core loss and mutual coupling are still unmodeled, explicitly provisional.

R4 is loaded by the yoke, so its isolated DC current is not the earlier
`12/(R2+R4 segment)` series estimate. With the 1 Ω end-stop floor, let
`a=max(1, R4×position)` and `b=max(1, R4×(1−position))`. Seen from the wiper
relative to end A, the 12 V bridge has `Vth=12a/(a+b+R2)` and
`Rth=a(b+R2)/(a+b+R2)`; the yoke branch adds the two choke resistances and
yoke resistance. The isolated ngspice check agrees with this expression at
both link polarities and positions 0, 0.5 and 1 to within 2 µA, allowing for
the two 1 mΩ numerical link contacts. At midpoint, the nominal current is
about ±17.71 mA, not zero. Full assembled-deck DC operating-point runs for
the two link pairs give +17.70951 and −17.70950 mA in `Lhorizontal`, with
unchanged other settings. These are only static checks; neither the fitted
link pair nor connected 16 kHz/native-frame behavior is qualified.

The regenerated A2 coverage report now has provisional register rows for
56/64 frame-path devices, zero devices absent from the ideal-rail assembly,
and eight unregistered horizontal-board magnetics. A6 has 190 partial bounded
entries including the two shared choke parameters and conditional link
selection. A1 still needs the rest of pages 9–10 and the installed link
orientation; A2 still needs the eight magnetics and connected sensitivity.

### A2/A5: T1 half-winding timing scale and profile correction (2026-11-20)

T1 (`012-6921:T1`, stock `1.11.017321.0/90`) is the three-terminal coupled
oscillator winding in the source-connected page-3 stage. C16 is documented
as 100 nF ±10% and runs from the tank node through R21's 27 Ω return; C15
also loads the tank through the transistor base. The native 2 kByte line
period is 62.5 µs (16 kHz), and manual page 17 prints a 14.338–16.338 kHz
horizontal-generator control range. `1/((2πf)²C16)` gives a 0.989 mH ideal
half-winding **scale**, with 0.863–1.369 mH over the printed C16 and
frequency ranges. The network is not an isolated LC resonator, so that
calculation cannot be assigned directly to T1.

The [reproducible autonomous-stage sweep](reference/k7222-11/horizontal-t1-design.json)
uses the source-addressed oscillator sheet, not a prescribed scan waveform.
The old profile default of 0.9 mH per half gives 19.911 kHz, above the
printed generator range. The 1.45 mH starting value already used by the
ideal-rail tune gives 15.890 kHz; a 0.5 µs output step changes the inferred
period by less than 0.01%. At 1.4 and 1.8 mH, the stage gives 16.142 and
14.478 kHz respectively. Its 0.1–5 Ω half-winding resistance endpoints give
15.820–16.230 kHz. Coupling 0.95–0.9999 gives 15.438–15.957 kHz. The
regenerated report changes T1's coupling alone; T2 now has an independent
parameter. Those results support a **conditional** 1.45 mH nominal with
1.2–2.1 mH exploratory bounds. They do not identify the factory winding or
establish the R24 control range; near the nominal setting, R24 positions 0.1
and 0.9 moved the isolated stage only from 15.960 to 15.825 kHz.

The [horizontal oscillator profile](profiles/k7222-11-horizontal-oscillator.json)
now uses 1.45 mH by default and limits the provisional half-winding DC
resistance to 0.1–5 Ω. A2 now records T1's active model, source, bounds and
remaining checks; the [design point](reference/k7222-11/design-point.json)
keeps the ideal and loaded-stage values separate. A6 has three additional
bounded entries. These are an engineering starting point for the connected
stage, not a Phase B calibration or a completed T1 qualification. A2 coverage
is now 57/64 with seven unregistered horizontal-board magnetics; A6 has 193
partial entries.

### A1/A2: conditional page-4 L1 feed branch and operating bounds (2026-11-20)

The [scoped source read](reference/k7222-11/page4-l1-source-read.json) uses
600 and 1200 dpi page-4 views for R42, L1, C22, V18 and T3. Its
[fresh KiCad comparison](reference/k7222-11/page4-l1-comparison.json) matches
the six R42/L1/C22 terminals in the selected 41P-to-R42-to-L1-to-C22-to-00
feed branch and checks that V18's collector and T3 X2:7 share a separate hot
line. The crossing of that hot line with the R42/L1 branch is visually
ambiguous; the scans do not settle whether an ink thickening is a junction
dot. The page-4 approximately 400 V hot-line annotation would imply about
52.8 A through the documented 6.8 Ω R42 if joined directly to the 41 V
rail. This functional stress check selects the no-junction model, but it is
not a visual proof or a measured waveform. C22 polarity, full page-3/4
connectivity and the remaining T3 terminals still need review.

The original L1 stock entry `1.33.003830.0/01` has no printed electrical
value. The [isolated L1 design check](reference/k7222-11/horizontal-l1-design.json)
uses documented R42=6.8 Ω, C22=220 µF and the native 16 kHz line rate. A
first-order LC corner at no more than one fifth of line frequency gives a
minimum 11.24 µH. A maximum 10% additional DC drop relative to R42 gives
0.68 Ω as the candidate copper-resistance ceiling. The active provisional
model is 100 µH/0.5 Ω, bounded by 12 µH–1 mH and 0.05–0.68 Ω. Five isolated
ngspice DC/AC cases agree with the analytical filter to their report
tolerances; the nominal 16 kHz feed ratio is 0.365%, and the nominal corner
is 1.073 kHz. These are operating-design bounds, not factory specifications.
C22 ESR, core loss and saturation, thermal limits and connected flyback
loading remain untested.

The A2 register now covers 58/64 frame-path instances, leaving L3, three L4
sections, T2 and T3 without rows. A6 has 195 partial bounded entries. The
[PLAN blocker](PLAN.md) remains: these scoped results do not close A1, A2,
A3, A5 or A6.

### A2/A3: T2 primary bounds and unloaded TP15 discrepancy (2026-11-20)

The [page-3 primary read](reference/k7222-11/page3-t2-primary-source-read.json)
places T2's top primary terminal after R23 and its bottom terminal at V13's
collector. The selected terminal nets match a fresh KiCad export in the
[nine-case driver check](reference/k7222-11/horizontal-t2-design.json).
The scan does not establish the T2 secondary terminal numbers or phase at
the page-3/4 seam. The printed T2 stock number `1.11.017361.0/90` has no
electrical specification in the inventory.

At the documented 16 kHz line rate, demanding primary reactance at least
five times the documented R23=62 Ω feed resistance gives L≥3.084 mH. Limiting
additional series drop to 10% of R23 gives R≤6.2 Ω. The active 5 mH/2 Ω
primary candidate is now bounded by 3.1–20 mH and 0.1–6.2 Ω. These are
functional budgets, not factory measurements. T1's and T2's coupling
parameters are now separate; the regenerated T1 timing sweep still passes
at 15.890 kHz nominal.

The source-connected but **unloaded** oscillator/driver stage gives 30.02
Vpp at V13 collector, below manual TP15's 45 Vpp ±20% (36–54 Vpp). Across
the nine primary inductance, resistance, ratio and coupling cases, its
collector swing remains 29.56–30.21 Vpp; changing T2 alone does not close
that gap. The secondary swing changes from 1.59 to 15.51 Vpp over the
exploratory ratio bounds, so the unverified secondary and V18 base loading
matter. A connected, probe-loaded TP15 solve is still needed for A3. The
T2 A2 row therefore covers only primary operating bounds; its ratio,
secondary resistance, coupling, core loss and thermal limits remain
unqualified. Coverage is now 59/64, with L3, three L4 sections and T3
unregistered; A6 has 197 partial entries.

### A2/A6: L3 output branch bound (2026-11-20)

The [isolated L3/R35 check](reference/k7222-11/horizontal-l3-design.json)
confirms that the current KiCad output sheet places L3 in parallel with
R35 between `h_hot` and `h_linout`. R35 is documented as 82 Ω ±5%; the
manual's 16 µs retrace gives a 31.25 kHz half-cycle frequency. Limiting
the R35 shunt current to 25% of L3 current even at the low R35 tolerance
endpoint gives a 99.1 µH upper inductance budget at 1 Ω winding resistance.
The active 95 µH ceiling passes that isolated AC check. The nominal 20 µH
and lower 1 µH candidates are exploratory; neither the original coil values
nor connected T3/yoke response has been established. The page-4 branch still
needs independent whole-page source comparison. Coverage is now 60/64,
leaving three L4 sections and T3; A6 has 199 partial entries. The
[PLAN blocker](PLAN.md) therefore remains in effect.

### A2/A6: conditional L4 base-path bound (2026-11-20)

The [L4 branch check](reference/k7222-11/horizontal-l4-design.json)
exports the current page-4 KiCad sheet and confirms that L4:1 and L4:2
are parallel between the T2 secondary and V18 base in the selected E2
configuration. L4:3 is bridged. With 1 V imposed directly across the two
equal chokes for one third of the documented 46.5 µs trace (15.5 µs),
the active 50 µH/1 Ω per-coil worst case reaches 0.533 A. This exceeds the
0.5 A base-drive condition in the BU508AF-class inductive switching test; the analytic
ceiling is 53.9 µH per coil. Two 1 Ω coils in parallel drop 0.25 V at
0.5 A total. These are conditional engineering budgets: the loaded T2
secondary has not been shown to supply the assumed 1 V. The one-third-trace
turn-on budget is an engineering choice, the E2 setting has not been
independently read, and the original A10/2.5 TGL34992
electrical values remain unknown. The stock-matched but bypassed L4:3
inherits the provisional bounds without a measured branch response.
The A2 register now covers 63/64 frame-path instances, leaving T3;
A6 has 201 partial entries. A1, A3, A5 and A6 remain open.

### A5: T3 HV ratio mismatch under the current tap hypothesis (2026-11-20)

The [isolated T3 ratio sweep](reference/k7222-11/t3-hv-ratio-sweep.json)
compares the active 1000-turn HV section with the existing conditional
[design point](reference/k7222-11/design-point.json). The unmeasured drive
sections total 64 turns, giving an ideal 15.625 HV/drive ratio. This is
below the 28.2–35.9 ratio implied by the candidate 60–70 V boost pulse
and the manual's 11–12 kV EHT target. If the 64-turn scale and boost
premise both hold, an ideal-ratio candidate has 1808–2300 HV turns,
with 2035 at the nominal point. The isolated 1 V, 16 µs pulse also
shows the current model's mean HV voltage from 5–15 µs remains below
the conditional target ratio (14.62 versus at least 28.2). The 2035-turn
candidate gives a 29.97 mean ratio versus its 31.80 ideal ratio; neither
result predicts a loaded rectified EHT.
The existing 80 ns sign test is still useful for polarity, but it is too
early to infer a turns ratio from its amplitude. The T3 graph, actual
collector pulse and loaded rectifier path remain unresolved, so the
active 1000-turn hypothesis is retained pending A1/A5 work.

### A1/A5: bounded T3 X1:3/X2:3 return alternatives (2026-11-20)

The [return-variant report](reference/k7222-11/t3-return-variants.json)
exports the current page-4 KiCad T3 ports, confirming that X1:3 and X2:3
share `h_upper2` in the model, while X1:7 shares the HV cold node with
X1:16. It then compares that tied-return hypothesis with an open X1:3
return, without changing the source sheet. The same 1 V, 16 µs primary
pulse drives a V21-class diode, 1 nF EHT capacitance and 200 MΩ leakage
for five line periods. Across all eight HV-sign-compatible candidates,
the flux model's tied variant reaches 20.30–21.90 V in the last pulse;
the open variant reaches 0.0044–0.0045 V. This is a strong conditional
functional discriminator, not evidence that the printed trace joins the
two terminals. The xspice tied variant aborts from a timestep failure
near 6 µs, so its sign result cannot confirm this loaded amplitude test.
The source return, winding order and connected service scores remain open.

### A2/A5: T3 cross-revision HV winding comparators (2026-11-20)

The [T3 winding comparator](reference/k7222-11/t3-hv-winding-comparator.json)
records two firsthand ÜHA78 repair accounts. A [2026 winding account](https://www.robotrontechnik.de/html/forum/thwb/showtopic.php?threadid=22157)
reports 36 layers of 66 turns plus 33 turns, or 2,409 turns of 0.08 mm wire,
for an original HV winding. A [K7222.25 repair guide](https://www.sax.de/~zander/zubehoer/k7222/uha78rep.pdf)
uses a 1,768-turn replacement with about 440 Ω measured DC resistance and
reroutes its cold end to chassis. Neither source proves the K7222.11 factory
winding or its tap/return graph. Using the reported 25 mm tube and 50 mm
maximum outer diameter only as broad candidate mean-diameter endpoints,
[standard copper resistivity](https://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular73e2.pdf)
gives 649–1,298 Ω at 20 °C for the 2,409-turn winding. That calculation makes
the active 1 kΩ winding resistance plausible but does not qualify it; the
active 1,000 turns are below both reported counts.

Holding the isolated loaded T3 bench fixed and changing only HV turns gives
20.30, 37.40, 43.12 and 50.92 V after five 1 V pulses for 1,000, 1,768,
2,035 and 2,409 turns respectively. These values do not predict the connected
11–12 kV operating point. The [A2 register](reference/k7222-11/device-model-register.json)
now includes a provisional T3 row, bringing [coverage](reference/k7222-11/device-model-coverage.json)
to 64/64 assembled frame-path devices. None of the 64 rows closes all
parameter qualification checks, so the [Phase A blocker](PLAN.md) remains.

### A1/A5: HV cold-end and upper-return interaction (2026-11-20)

A [K7222 repair discussion](https://www.robotrontechnik.de/html/forum/thwb/showtopic.php?threadid=6955)
describes the original HV winding footpoint as grounded. A separate
[firsthand board account](https://www.robotrontechnik.de/html/forum/thwb/showtopic.php?threadid=3903)
reports three secondary-coil leads going to the primary assembly and the
other secondary pins unused. The monitor revision and exact pin-to-pin paths
are not identified in either account. They are cross-revision topology
comparators, not a K7222.11 source netlist.

The [cold-return matrix](reference/k7222-11/t3-cold-return-matrix.json)
varies two independent assumptions in the same isolated flux-model bench:
whether X1:3 joins X2:3, and whether the HV cold end X1:16 remains on the
current floating node or is grounded. The current KiCad export joins X1:16
and X1:7 on `h_hvcold`, and joins X1:3 and X2:3 on `h_upper2`. Across all
eight sign-compatible candidates, the current tied/floating configuration
reaches 20.30–21.90 V after five 1 V pulses. Opening X1:3/X2:3 with that
floating cold node leaves 0.0044–0.0045 V, as previously reported. Grounding
X1:16 instead lets the open-return variant reach about 21.10 V whether X1:7
is also grounded or kept separate. Thus the earlier near-zero result does
not independently select an X1:3/X2:3 tie: it depends on the unverified
HV cold connection. This is a low-voltage, isolated diagnostic, not a
connected 11–12 kV prediction or proof of factory wiring. A source-first
pin comparison and connected stage sweep remain required for A1/A5.

### A5: repairer-reported collector pulse versus EHT (2026-11-20)

In [post 095 of a K7222 repair thread](https://www.robotrontechnik.de/html/forum/thwb/showtopic.php?threadid=4514&pagenum=lastpage#157127),
RP describes substituting three TV flyback transformers and reports a
370–420 V K7222 collector pulse corresponding to 11.5–12.5 kV EHT. The
monitor revision, measurement method and whether the values came from an
original or replacement transformer are unspecified. The archived
[comparator](reference/k7222-11/t3-collector-eht-comparator.json) therefore
uses these as cross-revision operating evidence, not K7222.11 factory data.

Dividing the endpoint ranges gives an effective EHT-to-collector amplitude
range of 27.38–33.78, overlapping the existing 28.24–35.94 conditional
design-point range. The active 1,000/64-turn ideal ratio is 15.625, below
both ranges. If 64 drive turns were correct, the repairer range would imply
about 1,752–2,162 HV turns before loading corrections; if the separate
2,409-turn winding account applied, it would imply about 71–88 drive turns.
Neither inference identifies the K7222.11 turn count or return graph. The
next connected T3 sweep should compare the reported winding scales with
feedback, retrace and EHT constraints jointly, rather than select turns from
the isolated ratio alone.

### A5/B3 preparation: prescribed-drive T3 output-stage sweep (2026-11-20)

The [output-stage sweep](reference/k7222-11/t3-output-stage-sweep.json) uses
the source-addressed horizontal-output transcription for V18, T3, V16/V17/V21,
L3/R35/R36 and the selected boost, retrace and yoke-coupling capacitors. It
drives V18 through a prescribed 1 Ω base resistor with a 46.5 µs on pulse,
uses an ideal 41 V feed, a 4 mH/2 Ω yoke, a 1 nF/200 MΩ EHT load and a
65 V initial boost guess. Omitted feedback/sync loads have explicit shunts.
These are stage assumptions, not a source-connected oscillator or a periodic
monitor. The T3 graph remains the current unverified tied/floating-cold case.

The active transformer without optional AC winding loss aborts from a tiny
timestep. With the separately archived passive AC-loss hypothesis, 30 of
32 combinations of eight sign-compatible polarities and 1,000/1,768/2,035/
2,409 HV turns reach the 5 ms endpoint; two still abort. Across the completed
4–5 ms windows, no case jointly falls inside the repairer-reported 370–420 V
collector and 11.5–12.5 kV EHT ranges. The highest final EHT is 10.73 kV,
also below the manual's 11–12 kV range. The representative 1,768-turn case
reaches 382.93 V collector peak, 9.62 kV final EHT and a 15.59 µs collector
flyback pulse at 10% of its swing. Holding that case fixed and sweeping the
declared tube capacitance from 0.25 to 4 nF gives 8.46–9.86 kV final EHT;
that alone does not close the gap. The final EHT still drifts across the
last 16 lines, so these windows cannot establish sustained operation.

This result identifies a concrete connected-stage mismatch under the stated
ideal-drive assumptions. The next sweep must add the source-connected T2/L4
drive and feedback loads, test explicit T3 return alternatives and validate
periodicity before using collector, EHT or retrace as an A3/A5 score.

### A3/A5: T2/L4 loaded output-stage sensitivity (2026-11-20)

The [T2/L4 output-stage sweep](reference/k7222-11/t2-l4-output-stage-sweep.json)
replaces the prescribed V18 base source with the transcribed R23/C23/R33/C24,
V13 collector, T2 and two parallel L4 sections in the selected E2 path. V13's
base still receives a prescribed pulse; its native oscillator, V12, exact
phase and feedback loads are absent. The benchmark keeps the earlier ideal
41 V feed, 65 V initial boost, 1,768-turn T3 hypothesis, unverified winding
graph, yoke/EHT loads and optional AC winding loss.

The page-3/4 source seam does not resolve T2 secondary polarity, so the
sweep tests the current model direction and its reversal. Eleven of 24
combinations of polarity, V13 drive phase, declared T2 ratio and L4
inductance bounds reach 5 ms with the original Gear relative tolerance of
0.001. Retrying with 0.002 reaches 5 ms in all 24. Where both solve, TP15
swing changes by at most 0.03%, collector peak by 0.81% and final EHT by
1.06%. This is a solver comparison, not a physical uncertainty bound.
None of the 24 completed cases reaches the manual's TP15 36–54 Vpp or EHT 11–12 kV
ranges. With the nominal T2 ratio of 3 and 5 µH per L4 coil, off-trace V13
drive gives 24.55 Vpp at TP15, 377.47 V collector peak and 9.44 kV final
EHT. Its EHT changes by about 117 V over the last sixteen line periods, so
the window is not a periodic score. The reversed-polarity, on-trace nominal-ratio case
also completes but gives 29.84 Vpp at TP15 and 9.44 kV EHT; reversing the
unverified secondary alone does not close either gap. The source-connected
oscillator, T3 return
alternatives, complete feedback and periodicity remain open before A3/A5
qualification.

### A5: optional C30 retrace capacitor sensitivity (2026-11-20)

The [C30 comparison](reference/k7222-11/horizontal-retrace-c30-sensitivity.json)
holds documented C27 at 10 nF and treats the transcribed optional 1 nF C30
as either populated or absent. From the manual's 16 µs retrace, the ideal
half-cycle effective inductance is 2.358 mH with both capacitors, or 2.594 mH
with C27 alone. These are whole-network resonance constraints, not T3 or yoke
winding values.

In the same 1,768-turn loaded output-stage hypothesis and 0.002 Gear solve,
removing C30 raises the 4–5 ms collector peak by 2.08–2.13%, raises final EHT
by 2.49–2.50%, and shortens the 10%-swing flyback width by 2.06–2.19% across
the two T2 polarity/drive-phase cases. TP15 changes by less than 0.03%.
Because the source population choice moves the stage above the Phase A 2%
sensitivity threshold, the [design point](reference/k7222-11/design-point.json)
now carries both alternatives. Neither result identifies the installed C30
or establishes periodic operation; A5 remains partial.

### A1/A5: source-visible C27 collector branch (2026-11-20)

A scoped 600/1200 dpi [page-4 source read](reference/k7222-11/page4-c27-source-netlist.json)
places C27 between V18's collector/T3 X2:7/V17 cathode and the shared 00
return at V18 emitter/V17 anode. A fresh KiCad export passes all six
[terminal comparisons](reference/k7222-11/page4-c27-comparison.json).
The export also puts C30 across the same two nodes, but this scoped source
read does not confirm C30's terminals or physical population. It is a check
of C27, not an independent whole-page netlist or a reason to select the
C27+C30 design-point alternative.

### A1: page-4 screen/focus divider source reread (2026-11-20)

The scoped [page-4 divider read](reference/k7222-11/page4-hv-divider-source-netlist.json)
first conflated two adjacent lines at 300/600 dpi: it called the screen-feed
resistor R28 and joined its input to the V21/EHT output. The model comparison
exposed that conflict. A distinct 1200 dpi crop resolves the resistor as R29
and shows its feed line below, separate from the EHT line; R28 is the brightness
control elsewhere on the page. R29 feeds the R30/R31 screen ladder and the R32
focus potentiometer. The corrected source read assigns R30/R31's junction to
X6:2 (UG2), R32's wiper to X6:3 (UG4), and the lower ends to the 00 return.

A fresh KiCad XML export agrees with all eleven pins of V21 and R29–R32 in the
[comparison](reference/k7222-11/page4-hv-divider-comparison.json). The
regression check ties the source pin list to the live KiCad export. This
closes that *external branch comparison* only. It does not identify which T3
internal tap feeds R29, resolve the X1:3/X2:3 return or complete A1's
independent page-3/4 netlist.

### A2/A6: V21 EHT rectifier class response (2026-11-20)

The active V21 [diode model](circuits/k7222-11-horizontal-models.cir) now has
explicit provisional bounds for all seven SPICE parameters in the
[device register](reference/k7222-11/device-model-register.json). The added
IS and N bounds are assumptions, while the RS upper bound follows a forward
voltage check; none identifies the factory V21 assembly. The
[repeatable class fixture](hv_rectifier_check.py) compares the model with
the manufacturers' [Rectron R12000H](https://www.rectron.com/public/product_datasheets/r12000h.pdf)
and [Semtech SDH15K](https://www.semtech.com/uploads/design-support/SG-SEMTECH-PD-DATABOOK.pdf)
limits. The Rectron recovery return threshold is absent from its data sheet,
so the fixture declares a 25%-of-reverse-current proxy. Semtech's recovery
specification applies to discrete devices before assembly.

The [saved response](reference/k7222-11/hv-rectifier-class-check.json) passes
both *class-comparator* fixtures. At Rectron's 10 mA forward and 12 kV reverse
conditions, the model gives 1.736 V and 0.0129 µA, versus 37.5 V and 2 µA
ceilings; its 0 V/1 MHz capacitance is 0.9504 pF versus the 1 pF ceiling.
Recovery is 43.27 ns at approximately 2 mA forward/4 mA reverse using the
declared return proxy, below the 100 ns limit. At Semtech's 200 mA forward
and 15 kV reverse conditions, the model gives 18.99 V and 0.0159 µA, versus
20 V and 2 µA ceilings. Its recovery is 41.34 ns at approximately 50 mA
forward/100 mA reverse to the specified 25 mA threshold, below the 2.5 µs
limit. These broad upper limits do not fit the model uniquely. An initial
100 Ω series resistance missed Semtech's 20 V ceiling; 90 Ω passes.

The changed V21 model was propagated through the saved transistor, diode,
and zener class reports and the loaded [T2/L4](reference/k7222-11/t2-l4-output-stage-sweep.json)
and [T3](reference/k7222-11/t3-output-stage-sweep.json) sweeps. All 24 T2/L4
and 32 T3 conditional cases complete, but none meets the respective joint
targets. The nominal T2/L4 off-trace case now gives 24.55 Vpp at TP15 and
9.49 kV final EHT, still drifting. Across complete T2/L4 cases the V21
change moves final EHT by at most 0.97%; it does not close the target gap.
The refreshed [C30 comparison](reference/k7222-11/horizontal-retrace-c30-sensitivity.json)
shows a 2.49–2.53% loaded final-EHT effect across its two polarity cases,
still above the Phase A 2% sensitivity threshold. The earlier stage numbers
in this evidence log record prior model revisions. V21 identity, joint
parameter corners, stage stress, T3 tap/return mapping, and sustained
native-grid operation remain open.

### A2: V21 connected-stage bound sensitivity (2026-11-20)

The [V21 connected sweep](reference/k7222-11/v21-connected-sensitivity.json)
inserts an ideal zero-volt current probe in series with V21 in the nominal
T2/L4/T3 loaded bench, then varies each of the seven explicit diode parameters
to its low and high bound one at a time. The probed nominal result differs
from the unprobed saved stage by at most 0.033% across final EHT, collector
peak, TP15 swing and flyback width. All 14 bound cases complete. Their
largest final-EHT change is **−4.45%** at the 2.5 µs upper transit-time proxy;
collector peak changes by up to 3.08%. Thus the broad recovery bound is
material to the connected stage and cannot be silently frozen at nominal.

The probed nominal 4–5 ms window reaches 11.939 kV reverse across V21 and
about 12.8 mA forward peak. The largest one-at-a-time reverse peak is
11.948 kV, only about 0.4% below the 12 kV repetitive reverse rating of the
[Rectron comparator](https://www.rectron.com/public/product_datasheets/r12000h.pdf).
This is a conditional, nonperiodic stage window with prescribed V13 drive,
ideal feed, an unverified T3 return graph and no beam-current load. The
milliamperes of transient reverse current in this probe include capacitive
current and are not a data-sheet DC leakage measurement. These readings
prioritize V21 identity, recovery bounds, joint corners and sustained stress;
they do not qualify the factory rectifier or its safety margin.

### A1: page-16 neck-board schematic review closure (2026-11-20)

The independent [page-16 neck-board pin list](reference/k7222-11/page16-neck-source-netlist.json)
covers 17 source nets, 39 component pins, 17 connector pins, six diode
directions, V1 C/B/E and C1 polarity. Its [fresh KiCad comparison](reference/k7222-11/page16-neck-comparison.json)
has no missing, changed or extra board pins. The [static and isolated
checks](reference/k7222-11/page16-neck-static.json) find DC paths to all
listed nets, the expected electrolytic polarity, plausible V1 states and
functional video/intensity response. No winding appears on page 16, so
winding polarity has no applicable check. The real
[A1 source-review gate](reference/k7222-11/source-review-gate.json) now marks
the neck-board schematic reviewed, with zero open frame-path part decisions
and five schematic pages still open: 3, 4, 9, 10 and 18.

This board closure does not assign values or DC behavior to the separate
[measuring-cable inset](reference/k7222-11/page16-meter-cable-source-read.json).
Its transfer, the service voltmeter's response, and a qualified tube-emission
model are still needed before the 0.1/3.6 mV service observations can be
compared. The page-16 decision in
[source-review-decisions.json](reference/k7222-11/source-review-decisions.json)
states that boundary explicitly.

### A1: refreshed page-18 cable semantics (2026-11-20)

The earlier page-18 receipt recorded six functional board-net gaps before
the centring-choke model was connected. Reassembling the current KiCad sheets
and comparing them with all 18 source-labelled cable pairs changes the
[semantic receipt](reference/k7222-11/page18-frame-comparison.json) to 14
board-net matches and four explicitly classified model-scope gaps. X1/X2 now
reach the vertical board through its L1/L2 centring chokes; their physical
connector and yoke endpoints remain checked separately. The refreshed
[physical-pin receipt](reference/k7222-11/page18-board-cable-pin-comparison.json)
still matches all 18 cable pairs at both ends. The page-18 comparison now
hashes the actual assembled component set, so a later source-sheet change
cannot leave its saved semantic result silently unchanged.

The three remaining gaps have distinct boundaries: the vertical-board 41P
and SYNCH paths belong to the excluded converter, and the neck 10.7P
heater branch is replaced by a held thermal state. The V5 collector now
connects to the represented IS neck output. These are model-scope
dispositions, not evidence that the electrical paths have been restored.
The refreshed [panel topology](reference/k7222-11/page18-panel-topology-comparison.json)
still matches its source read. The functional contrast response and remaining
page-3/4 source review are open, so page 18 is not marked complete in the A1
gate.

### A1: corrected page-3/4 intensity seam and unresolved contrast response (2026-11-20)

The short input/neck bench previously left `p35` floating and omitted the
source-read external R1 brightness segments, so it could not test the R2/V1
contrast path. The maintained [signal-path bench](signal_path.py) now supplies
an explicitly ideal 35 V `p35` feed and includes R1's two segments using the
same bounded resistance/position rule as the assembled frame model. This is a
bench correction, not a claim that the unverified flyback-derived 35 V feed
has been qualified.

The [page-3/4 seam read](reference/k7222-11/page3-4-intens-seam-source-read.json)
uses registered 300 and 600 dpi views to separate three page-edge lines:
incoming X9:5 INTENS goes to T200's input (`rx_intens`), V5's collector and
V3's cathode form the IS output to neck X3:2 (`intens`), and the panel HRS
wiper goes to V1's base (`v1_base`). The earlier direct input-to-neck
passthrough claim was wrong; the associated cathode and beam-current
differences must not be used as evidence. The source read does not establish
all junctions or the IS high-state bias, so the full page-3/4 netlist remains
open.

The corrected [contrast stage check](reference/k7222-11/page18-contrast-stage-check.json)
uses the generated highlight pattern and R2 positions 0.05, 0.50 and 0.95.
All three ngspice runs complete. The cathode spans about 0.34–33.70 V at
each setting, but the largest low-versus-high pointwise difference is only
0.11 µV. The held-warm CRT proxy likewise changes by at most 0.00000133 µA
across settings. These are numerical-level changes in this conditional bench,
not a qualified service contrast response. The short bench fixes beam
current at 20 µA for its voltage probe; the manual's page-30 procedure uses
a meter across neck-board R4 to set maximum beam current. The proxy uses
provisional 894/669 K heater/cathode temperature rises, ideal 11.5 kV anode
and fixed −25/350 V grid supplies. The
[panel pin/topology comparison](reference/k7222-11/page18-panel-topology-comparison.json)
still passes, but page 18 remains open. This synthetic-pattern check is not
a native-grid sustained A3 score.

The [16-point DC diagnostic](reference/k7222-11/page18-contrast-dc-diagnostic.json)
holds each video/intensity logic pair fixed, sweeps the two contrast endpoints,
and repeats with an illustrative 100 Ω source impedance ahead of 35P. With
the ideal feed and intensity high, V1 collector current falls by 28.21 mA
from low to high contrast while the modeled IS output remains below 1 V.
The neck cathode DC level does not change at either video level. The
100 Ω value is a sensitivity probe, not a source-derived rail model. The
source graph and IS high-state bias, T200 functional model, original tube
response and service-meter transfer require qualification before judging the
physical monitor's contrast function.

A separate [IS drive diagnostic](reference/k7222-11/page3-4-is-drive-diagnostic.json)
resolves an apparent contradiction between that DC result and the short
highlight trace. With nominal 3 pF junction capacitance on neck-board V2:4,
IS has a 4.41 V median during stable dark-video/intensity-high intervals,
although a fixed-input 0.2 ms solve remains at 0.302 V. Changing only that
diode's capacitance to its declared 0.5 pF lower and 20 pF upper bounds moves
the transient median to 0.282 V and 25.45 V; the zero-capacitance diagnostic
gives 0.202 V. The cathode remains near its dark level in those intervals.
With video bright, IS stays below 1 V for either intensity input and the
modeled cathode difference is below 0.01 V. Thus the nominal high interval
is capacitive coupling in this model, not evidence of a stable IS logic high
or a working intensity/contrast response. The 20 pF case exceeding the 5 V
logic rail further shows why the transient cannot validate the original
circuit. This isolates the model's dependence on an unqualified diode
parameter; it does not identify a missing physical connection or license an
unsourced pull-up in the source-addressed schematic.

A renewed [page-16 source read](reference/k7222-11/page16-neck-source-netlist.json)
checks the IS label in independent 300 and 600 dpi renders and corrects the
render hashes in the saved source artifact. The printed note explicitly says
`L = intensiv, H = normal`; V2:4 has its anode at IS and cathode at the SUK
drive. The isolated neck check now labels its four input states by the
actual IS polarity and asserts that low IS lowers the cathode during bright
video. This corrects the earlier ambiguous `intensity_only` and
`video_and_intensity` labels; it does not qualify the main board's high-state
drive or the manual's 15 V normal-bright cathode level.

The operating manual (`older-operation.pdf`, PDF pages 10–11, printed pages
8–9) describes roughly 35 V at the cathode for dark video and 15 V for normal
bright video. Its Fig. 6 shows a functional 15 V contrast reference and V1/V5
control paths, but it is not a pin-level substitute for the page-3/4 board
schematic. In the isolated neck report, an ideal 5 V IS input with bright video
reaches only 4.39 V at the cathode. This does not validate a guessed 5 V
pull-up as the missing board drive. The independent page-3/4 read still needs
to identify the original steady IS bias before the contrast response can be
qualified against the manual.

### A1: V5 lower return and V4 reference conflict (2026-11-20)

Two independently rendered page-3 crops, one at 300 dpi and one at 600 dpi,
show V5's lower-right lead crossing the 12P and sync-collector lines without
junction dots, then reaching 00. The corrected
[page-3 source read](reference/k7222-11/page3-r11-r37-source-read.json)
therefore moves that terminal from the earlier, erroneous 12P list to 00.
The active input model already returns V5 to 00, so this correction improves
source provenance but does not fix the missing steady IS high state. The two
image hashes and the parent schematic hash are in the source-read artifact;
V5 C/E polarity remains unqualified.

The page-8 factory parts list identifies V4 as `9.1 ZC`, while the operating
manual's simplified Fig. 6 (PDF page 11) labels a 15 V reference. This may
reflect a functional simplification or a document revision; the figure does
not establish that factory V4 was a 15 V zener. The extended
[contrast DC diagnostic](reference/k7222-11/page18-contrast-dc-diagnostic.json)
holds bright video, both incoming intensity states and both R2 endpoints,
then changes only V4's model breakdown from 9.1 to 15 V. The local reference
rises by 5.85–5.88 V and V1 collector current changes, but steady IS and
cathode voltages do not move in any of the four cases. The result rules out
that single substitution as a repair for this bench; it does not resolve the
manual's reference topology or qualify the complete page-3/4 source graph.

### A1 fallback boundary: required steady IS drive (2026-11-20)

The [IS boundary requirement](reference/k7222-11/page3-4-is-boundary-requirement.json)
uses the same source-addressed input/neck deck, holds incoming INTENS low,
and replaces only V5 with a fixed Thevenin source at IS for each
DC solve. It is a diagnostic for a possible labelled fallback, not a change
to the active source model. The bench retains neck diode V2:4, the 20 µA
fixed cathode load, ideal rails and the provisional silicon models.

With dark video, the cathode stays at 33.69 V across the tested 0–16 V IS
sources. With bright video, an ideal 15.7 V IS source gives 15.01 V at the
cathode, close to the manual's approximate 15 V normal-bright level, and
delivers 28.7 mA. At the same source voltage, 10, 100 and 1,000 Ω series
resistance give cathode levels of 14.73, 12.66 and 5.81 V. A simple 5 V
pull-up cannot reach the manual level, and a future equivalent needs both
sufficient voltage and current drive. This sweep does not identify the
original V5 drive, establish the manual contrast transfer, or qualify CRT
emission and service-meter observations.

### A1 document conflict: detailed contrast graph versus manual Fig. 6 (2026-11-20)

The detailed page-3/4 source read places V5's upper lead at IS and V1's
lower lead at KRS, the external contrast wiper/low contact. The operating
manual's functional Fig. 6 instead puts V1's lower lead at IS and V5 at the
lower contrast contact. The
[fixed-logic topology comparison](reference/k7222-11/page3-4-manual-topology-comparison.json)
keeps the same input, neck, diode and transistor models and moves only those
two leads and V1's printed 5.1 kΩ emitter shunt. It tests the listed 9.1 V
V4 and a separate hypothetical 15 V V4, two R2 positions and two bounded
brightness positions. The 15 V variant tests the manual's reference label;
it does not replace the factory-list zener value.

At brightness position 0, the detailed topology gives about 0.341 V at
the bright cathode with no R2 response. The swapped topology with 9.1 V V4
gives 13.56–16.48 V and a 2.92 V span across R2 when incoming INTENS is low;
all three compared topologies keep dark video near 33.69 V. With incoming
INTENS high, however, the swap gives about 16.49 V at both R2 endpoints.
The manual describes the V5/contrast action using a regenerated intensity
signal. The provisional T200 model inverts the raw incoming INTENS line
before V5, so the raw 0/1 labels in this sweep cannot establish a polarity
conflict with the manual. The terminal swap is a useful functional
alternative but does not settle which document maps the K7222.11 board pins
or justify changing the active sheet.

The [connected ideal-rail DC comparison](reference/k7222-11/page3-4-connected-contrast-dc.json)
repeats the same three-terminal swap in the 222-component assembled deck,
with V4 kept at its listed 9.1 V, brightness position 0, fixed bright video,
and both raw incoming INTENS and R2 endpoint states. The active detailed
wiring gives a 0.328 V cathode and no measurable R2 span in either input
state. The manual alternative gives 13.375–16.329 V at the cathode, a
2.954 V R2 span, for raw incoming INTENS low; with that input high it gives
16.336 V at both R2 endpoints. With dark video and R2 centred, both
topologies give 33.671 V at the cathode for either raw intensity state,
near the manual's approximate 35 V dark level. The result is consistent with
the isolated fixed-logic comparison after the rest of the ideal-rail circuit
is attached.
This is a DC operating point: EHT is approximately zero, scan is not
periodic, and the tube response and regenerated INTENS polarity are still
unqualified. The manual alternative remains conditional and is not the
active KiCad topology or a connected native-grid A3 score.

The connected runner now exposes the terminal swap as the labelled
`manual-fig6-equivalent` contrast topology. It changes only V5's upper
terminal, V1's lower terminal and the printed 5.1 kΩ shunt terminal in the
assembled deck; the KiCad export stays unchanged. Run metadata and the
calibration proposal/freeze bind the topology, and both the native runner and
final gate reject a different deck topology from its grid freeze. The default
remains the detailed page-3/4 wiring. The stage label is
`manual-fig6-contrast-control`.

A [200 µs connected startup screen](reference/k7222-11/page3-4-connected-contrast-transient.json)
uses the archived native logical capture and one unverified T3 sign candidate.
With the revised V13/V18 models, the detailed topology reaches 200 µs
(2,425 rows) under default sparse settings. The manual sparse equivalent
also reaches 200 µs (2,396 rows). With KLU,
50 ns maximum step, 0.002 relative tolerance and 10⁻⁸ A absolute tolerance,
the manual equivalent reaches 200 µs (5,166 rows). This only
establishes short-startup solver feasibility for that one candidate. It
does not score a field, show lock or periodic settling, prove the manual
terminal assignment, or qualify the native frame.
The [same variant extended to 2 ms](reference/k7222-11/page3-4-connected-contrast-2ms.json)
also completes with 82,724 data rows. Its final EHT is 5.143 kV, below
the 11–12 kV sustained target. This
extends the solver feasibility bound, but remains only about one tenth of
the 19.5 ms native field and cannot establish an A3 or A5 pass.

The [page-16 measuring-cable transfer check](reference/k7222-11/meter-cable-transfer-bound.json)
uses the source inset's unvalued series capacitor and a conditional common
return. The ideal passive RC has zero steady DC gain. With an illustrative
100 pF series capacitor, a 1 MΩ AC meter passes less than 4% of a 51.3 Hz
field component but more than 99% of a 16 kHz line component. These are
sensitivity cases, not values assigned to cable 1.11.017154.0. A comparable
Fluke meter documents 1 MΩ for AC mV and 10 MΩ for DC mV; the Robotron
instruction names no meter model or AC/DC mode. The cable's lower-terminal
connection and shunt values are also absent from the inset. The 0.1 mV rise
and 3.6 mV target therefore remain unscorable until the transfer and native
grid/tube response are bounded.

The [A2 implicit-default inventory](reference/k7222-11/a2-implicit-default-audit.json)
compares every registered discrete semiconductor model declaration with a
first critical parameter set based on the [ngspice device-model manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).
The 51 frame-path transistor, diode and zener instances map to 24 register
entries; every one of those entries leaves a screened default implicit. The
inventory checks current model text and cross-checks all instance IDs against
the A2 coverage report. It is a worklist, not a model-response pass: source
bounds, joint sensitivities, connected stress, subcircuit internals and any
other material defaults remain to be examined before A2 can close.

The vertical-stage 1AE15 diode model now declares its formerly implicit
`VJ=1`, `M=0.5`, `FC=0.5`, `EG=1.11` and `XTI=3` values. The [Diodes
Incorporated 1N4148W SPICE model](https://www.diodes.com/spice/download/1589/1N4148W.spice.txt)
supplies a same-class `M=0.333` comparator, not a 1AE15 identification;
the other spreads are assumed. Both A2 and A6 registers carry these five
provisional ranges, bringing A6 to 214 entries. The regenerated
[implicit-default audit](reference/k7222-11/a2-implicit-default-audit.json)
has 41 affected instances in 23 entries instead of 51 in 24. The
[isolated response check](reference/k7222-11/vertical-diode-model-check.json)
still passes its four 1N4148-class fixtures. The
[24-case stage sensitivity receipt](reference/k7222-11/vertical-diode-stage-sensitivity.json)
completes with a maximum 5.52% yoke-span shift over all twelve diode
parameters. The new five alter yoke span by less than 0.001% individually
at fixed temperature; `EG` and `XTI` show zero change there because they
govern temperature behavior. A paired solve of the current deck with the
five values explicit and implicit produced identical four reported stage
metrics. The old sensitivity receipt used older profile and runner hashes,
so its different baseline is not evidence of a model-induced change.
Neither the one-at-a-time bench nor the class comparator qualifies joint
corners, original-device ratings or connected native-frame stress.

The monitor tooling check on the local Python 3.9.6 runner exposed use of
`hashlib.file_digest` in artifact verification, although that API is absent
there. A shared [streaming SHA-256 helper](file_hash.py) now reads bounded
1 MiB chunks for cache, raw trace, image, gate and runtime checks. The
[pinned-runtime builder](monitor_runtime.py) validates every archive member
before extraction and binds the imported hash helper and command runner in
its receipt. The rebuilt local ngspice-47 runtime at
`build/monitor/runtime-phase-a-gcc16-verified/` verifies; its `runtime.json`
SHA-256 is `82aca1ae153d04d101e502c431305435ccad5bd993bfabbf52de33f72d3fb2f9`
and installed solver SHA-256 is
`3e14f93f378ffcb37ec55e797b3da6099ce9ee6293a4fe7f203619299a5f9da9`.
These are local build artifacts, not committed source files. Three horizontal
class-check receipts needed only updated register hashes; their measured
results did not change. The full-path regression now checks the current
260/260 source-addressed connected parts, while the audit still marks 81
entries unresolved for qualification. The vertical-output regression now
uses the actual A3 input and Y2 probe columns for its input equality and
R/L winding checks. With `MONITOR_RUNTIME` set to the verified runtime,
`make test-monitor` passed 304 tests with no skips. This test pass verifies
tool behavior and current receipts, not a sustained native-grid frame or
completion of the remaining Phase A done conditions.

The connected assembly uses the neck profile's parameterized `1AD50_BOUND`
for eight printed 1AD50 clamps and four input/sync 1AE15 diodes; the two
fixed vertical-stage copies of that alias are removed when the full assembly
is built. All three declarations now make `VJ`, `M`, `FC`, `EG` and `XTI`
explicit, and the neck profile bounds the connected values. The nominal
values remain the earlier ngspice defaults. The diagnostic neck profile uses
the same bounds so the atlas and continuous thermal lifecycle decks resolve
the shared model. The lower `M=0.333` endpoint
comes from the [Diodes Incorporated 1N4148W SPICE model](https://www.diodes.com/spice/download/1589/1N4148W.spice.txt);
it is a same-class comparator, not an identification or original-part limit.
The other new spreads are assumed. A2 and A6 now register these five values
for both printed-type families, bringing A6 to 224 partial entries. The
[implicit-default audit](reference/k7222-11/a2-implicit-default-audit.json)
falls from 41 affected instances in 23 entries to 29 in 21. The
[1AD50 isolated comparator](reference/k7222-11/neck-diode-model-check.json)
still passes, and the page-16 static and page-3/4 IS-drive diagnostics retain
their measured values; only model/profile/deck hashes changed. Regenerating
the [vertical-diode stage sweep](reference/k7222-11/vertical-diode-stage-sensitivity.json)
after the fixed-copy edit gave identical baseline and 24 bound-case metrics.
The two printed types still share a provisional connected electrical proxy,
and no source-backed original rating, temperature sweep, joint bound or
native connected-stage stress has been established for these twelve parts.
With the verified pinned runtime, `make test-monitor` passes 306 tests with no
skips after these model and receipt changes. The rerun includes atlas nominal
publication, the continuous neck thermal lifecycle, saved-report equality and
the connected V21 sensitivity check; it does not close the remaining Phase A
done conditions.

The horizontal `HOR_D`, `HOR_RECT`, `HOR_Z6` and `HOR_HV_RECT` aliases now state
`VJ=1`, `M=0.5`, `FC=0.5`, `EG=1.11` and `XTI=3`, the previously implicit
nominal values in the [ngspice diode model](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).
These four declarations serve eight additional frame-path diodes in six A2
register entries: two 1AL25 signal diodes, four 1YL1 flyback rectifiers, V11's
zener and V21's EHT rectifier. All five new bounds are explicitly provisional
engineering spreads; neither the signal-diode nor the rectifier comparators
establish original-part values. The [A2 audit](reference/k7222-11/a2-implicit-default-audit.json)
now records 21 affected instances in 15 entries, and the A6 register has 254
partial rows. Isolated class fixtures still pass with unchanged measured
values. The refreshed 32-case T3 and 24-case T2/L4 prescribed-drive sweeps
retain their prior values and still find no joint manual TP15/EHT match.
The [V21 connected-stage sweep](reference/k7222-11/v21-connected-sensitivity.json)
now completes all 24 one-at-a-time bounds: the new `VJ`, `M` and `FC` cases
move final EHT by at most 0.17%, `EG` and `XTI` make no difference at nominal
temperature, and the slow `TT` endpoint still changes it by 4.4%. These
conditional tests do not establish original diode identity, joint corners,
temperature behavior or sustained native-grid stress.
The refreshed non-V21 receipts differ from the preceding commit only in
source/model/deck hashes; V21's nominal and prior 14 bound results are
unchanged, with ten new complete cases. With the verified pinned runtime,
`make test-monitor` passes 306 tests with no skips. This validates the current
checks and receipts, not the outstanding A1, A2, A3, A5 or A6 done conditions.

The five printed `1SA20C` and two `1SC60A` instances now have all nine
screened formerly implicit BJT parameters explicit in their separate
[class models](circuits/k7222-11-small-transistor-models.cir). The
[ngspice manual's BC546B example](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf)
provides provisional finite `IKF`, `RB` and junction-shape values; `EG`,
`XTI` and `FC` state the former simulator defaults. The assumed engineering
spreads are recorded in both A2 and A6 registers and are not original-part
limits. The [A2 audit](reference/k7222-11/a2-implicit-default-audit.json)
falls from 21 affected instances in 15 register entries to 14 in 13; A6 grows
from 254 to 272 partial entries. The [isolated BC546B-class comparison](reference/k7222-11/small-transistor-class-check.json)
still passes, now at hFE 268.7, 0.097 V saturation and a 181.7 MHz
transition-frequency proxy. Seven other device class-check receipts
changed only in the shared register hash; their measured results are unchanged.

The revised models do move some conditional stage results. The
[IS-drive diagnostic](reference/k7222-11/page3-4-is-drive-diagnostic.json)
now has a 4.15 V nominal median in its transient high interval, versus 4.41 V
before; its lower and upper neck-diode-capacitance cases give 0.24 and
25.22 V, respectively. Fixed input still settles near 0.30 V, so this is not
a qualified high-state drive. The [page-18 loaded contrast check](reference/k7222-11/page18-contrast-stage-check.json)
still has only 0.98 µV maximum low/high cathode difference and 0.00000223 µA
provisional beam difference. The [manual terminal-swap comparison](reference/k7222-11/page3-4-manual-topology-comparison.json)
now gives 13.53–16.44 V and a 2.91 V R2 span at the tested brightness
endpoint; that topology remains a source-unverified alternative. The
[vertical diode stage sweep](reference/k7222-11/vertical-diode-stage-sensitivity.json)
baseline yoke span moves from 0.545973 to 0.546044 A, and its maximum
one-at-a-time bound change is now 5.50%. The refreshed
[V21 sweep](reference/k7222-11/v21-connected-sensitivity.json) changes only
its register hash; all 24 electrical results are identical. These connected
diagnostics do not qualify the original transistor identities, joint corners,
temperature behavior, switching storage or sustained native-grid stress.
With the verified pinned runtime, the refreshed receipts pass all 18 focused
checks and `make test-monitor` passes 306 tests with no skips. This verifies
model/report consistency, not completion of the remaining Phase A conditions.

The source-connected [T2/L4 loaded sweep](reference/k7222-11/t2-l4-output-stage-sweep.json)
now applies the [ST BU508AF](https://www.st.com/resource/en/datasheet/bu508af.pdf)
9 V absolute maximum emitter-base reverse-voltage comparator to V18. This is
a class limit, not a rating recovered for the printed transistor. Sixteen
of 24 previously completed 4–5 ms cases drive V18's base below −9 V, even
though the model has no reverse emitter-base breakdown mechanism. None of
the 24 reaches both manual TP15 and EHT ranges, so no stage pass follows.

To test whether the missing TP15 swing alone explains EHT, the
[ideal TP15 boundary sweep](reference/k7222-11/tp15-equivalent-output-stage.json)
replaces V13 and its base drive with a 0–45 V source at its collector, leaving
the transcribed T2/L4/V18/T3/output load in place. Thirty-four of 36 combinations of
1,768/2,035/2,409 HV turns, T2 ratios 1/3/10, two secondary polarities and
two pulse phases reach the 19–20 ms window; two abort. Two 2,035-turn cases match the
manual 11–12 kV EHT range and the independent repairer's 370–420 V collector
comparison. The model-polarity, on-trace case gives 11.281 kV EHT, 388 V
collector peak, 14.34 µs flyback at the 10% crossing, and only 2.74 V EHT
drift across the 16-line window. Yet its V18 base reaches −54.04 V; the
reversed-polarity, off-trace match reaches −54.11 V. Every one of the 34 completed cases
exceeds the 9 V class limit, including the lower-EHT cases. The apparent
voltage match is therefore not an admissible equivalent-driver operating
point. A 16-line EHT drift check is also not a three-field native-grid
periodicity score. The source T2 secondary/T3 graph, V18 switching stress and
stage loading must be resolved or bounded before A3/A5 can close.
With the verified pinned runtime, `make test-monitor` passed 307 tests with no
skips after the stress audit and dependent receipt refresh. This verifies the
diagnostic and saved reports, not a source-validated or stress-safe stage.

### A1: page-3/4 T2/L4/V18 seam reread (2026-11-20)

The [scoped source comparison](reference/k7222-11/page3-4-t2-l4-source-read.json)
uses 300/600 dpi full-page views and a different 1200 dpi page-4 view.
The visible page-3 T2 primary ends agree with the selected driver model.
On page 4, V18's base meets R36 and the L4:3 right side; R36 and V18's
emitter return to 00. The drawing has an upper E2 branch around L4:3, so
the working bridged branch is one possible jumper setting. The installed
setting is not known. The scans cut through the T2/L4 seam, so they do not
establish T2 secondary terminal order, phase or return, or independently
prove the parallel L4:1/L4:2 model path. The earlier T2/L4 and ideal-TP15
sweeps therefore remain conditional. This is a scoped comparison after model
exposure, not the independent whole-page A1 netlist.

The [eight-case L4-path sensitivity](reference/k7222-11/t2-l4-topology-sensitivity.json)
holds the conditional 2,035-turn T3 and ideal 45 Vpp TP15 boundary fixed,
then tries the selected parallel L4:1/L4:2 path, a single coil, two series
coils, and a near-short bridge at T2 ratios 1 and 10. Seven 19–20 ms cases
complete; the series-path ratio-10 case aborts. All four completed ratio-1
cases match the EHT range but drive V18's base to −53.19 to −54.65 V. The
near-short bridge at ratio 10 stays within the 9 V reverse-base class
comparator at −7.52 V, but gives only 9.92 kV EHT. None is both a voltage
match and reverse-base safe. The selected parallel ratio-1 case reproduces
11.281 kV EHT, 388 V collector peak and −54.04 V at V18's base. These branch
changes alone do not rescue the apparent TP15 voltage match. The alternate
L4 paths are exploratory impedance bounds, not source-read jumper settings;
T2 secondary and T3 graph uncertainty still governs the next stage check.
With `MONITOR_RUNTIME=build/monitor/runtime-phase-a-gcc16-verified`, the
complete `make test-monitor` suite passed 308 tests with no skips on Python
3.9.6. This validates the saved sensitivity receipt and other tool checks;
it does not meet the remaining Phase A done conditions.

### A2/A6: V18 high-current BJT bounds (2026-11-20)

The active V18 `HOR_OUTPUT_N` model now declares `IKF`, `RB`, `RC`, `RE` and
the screened junction and temperature defaults. The [parameter-corner
receipt](reference/k7222-11/horizontal-output-bjt-bounds.json) compares the
live model with the [ST BU508AF class sheet](https://www.st.com/resource/en/datasheet/bu508af.pdf)
at 25 °C. All four independent `BF`/`IKF` corners meet the sheet's 0.1 A
gain interval of 10–30 and 4.5 A gain floor of 5; the lowest 4.5 A gain is
6.41. The combined maximum registered `RB`/`RC`/`RE` case gives 0.625 V
collector-emitter and 1.067 V base-emitter saturation proxies, below the
1.0/1.1 V class comparators. The nominal model gives gains 20.50 and 11.18
at 0.1/4.5 A. This is a comparator for an unidentified original transistor,
not a fitted SU165 model. The [switching proxy](reference/k7222-11/horizontal-output-switching-proxy.json)
now uses the registered `TF` endpoints and about 0.495 A on-base drive; its
nominal command-to-clamp-10% and clamp-10–90% intervals are 0.801 and
0.745 µs. Those fixture intervals are not the sheet's inductive storage
and fall-time measurements. The original identity, joint capacitance/transit
and temperature bounds, and connected switching stress remain open.

The refreshed [prescribed-V13 T2/L4 stage](reference/k7222-11/t2-l4-output-stage-sweep.json)
completes all 24 cases with a bounded solver retry, but none meets the
manual TP15 or EHT window. Sixteen cases exceed the 9 V BU508AF-class
reverse emitter-base limit; with the revised V13 model, the nominal off-trace
case reaches 9.509 kV EHT, 380 V collector peak and −17.60 V at V18's base.
Explicit DC gain and
series resistance therefore narrow A2's model inventory without closing
the A3 connected waveform score or A5 design point. The level-1 BJT model
has no reverse emitter-base breakdown or full safe-operating-area behavior.
With `MONITOR_RUNTIME=build/monitor/runtime-phase-a-gcc16-verified`, the
refreshed `make test-monitor` suite passed 309 tests with no skips on Python
3.9.6. This checks the saved receipts and tool contracts, not the missing
source, safe connected-stage or full design-point evidence.

### A2/A6: V13 driver model assumptions (2026-11-20)

The active V13 `HOR_DRIVER_N` model now states `IKF`, `RB`, `RC`, `RE`,
junction-shape and temperature assumptions explicitly. The source remains
the historical SF128 base-family table; the printed `SF1280` suffix does not
identify a gain group or an exact model. The [five-case class-corner
receipt](reference/k7222-11/horizontal-driver-bjt-bounds.json) checks nominal,
low/high `IKF`, maximum series resistance, and combined low-`IKF`/maximum
resistance at 25 °C. All five meet the broad family comparison at 50 mA/2 V,
the 0.5 V saturation comparator at 150/15 mA, and the 60 MHz transition-
frequency floor. Nominal gain is 55.55, the 15 MHz gain-product proxy is
144.69 MHz, and saturation is 0.101 V. The combined corner saturates at
0.285 V. These are selected checks, not a qualification of the unknown
family group or the broad `BF` range jointly with every other bound.

The [A2 default audit](reference/k7222-11/a2-implicit-default-audit.json)
now counts 12 affected semiconductor instances in 11 register entries;
the [A6 register](reference/k7222-11/class-typical-register.json) has 300
partial entries. Original V13 storage/fall behavior, package/rating,
temperature and connected current/voltage stress remain open. The selected
corner results do not close A2 or A6. The refreshed
[prescribed-V13 T2/L4 sweep](reference/k7222-11/t2-l4-output-stage-sweep.json)
completes 24 cases after bounded solver retry; none reaches the manual TP15
or EHT window. Its nominal off-trace case gives 24.58 Vpp TP15, 9.509 kV
final EHT, 380 V collector peak and −17.60 V at V18's base. Sixteen of the
24 cases exceed the 9 V V18 reverse-base class comparator, so the driver
model update alone does not establish a viable A3 operating point.
With `MONITOR_RUNTIME=build/monitor/runtime-phase-a-gcc16-verified`, the
full `make test-monitor` suite passes 310 tests with no skips on Python
3.9.6. This verifies the refreshed receipts and tool contracts; the A1,
A2, A3, A5 and A6 completion evidence is still missing.

### A3: bounded native-grid four-field attempt (2026-11-20)

The [bounded-attempt receipt](reference/k7222-11/native-grid-four-field-bounded-attempt.json)
records both solver outcomes and the shared-resolution comparison. The
connected runner used the archived native logical capture, verified
`runtime-phase-a-gcc16-verified`, conditional `t3-fc941ad61c50ce31` sign
candidate and `manual-fig6-equivalent` contrast wiring. Both trials used
KLU, relative tolerance 0.002 and absolute tolerance 10⁻⁸ A. Their raw
traces remain under `build/monitor/phase-a/native-v13-v18-grid-*/`; the
small [50 ns](reference/k7222-11/native-grid-50ns-partial-diagnostic.json)
and [200 ns](reference/k7222-11/native-grid-200ns-partial-diagnostic.json)
diagnostics preserve trace hashes, complete-row counts and 1 ms time-weighted
voltage bins. The first solve was deliberately stopped after 257 s because
its progress projected beyond the search budget; it has 983,665 complete
rows through 16.126 ms. The second exhausted its 596 s solve budget and
has 2,063,542 complete rows through 36.435 ms. Neither reached the required
four-field endpoint, so the runner reported no accepted three-field lock or
service score.

At the shared 15–16 ms interval, the 50 ns trace averages 7.936 kV EHT and
the 200 ns trace 9.668 kV, a 21.8% resolution difference. The new
[50 ns](reference/k7222-11/native-grid-50ns-horizontal-chain.json) and
[200 ns](reference/k7222-11/native-grid-200ns-horizontal-chain.json)
horizontal-chain diagnostics show that V13's collector keeps about 16 pulses
per millisecond and V18's collector keeps 15–17 across the 2–12 ms bins.
The pulse train is present; the earlier inference from a 100 V `h_sync`
threshold was too broad. The TP17-mapped `h_sync` node instead swings only
15.3–20.5 Vpp at 50 ns and 18.7–20.8 Vpp at 200 ns over 1–12 ms, well below
the manual's 80 Vpp ±20% guideline. Rare large `h_sync` bursts coincide with
large V18 collector peaks and do not establish a stable TP17 waveform.
The 200 ns EHT exceeds 12 kV in late bins, but that crossing is not a
converged steady state. The conditional T3 pulse-winding/rectifier path,
numerical stiffness and TP17 under-amplitude block a native-grid A3 score;
the unfinished traces cannot qualify A5.

### A3/A5: source-loaded TP17 winding sensitivity (2026-11-20)

The [TP17 stage sweep](reference/k7222-11/t3-tp17-path-sweep.json) adds
source-connected V14, C18 and R28 to the prescribed-drive T3/output bench.
Page 4 places V14's cathode at the X2:6/TP17 pulse node and its anode at the
C18/R28 brightness node; this local read agrees with the live transcription,
but does not settle the internal T3 winding graph. The sweep varies the
provisional X2:5–X2:6 section from 2.5 to 5 and 10 turns, its existing bound.
It also varies C18 series resistance as an explicit *numerical diagnostic*,
not a sourced capacitor specification.

With 2.5 turns and ideal C18 or 1 Ω series resistance, ngspice aborts at a
tiny timestep. At 10 Ω it completes the 4–5 ms prescribed-drive window and
gives 24.94 Vpp at `h_sync`, below TP17's 64–96 Vpp manual guideline. The
5- and 10-turn cases at 10 Ω also abort at tiny timesteps. Thus the sweep
does not establish a turns-ratio remedy, a physical C18 loss value or an A3
service score. It independently reproduces both the TP17 amplitude gap and
the numerical stiffness of the conditional T3 pulse path. The next A5 move
is a source-informed, labelled T3 equivalent from the PLAN fallback if the
source cannot resolve this winding and its return; any such candidate still
needs a converged connected-grid check before A3 or A5 can close.

### A5: labelled passive T3 equivalent screen (2026-11-20)

The [passive-coupled sweep](reference/k7222-11/t3-coupled-equivalent-sweep.json)
and its [parameter candidate](reference/k7222-11/t3-coupled-equivalent-parameters.json)
implement the PLAN fallback as a *candidate*, leaving the existing flux
model as the default. Each provisional winding section retains its declared
series resistance, leakage and capacitance. Coupled inductors use 0.999
mutual coupling and the provisional B/H origin slope, which gives 486 µH
primary magnetizing inductance. The model exposes an algebraic flux probe for
the existing periodicity check and is labelled
`T3_PASSIVE_COUPLED_EQUIVALENT` in connected-run metadata. The coupling,
core slope and section parasitics are not yet source-qualified `class-typical`
bounds, and the graph remains conditional.

All eight sampled 4–5 ms prescribed-drive stage cases complete with the
pinned runtime. With the algebraic probe and 100 ns maximum step, 7.5 auxiliary
turns and the 1,000-turn HV hypothesis give 86.91 Vpp TP17 but 13.162 kV
final EHT; 7.5 turns and the 1,768-turn cross-revision comparator give
56.78 Vpp and 10.657 kV; 7.5 turns and the conditional 2,035-turn A5 scale
give 72.32 Vpp and 10.188 kV. None of the sampled cases jointly reaches
TP17's 64–96 Vpp guideline and 11–12 kV EHT. The 7.5/1,768 case changes to
57.97 Vpp and 10.519 kV at 50 ns. Removing only the non-driving flux probe
at 100 ns changes it to 63.52 Vpp and 11.842 kV. That roughly 10% probe
sensitivity and the remaining step-size difference forbid a T3 freeze or
stage-level waveform qualification.

The first [bounded connected attempt](reference/k7222-11/native-coupled-equivalent-bounded-attempt.json)
used a temporary probe-integrator version of this equivalent and the same
7.5/1,768 parameter file. The saved deck hash identifies that variant; it is
not the current algebraic-probe implementation. Its 200 ns, four-field solve
times out after 596 s with 1,882,692 complete raw rows through 26.114 ms.
The [partial EHT/TP17 bins](reference/k7222-11/native-coupled-equivalent-partial-diagnostic.json)
and [horizontal-chain bins](reference/k7222-11/native-coupled-equivalent-horizontal-chain.json)
show ongoing flyback pulses. The 15–16 ms bin has 12.386 kV mean EHT and
67.3 Vpp TP17; the 20–21 ms bin has 12.330 kV and 87.0 Vpp but 41 V13
collector threshold crossings; the 24–25 ms bin has 12.260 kV and 59.6 Vpp.
These are startup diagnostics from one incomplete field history, not a
periodic joint TP17/EHT result or a connected A3 score. This variant cannot
establish the behavior of the current algebraic-probe implementation.

The separate [current-code bounded attempt](reference/k7222-11/native-coupled-algebraic-bounded-attempt.json)
uses that algebraic flux probe and the same native capture, parameter file,
candidate, solver settings and 200 ns maximum step. It also times out after
596 s, with 1,722,140 complete rows through 21.140 ms. Its
[EHT/TP17 bins](reference/k7222-11/native-coupled-algebraic-partial-diagnostic.json)
and [horizontal-chain bins](reference/k7222-11/native-coupled-algebraic-horizontal-chain.json)
show an unstable connected response: the 5–6 ms bin has 12.504 kV mean EHT,
570.6 Vpp `h_sync`, 112 V13 drive threshold crossings and 31 V18 flyback
crossings instead of about 16 each, with a 1.004 kV V18 collector peak.
The 18–19 ms bin has 12.167 kV EHT and 62.5 Vpp `h_sync`; the 20–21 ms bin
again has 631.4 Vpp, 126 drive crossings and 41 flyback crossings with a
1.007 kV collector peak. These bursts are not a stable TP17 waveform.
The changed partial behavior between two probe-only formulations, together
with the stage sensitivity above, makes this equivalent numerically
unqualified. No connected service score or A5 design point is claimed.

### A2: explicit frame-path zener defaults (2026-11-20)

The [A2 implicit-default audit](reference/k7222-11/a2-implicit-default-audit.json)
now counts 9 affected frame-path instances, down from 12. Page-9 V3's
`REG5_ZENER` model explicitly sets its six previously implicit ngspice 45
diode parameters: TT=0, VJ=1 V, M=0.5, FC=0.5, EG=1.11 eV and XTI=3.
The V4 `Z9_BOUND` and V15 `VERT_Z16` zener models already had a bounded TT
proxy; each now explicitly sets the other five defaults, with the same
nominal values as V3.
The [device-model register](reference/k7222-11/device-model-register.json)
and [class-typical register](reference/k7222-11/class-typical-register.json)
give each an exploratory bound and identify the simulator default as its
nominal source. These are model choices, not original ZC5.1 measurements.
The [ngspice 45 diode tables](https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf)
give the default values and explain their effects on charge storage,
capacitance and temperature response.

The [5 mA V3 class check](reference/k7222-11/regulator5-zener-model-check.json)
still gives 5.125153 V and 12.715 ohm local differential resistance. The
[V4/V15 class check](reference/k7222-11/frame-zener-class-check.json) also
passes. All three DC measurements match their pre-explicitation results;
they do not constrain TT or connected temperature and transient stress.
The other eight audit rows and the zeners' joint-bound sensitivity remain
open; A2 is not complete.

### A5/A6: class-informed T3 overwind screen (2026-11-20)

The [source-informed overwind candidate](reference/k7222-11/t3-coupled-source-overwind-parameters.json)
and [loaded TP17 stage sweep](reference/k7222-11/t3-source-overwind-sweep.json)
separate the high-voltage winding from the older all-0.999-coupled fallback.
A [firsthand ÜHA78 replacement account](https://www.sax.de/~zander/zubehoer/k7222/uha78rep.pdf)
for K7222.25 reports 1,768 turns and about 440 ohm, and says moving the
overwind axially changes EHT. The earlier
[cross-revision comparator](reference/k7222-11/t3-hv-winding-comparator.json)
also records a 2,409-turn original-winding account and a conditional
649–1,298 ohm copper estimate. A separate
[monochrome CRT LOPT study](https://www.worldphaco.com/uploads/RESTORING%20THE%20%20PET%20COMPUTER%209.pdf)
gives a typical primary-to-overwind coupling range 0.5–0.97, a measured
example at 0.92, and roughly 7–8 pF overwind self-capacitance. These are
class comparators, not measurements or factory limits for the .11 unit.
The [class-typical register](reference/k7222-11/class-typical-register.json)
records the candidate's 1,768–2,409 turn, 400–1,300 ohm, 5–20 pF and
0.5–0.97 coupling envelopes; its other winding and core assumptions remain
provisional. The equivalent applies the reduced coupling only to pairs
containing the HV winding. It retains the existing explicit series leakage,
so the combined leakage is still an unqualified model assumption.

With the pinned runtime and the same 4–5 ms prescribed drive, k=0.5 and
k=0.92 abort with a timestep-too-small error. At k=0.95 the completed case
gives 787.9 Vpp on the TP17-mapped `h_sync` node and 11.825 kV final EHT;
at k=0.97 it gives 719.1 Vpp and 12.666 kV. Both swings far exceed the
manual's 64–96 Vpp guideline. The k=0.97 swing moves to 686.2 Vpp at 50 ns
and 1,027.6 Vpp when only the non-driving flux probe is removed at 100 ns.
These results cannot qualify a periodic connected operating point.

The one-factor cases show why the variant cannot simply replace the old
candidate. The old 0.999 coupling/1,000 ohm/15 pF case gives 56.8 Vpp and
10.657 kV. Changing only resistance to 440 ohm aborts; changing only
capacitance to 7.5 pF gives 66.3 Vpp and 12.516 kV; changing only the HV
coupling to 0.97 gives 225.8 Vpp and 10.679 kV. Changing resistance and
capacitance together also aborts. These outcomes identify separate loss,
resonance and coupling sensitivities of the *current equivalent*, not
original-transformer properties. No case jointly establishes TP17 and EHT,
and no connected native-grid run of this variant has been scored. A5 and
A6 remain open.
