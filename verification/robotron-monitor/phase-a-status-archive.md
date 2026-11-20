# Phase A status narrative, archived from PLAN.md

Moved verbatim out of [PLAN.md](PLAN.md) on 2026-11-20, when the plan's status
section was cut to a short table. This is the running status text as it stood
at commit `7fe5169f`. It is a record, not a plan: some counts in it were
already superseded when it was moved, and it repeats itself. Current results
are in [phase-a-evidence.md](phase-a-evidence.md) and the reports under
`reference/k7222-11/`; current status is in the plan.

### Status before the 2026-11-19 agent-review migration

Phase A tooling exists but still demands human marks (A4 above). A1 stands at
227 machine-confirmed and 33 open entries, with no second netlist. A2 has 77
identity-only devices. No stage has been scored. The
connected grid runs under `build/monitor/phase-a/` are startup diagnostics of
an under-damped T3 placeholder and establish nothing about the sustained
state; they are not to be extended.

Next, in order: A4 tool change, A5 design point, A2 device models, A1 second
netlist and open reads, A3 connected waveform scoring, A6 register, then B1. A5 comes
early because it is cheap and its result tells A1 and A2 which parts matter.
Phase C (speed) waits for B8.

### Phase A goal completion blocker (updated 2026-11-20)

**Tracked goal disposition (2026-11-20): completion blocked; implementation
remains active.** Only A4 meets its done condition. The 310 passing tests verify
the current toolchain and saved reports, but Phase A still lacks the independent
source and T3 graph checks (A1), qualified device and class-typical bounds (A2
and A6), a sustained native-grid score (A3), and a frozen tube/yoke design
point (A5). Conditional simulations and bounded substitutes are useful
intermediate evidence, not completion evidence. Finish the checks below, then
document, commit and push their results before closing the tracked goal. The
remaining work can proceed under this plan's bounded `class-typical` and
equivalent-stage fallbacks without human approval or a physical measurement.

| Item | Unmet done condition | Next resolution step |
|---|---|---|
| A1 | The independent page-3/4 and 9/10 netlists, page-18 contrast/service-meter response, and page-16 source-observation check are incomplete. The [T2/L4 seam reread](reference/k7222-11/page3-4-t2-l4-source-read.json) confirms local V18/R36 and T2-primary edges but cannot establish T2 secondary phase/return or the installed E2 setting. T3 return and tap order remain unverified. | Finish the pin-to-pin source comparisons; keep unresolved seam connections as bounded alternatives. |
| A2 | All 64 assembled frame-path devices have provisional register rows, but none passes every parameter-qualification check. The [implicit-default audit](reference/k7222-11/a2-implicit-default-audit.json) finds 12 semiconductor instances in 11 register entries still relying on screened simulator defaults. V18 and V13 now declare high-current roll-off, series resistances, junction shape and temperature assumptions; selected 25 °C class corners pass, but original identities, joint bounds, inductive switching and connected stress remain unqualified. | Make the other defaults explicit, qualify their bounds and connected operating stress, then finish the remaining device checks. |
| A3 | No sustained connected native-grid run has been scored against all required waveform and probe conditions. The refreshed 2 ms startup run ends at 5.143 kV EHT, below the sustained 11–12 kV target. With the revised V18 model, 34 of 36 ideal-TP15 fallback cases complete, and all completed cases exceed the 9 V V18 reverse-base class limit, including the two apparent EHT matches. The prescribed-V13 T2/L4 sweep has no TP15 or EHT match among 24 completed cases; the [eight-case L4-path bound](reference/k7222-11/t2-l4-topology-sensitivity.json) remains conditional. | Resolve or bound the T2 secondary/drive and L4 base path, locate the connected horizontal-sync loss, demonstrate step-size convergence, then score a stable native-grid operating state. |
| A4 | Done. | No remaining Phase A action. |
| A5 | T3's source return/tap graph, winding ratios and polarities are unresolved; the yoke/tube design point remains conditional. | Resolve the source graph or use the plan's labelled bounded equivalent, then verify the full design point. |
| A6 | The 300-entry class-typical register is partial: V18's and V13's 18 active parameter rows each include provisional engineering bounds, and exact B31G22 cold/thermal/emission and G4-dependent cut-off data, T3 parasitics, yoke sensitivity and other frame-path bounds are not qualified. | Complete sourced bounds and the affected stage checks. |

The source reads and diagnostics below narrow these gaps but do not satisfy
their done conditions. This is a blocker to **goal completion**, not to further
implementation.

The current monitor toolchain passes `make test-monitor` with a verified pinned
runtime (310 tests, no skips, Python 3.9.6). This verifies the checks and
saved-report consistency; it does not supply the missing A1, A2, A3, A5 or A6
evidence in the table.

A [bounded native-grid four-field attempt](reference/k7222-11/native-grid-four-field-bounded-attempt.json)
with the current V13/V18 models and conditional manual contrast wiring did
not complete. The [50 ns partial
trace](reference/k7222-11/native-grid-50ns-partial-diagnostic.json) reaches
16.126 ms before a controlled stop; the [200 ns partial
trace](reference/k7222-11/native-grid-200ns-partial-diagnostic.json) reaches
36.435 ms before its 596 s solve budget expires. Their time-weighted EHT
means over 15–16 ms are 7.936 and 9.668 kV, a 21.8% disagreement. The
200 ns trace later rises above 12 kV, but neither run yields a completed
three-field lock or waveform score, and neither resolution is qualified by
the other. Resolve the driver/topology and numerical sensitivity before
using a voltage crossing as A3 or A5 evidence.

A renewed page-3/4 source read separates incoming X9:5 INTENS
(`rx_intens`), V5's IS output to neck X3:2 (`intens`), and the panel HRS wiper
at V1's base (`v1_base`). It supersedes the earlier direct INTENS-to-neck
passthrough claim and its contrast measurements. With those nets corrected,
the page-16 source note identifies IS as active-low (`L = intensiv, H = normal`).
The operating manual (pages 10–11, printed pages 8–9) describes about 35 V
at the cathode for dark video and about 15 V for normal bright video; its
functional Fig. 6 also shows a 15 V contrast reference and V1/V5 control
paths. That simplified figure does not establish the detailed page-3/4 pin
connections, but its cathode target makes the missing steady IS high-state
drive a functional blocker. The isolated neck check reaches only 4.39 V at
the cathode for bright video with an ideal 5 V IS input, so a guessed 5 V
pull-up would not by itself qualify the documented normal-bright level.
[Independent 300 and 600 dpi page-3 reads](reference/k7222-11/page3-r11-r37-source-read.json)
correct V5's lower lead from the
earlier claimed 12P connection to 00: it crosses the 12P and sync lines
without junction dots. The active model already has that return, so this
correction does not recover the IS high state. The page-8 parts list calls V4
`9.1 ZC`, whereas the manual's functional Fig. 6 labels a 15 V reference.
In the [fixed-logic contrast diagnostic](reference/k7222-11/page18-contrast-dc-diagnostic.json),
substituting 15 V for V4's 9.1 V breakdown raises the local reference by
5.85–5.88 V but leaves steady IS and cathode unchanged. This tests the
conflict without treating the simplified figure as a factory V4 specification.
An [isolated IS boundary sweep](reference/k7222-11/page3-4-is-boundary-requirement.json)
shows what a labelled fallback would need: with V5 replaced only for the
diagnostic, 15.7 V at IS yields 15.01 V at the normal-bright cathode and
supplies 28.7 mA; 100 Ω source resistance drops the cathode to 12.66 V.
No source-backed driver or contrast transfer has yet met that boundary.
A [fixed-logic comparison of the manual Fig. 6 terminal assignments](reference/k7222-11/page3-4-manual-topology-comparison.json)
puts the bright cathode at 13.53–16.44 V and moves it by 2.91 V across R2
at one bounded brightness endpoint with the factory-list 9.1 V V4. That
response occurs for raw incoming INTENS low. The provisional T200 model
inverts that input, while the manual discusses a regenerated intensity
signal, so those state numbers cannot be compared directly. The manual
arrangement remains a conditional alternative, not an adopted correction
to the detailed netlist.
The [full-assembly DC comparison](reference/k7222-11/page3-4-connected-contrast-dc.json)
confirms the contrast difference with the remaining ideal-rail circuitry
attached: the detailed wiring holds the bright cathode near 0.328 V with
zero R2 span, while the manual terminal swap gives 13.375–16.329 V and a
2.954 V span for raw incoming INTENS low at brightness position 0. This is
still a conditional DC result with EHT approximately zero; both topologies
retain a 33.671 V dark cathode. It does not qualify a sustained frame, tube
emission or the factory terminal map.
The conditional wiring is now available in the connected runner as
`--contrast-topology manual-fig6-equivalent`; the detailed page-3/4 wiring
remains the default. The deck, run report and grid calibration freeze name
and bind this equivalent, so it cannot silently replace the source export or
change between calibration and native rendering. A [native-input 200 µs
startup screen](reference/k7222-11/page3-4-connected-contrast-transient.json)
reaches its stop time in all three tested solver/topology cases with the
revised V13 model. This qualifies only bounded solver startup, not a
periodic connected A3 score or the factory topology.
An [extended 2 ms startup solve](reference/k7222-11/page3-4-connected-contrast-2ms.json)
also completes for that KLU setting, with final EHT at 5.143 kV;
it covers only about a tenth of one field and does not meet the sustained
11–12 kV target.
The short contrast bench shows effectively no cathode or provisional beam
change across R2's range. The fixed-logic diagnostic shows V1 current changes,
but the modeled IS output stays low and the neck cathode does not respond to R2.
A [bounded IS drive diagnostic](reference/k7222-11/page3-4-is-drive-diagnostic.json)
finds that the nominal transient IS high interval is set by the neck diode's
unqualified junction capacitance: its median is 0.24 V at the lower bound,
4.15 V nominal and 25.22 V at the upper bound, while fixed inputs settle near
0.30 V. That does not establish a qualified logic high. The original IS drive,
tube response and manual service-meter transfer remain open. Without the T3
graph, A5 cannot qualify the winding design point. A2's 64 device rows are provisional, A3 has no sustained
connected native-grid waveform score, and A6's 300 class-typical entries remain
partial. The conditional simulations and source checks below narrow these
gaps but do not satisfy the PLAN's completion criteria. Finish and verify the
remaining A1, A2, A3, A5 and A6 work before marking the tracked goal complete.

**Goal completion blocked reason (as of 2026-11-20):** The independent
page-3/4 and 9/10 source netlists are still partial. The page-3/4 V19/V1
correction and local L1 feed
comparison do not settle transistor C/E assignments or T3's return and tap
order; the L1-to-flyback crossing is a conditional functional choice. The 300
and 600 dpi T3 reads cannot establish the proposed X1:3-to-X2:3 return, so
the eight surviving flyback-sign candidates still depend on an unverified
winding graph. A5 therefore cannot freeze the winding ratios, polarities or
complete design point. A2 now has provisional register rows for all 64
assembled frame-path devices, including T3, but none meets every parameter
qualification check. T3's active turns, resistance and parasitics remain
assumed-bound. Two cross-revision ÜHA78 winding reports give 1,768 replacement
turns and 2,409 reported original turns, both above the active 1,000-turn
hypothesis; neither establishes the K7222.11 factory winding or connection
graph. The active T3 model therefore cannot be frozen from these reports.
A prescribed-drive output-stage sweep adds a loaded T3/yoke comparison, but
its ideal feed/base drive and unverified transformer topology do not give a
connected native-grid A3 score or a qualified A5 design point.
The follow-up [T2/L4 loaded-stage sweep](reference/k7222-11/t2-l4-output-stage-sweep.json)
connects the transcribed V13 collector, T2 and selected E2/L4 base path while
prescribing V13's base pulse. Because the page-3/4 seam does not establish
T2 secondary polarity, the sweep tests both directions. Ten of 24
T2-ratio/L4-bound cases reach 5 ms at the original 0.001 Gear tolerance;
retrying at 0.002 completes all 24. The ten cases solved at both
tolerances agree within 0.70% on final EHT and within 0.58% on collector peak.
None of the 24 completed cases meets the
manual's TP15 36–54 Vpp or EHT 11–12 kV ranges. The nominal off-trace case
gives 24.58 Vpp at TP15 and 9.51 kV final EHT, with EHT still drifting.
This narrows the A3/A5 gap but cannot identify a factory T3 winding or
establish a sustained native-grid stage score: V13 phase, T2/L4 values, E2
setting, T3 return graph and omitted feedback remain conditional.
The same [T2/L4 sweep](reference/k7222-11/t2-l4-output-stage-sweep.json)
now checks V18 emitter-base stress against the [BU508AF class 9 V reverse
rating](https://www.st.com/resource/en/datasheet/bu508af.pdf): 16 of its 24
cases exceed it. A separate [36-case ideal TP15 boundary sweep](reference/k7222-11/tp15-equivalent-output-stage.json)
prescribes 45 Vpp at V13's collector and compares three conditional T3 turn
counts, both T2 polarities and drive phases, and three T2 ratios over
19–20 ms. Thirty-four cases complete; two abort. Two 2,035-turn cases reach
about 11.28 kV EHT and 388 V collector peak, but their V18 base falls
54.0–54.1 V below its emitter. All 34 completed cases exceed the 9 V class
limit; the active level-1 BJT model does not clamp
reverse emitter-base avalanche. This rejects the apparent voltage match as a
viable equivalent driver. Resolve or bound the T2 base path and T3 graph,
then repeat the loaded stress and periodicity checks before adopting a
fallback or freezing A5.
A fresh loaded A3 vertical-stage run with the current device
models passes TP7 at 2.1599 Vpp and gives TP8 a 25.7855 Vpp full swing. The
prior TP8 comparison to 17 Vpp was a source-reading error: the manual's 17 V
arrow ends at the drawn zero line, while its separate 10 V arrow spans the
post-step shoulder to the negative trough. The corrected register tests the
17 V positive crest (14.5803 V measured, within ±25%) and marks the full TP8
numeric reference incomplete until the 10 V arrow is attributed between X2:3
and the distinct R48/V20 bias net.
The run uses synthetic sync, and adjacent late fields still differ by about
0.59 V at the Y1 reset. The isolated,
unloaded driver also misses TP15
(30.02 Vpp versus 45 Vpp ±20%). No connected native-grid A3 score exists. A6
still lacks bounded frame-path values. The isolated L3/R35 branch check now
bounds a provisional L3 inductance ceiling, including R35 tolerance, but
does not establish the original choke value or connected output behavior.
An isolated L4 base-path pulse check also gives conditional operating bounds
for the three stock-matched chokes, but E2 setting and loaded T2 drive are
unverified. A T3 ratio sweep also shows that the active 1000/64-turn ideal
ratio of 15.625 falls below the conditional 28.2–35.9 EHT ratio; the latter
depends on an unverified boost voltage and winding scale. Both tied and open
X1:3/X2:3 returns are now explicit in an isolated functional comparison;
only the tied variant charges its EHT load with the active floating HV cold
node. A six-topology sweep shows that grounding the HV cold end restores
charging even with X1:3/X2:3 open, so the earlier result cannot select the
physical return. The xspice tied case hits a timestep failure. Source
continuity and a connected stage score remain open. Only A4 meets its
done condition. Because the tracked goal requires all six
Phase A items documented, committed and pushed, these partial results cannot
complete it.

This blocks **completion**, not further implementation: no human approval or
hardware measurement is needed. Use the bounded fallbacks above, but keep
unverified connections, generic device aliases and conditional stage results
labelled as such. The remaining done-condition gaps are:

| Item | Evidence still needed for completion |
| --- | --- |
| A1 | The page-16 neck-board pin list and static checks close that schematic review; the separate unvalued measuring-cable inset still needs a bounded transfer and qualified tube response before its service observations can be checked. Finish the independent page 3–4 and 9–10 pin comparisons beyond the checked local C27, V21/divider, page-9 centring and [V11/V12-to-A2 bridge](reference/k7222-11/page9-v12-bridge-comparison.json), including remaining transistor C/E assignments, L1's ambiguous hot-line crossing and page-edge traces; record conditional alternatives for any T3 connections that the scan cannot settle. Page 18 has three classified model-scope gaps. The [page-3/4 seam read](reference/k7222-11/page3-4-intens-seam-source-read.json) corrects the earlier input-to-neck INTENS claim: V5's IS output and V1's HRS bias are separate from incoming INTENS. The [short contrast check](reference/k7222-11/page18-contrast-stage-check.json) shows effectively no modeled cathode or provisional beam response across R2's range; the [DC diagnostic](reference/k7222-11/page18-contrast-dc-diagnostic.json) shows V1 current changing while IS remains low. The [IS drive sweep](reference/k7222-11/page3-4-is-drive-diagnostic.json) shows the apparent transient high is controlled by unqualified neck-diode capacitance, not a stable modeled high-state drive. The operating manual's normal-bright cathode target is about 15 V; the isolated neck reaches 4.39 V with ideal 5 V IS, so resolve the original IS bias and qualify the tube/service-meter response before judging contrast function. C30 placement/population and the installed E1–E4 pair are not identified. |
| A2 | Qualify every frame-path device model and its bounds. All 64 instances have provisional register rows, including T3, but none closes every parameter check. V21 has explicit bounds for all twelve SPICE diode parameters, passes bounded Rectron/Semtech class fixtures, and has a 24-case one-at-a-time connected-stage sensitivity sweep. The slow TT endpoint moves final EHT by 4.4%; nominal late-window reverse voltage reaches 11.94 kV, near the 12 kV comparator rating. V21 identity, joint corners and sustained stage stress remain open. The two cross-revision ÜHA78 winding reports challenge T3's active 1,000-turn hypothesis without proving the K7222.11 construction; its other turns, parasitics and connected sensitivity remain unqualified. Original values and connected sensitivity also remain open for the page-9 centring chokes, T1, T2's primary, horizontal-feed L1, output L3 and three L4 chokes. |
| A3 | All 17 manual waveform shape descriptors are registered. TP8's 17 V crest-to-zero check passes in the synthetic-sync loaded bench; a dual-node probe shows the separate 10 V arrow remains sensitive to reset masking and node attribution. The prescribed-V13 T2/L4 loaded-stage sweep misses TP15 and EHT in all 24 cases across both T2 polarities after a bounded solver retry. Score connected stages with stable feature definitions, the required loaded probes, native grid stimulus and recorded trims. |
| A5 | A conditional vertical current/voltage calculation exists. The loaded T2/L4 sweep does not establish a periodic EHT or identify the factory T3 winding. Optional C30 population changes the inferred 16 µs effective resonance inductance from 2.36 to 2.59 mH and loaded final EHT by 2.49–2.53% in the refreshed V21 model; its source population is still unverified. Resolve or explicitly bound the T3 tap/return graph, freeze the winding ratios and polarities, and qualify the complete tube/yoke design point. |
| A6 | Complete cited bounds for the remaining tube, T3, yoke, measuring cable and other frame-path model values; the current register has 300 partial entries, including three explicitly assumed-bound T3 rows, 45 explicit diode-default rows across nine register entries, 18 provisional small-signal BJT-default rows across two families, 18 provisional V18 BJT parameter rows and 11 additional explicit V13 BJT parameter rows. The [Tungsram M31-120 heater check](reference/k7222-11/tube-heater-class-check.json) supports the active 11 V/68 mA class operating point through the printed 15 Ω R22. The [cut-off class check](reference/k7222-11/tube-cutoff-class-check.json) moves the provisional grid factor into the catalog/manual overlap, but the installed B31G22 gun, G4 effect, cold resistance, thermal law and emission remain unqualified. The page-16 meter-cable capacitance, shunts and DVM loading remain unbounded. The older RFT B30G1 6.3 V/0.47 A comparator remains excluded: it would require 13.35 V ahead of R22, above the modeled 12 V rail. |

The [local page-9 oscillator comparison](reference/k7222-11/page9-oscillator-comparison.json)
now matches the source image's V5/V11 collector, base and emitter branches,
R31/R32 collector loads, R25 feedback, C13 timing link and R22/R23/R24
emitter trim/return chain. A V5 collector/emitter reversal fails the check.
This read followed earlier model exposure and covers only this local network;
the independent complete page-9 comparison in A1 remains open.

The [page-16 measuring-cable transfer bound](reference/k7222-11/meter-cable-transfer-bound.json)
shows that the inset's literal common-return, series-capacitor interpretation
has zero steady DC gain even with an ideal source. A Fluke meter class
comparison gives different 100 mV input impedances for DC (10 MΩ) and AC
(1 MΩ), and the conditional 50 Hz and 16 kHz gains vary strongly with the
unprinted series capacitance. The Robotron instruction specifies only a
digital voltmeter; it does not state its AC/DC mode, input circuit or
integration window. The inset also omits the lower-terminal connection and
both shunt values. These limits rule out using direct X3 DC voltage as the
0.1/3.6 mV service observation; they do not assign a cable value or close A6.

The [A2 implicit-default inventory](reference/k7222-11/a2-implicit-default-audit.json)
now screens every registered frame-path discrete semiconductor against a
specified gain, switching, capacitance, breakdown and temperature parameter
set. The vertical 1AE15 family's five formerly implicit parameters are now
explicit and provisionally bounded in the model and registers, reducing the
open set from 51 to 41 semiconductor instances and from 24 to 23 register
entries. Other diode models still leave junction-potential, grading and
temperature terms implicit; BJT models leave high-current gain rolloff and
junction-capacitance shape implicit. The screen does not qualify those
defaults or cover internal IC
subcircuits. A2 remains open despite provisional model names and register
rows for all 64 frame-path devices.

For the ten vertical-stage 1AE15 instances, `VJ`, `M`, `FC`, `EG` and `XTI`
are now explicit at the former ngspice defaults. The [manufacturer 1N4148W
SPICE comparator](https://www.diodes.com/spice/download/1589/1N4148W.spice.txt)
provides only the `M=0.333` alternative; other new ranges are labelled
engineering assumptions, not original-part limits. The [isolated diode
check](reference/k7222-11/vertical-diode-model-check.json) still passes and
the [24-case one-at-a-time stage sweep](reference/k7222-11/vertical-diode-stage-sensitivity.json)
completes. The largest yoke-span change across all twelve bounded parameters
is 5.50%; the five newly explicit parameters change it by less than 0.001%
in this fixed-temperature bench. `EG` and `XTI` need a temperature sweep,
and original-part identity, joint bounds and native connected stress remain
unqualified.

The shared connected `1AD50_BOUND` alias used by eight 1AD50 and four input/sync
1AE15 instances now declares those same five parameters through the bounded
neck profile; its two fixed vertical-stage copies also state the defaults.
This removes both families from the screened-default worklist, leaving 29
instances in 21 entries. The [1AD50 class check](reference/k7222-11/neck-diode-model-check.json)
and refreshed page-16 and IS-drive diagnostics retain their measured values.
The `M=0.333` bound is a comparable manufacturer's SPICE value; other spreads
are assumptions. Original-device ratings, temperature response, joint bounds
and native connected stress remain open for A2.

The horizontal `HOR_D`, `HOR_RECT`, `HOR_Z6` and `HOR_HV_RECT` aliases now
declare the same five diode defaults. They cover eight more frame-path
instances across six register entries, leaving 21 affected instances in 15
entries in the A2 audit. The [V21 connected sensitivity](reference/k7222-11/v21-connected-sensitivity.json)
now completes 24 one-at-a-time bound cases; the added junction and capacitance
spreads change final EHT by at most 0.17% in that conditional late-window
bench, while `EG` and `XTI` have no effect at its fixed nominal temperature.
These assumed spreads still need original-part evidence, joint corners and
sustained native-grid stress before A2 can close.

All five printed `1SA20C` instances and both `1SC60A` instances now use
separate [BC546B-class NPN model aliases](circuits/k7222-11-small-transistor-models.cir)
with cited parameter bounds in the A2 and A6 registers. The
[isolated class check](reference/k7222-11/small-transistor-class-check.json)
passes nominal gain, saturation and transition-frequency comparisons against
the [onsemi BC546B data sheet](https://www.onsemi.com/download/data-sheet/pdf/bc546-d.pdf).
This is a class comparator, not a claim that either printed type is a BC546B.
Nine formerly implicit screened BJT parameters are now explicit per alias:
the [ngspice manual's BC546B example](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf)
provides provisional `IKF`, `RB` and junction-shape values, while `EG`, `XTI`
and `FC` state the previous defaults. The isolated check now measures gain
268.7, saturation 0.097 V and a 181.7 MHz transition-frequency proxy. The
A2 default audit falls to 14 instances in 13 entries, and A6 grows to 272
partial rows. The revised nominal IS-drive diagnostic reaches 4.15 V in its
transient high interval; page-18 contrast still has negligible modeled cathode
response. These changes do not establish an original transistor fit.
Original ratings, every printed-arrow read, connected current/voltage/thermal
stress, joint bounds and optional BJT defaults beyond the screened set remain
unqualified. T3 on board
012-6921 now has a provisional register row, with assumed-bound active values
and unresolved winding continuity. Both
012-6931 L1/L2 centring chokes now have
bounded provisional RL models in the source-addressed
[page-9 bridge sheet](circuits/k7222-11-centering.kicad_sch). The
[independent source comparison](reference/k7222-11/page9-centering-comparison.json)
matches nine local component terminals; the
[isolated bridge check](reference/k7222-11/centering-bridge-check.json)
passes both conditional link polarities. The installed E1–E4 pair, original
choke construction and connected-stage effect remain open. The earlier
midpoint-neutral current-source equivalent has been replaced by this branch.

T1 now has a conditional
[half-winding design check](reference/k7222-11/horizontal-t1-design.json).
Documented C16 and the 16 kHz native line period give a 0.989 mH ideal LC
scale; the source-connected autonomous oscillator gives 15.89 kHz at the
1.45 mH per-half starting value already used by the ideal-rail tune. The
former 0.9 mH profile default instead gives 19.91 kHz, outside the printed
14.338–16.338 kHz generator range. The profile default and bounded T1
register row now agree with the live starting value. This is conditional on
the provisional oscillator transistor loading and is not a T1 measurement
or Phase B calibration. T1 and T2 now have independent coupling parameters;
the regenerated T1 sweep varies only its own coupling.

T2 now has a [scoped primary source read](reference/k7222-11/page3-t2-primary-source-read.json)
and [nine-case isolated check](reference/k7222-11/horizontal-t2-design.json).
R23=62 Ω and 16 kHz give a 3.08 mH minimum primary inductance for reactance
at least five times R23 and a 6.2 Ω resistance budget for at most 10% added
series drop. The provisional 5 mH/2 Ω model meets those operating budgets,
but the nominal isolated V13 collector swing is only 30.02 Vpp against TP15's
36–54 Vpp manual range. V18 base/output loading is absent from this bench;
T2's secondary map, ratio, loss and coupling remain unqualified. This does
not close A3 or identify the factory transformer.

Horizontal-feed L1 now has a conditional
[page-4 source comparison](reference/k7222-11/page4-l1-comparison.json) and
[isolated design check](reference/k7222-11/horizontal-l1-design.json).
Documented R42=6.8 Ω and C22=220 µF with the 16 kHz line rate give an
11.2 µH minimum for an LC corner below one fifth of line frequency and a
0.68 Ω winding-resistance budget for no more than 10% additional DC drop
relative to R42. The provisional 100 µH/0.5 Ω model passes the isolated
check; its nominal 16 kHz feed ratio is 0.365%. The source crossing with the
approximately 400 V flyback-hot line remains visually ambiguous. Keeping it
separate avoids an implied 52.8 A R42 peak, but does not prove the printed
connection. Factory L1 values, C22 ESR, core saturation and connected-stage
sensitivity remain unqualified.

The [page-4 V20 source read](reference/k7222-11/page4-v20-source-read.json)
and [page-3 R11/R37 read](reference/k7222-11/page3-r11-r37-source-read.json)
now distinguish V19 on page 3 from V1 on page 4. The source routes `12P` to
R38 left/R39 upper, V19's upper lead to R39 lower and parallel R40/C34 left,
and the lower return to V6/V19/V20. The assembled branch includes V19 and
V20, with its R38/R39/R40/C34 feeds corrected. Separately, page-4 V1 has its
R3/upper lead on `35P`, base fed by R1/R3, and lower lead on the KRS contrast
line. R11.2 runs from `12P` to `sync_feed`, R11.1 from `sync_feed` to
`sync_c`, C33 bridges those nodes, and R37 biases `sync_c` from `12P`.
An [isolated DC polarity comparison](reference/k7222-11/page3-4-transistor-polarity-functional-check.json)
supports the current lower-emitter NPN assignment for V6/V19/V20: its
`h_feedback` output swings 12.0 to 0.044 V under two input states, whereas
reversed NPN and PNP alternatives swing less than 0.6 V. The separate V1
check gives a 21.19–24.80 V KRS adjustment over the R4 range; the PNP
alternative stays near 35 V, and reversed NPN enters unqualified reverse
base-emitter bias. This is functional support for four local C/E assignments,
not a printed-arrow read or an original-device fit. The C/E assignments and
class transistor models remain provisional;
original device parameters, connected stress, the full page-3/4 comparison
and a connected contrast score remain open.

The former V10 lower-return and V1-to-`00` mismatches were cropped-label
errors: the page-3 right transistor is V19; V10 is in the upper oscillator
and V1 is on page 4. V10's separate `h_reactemit` network and V1's KRS lower
lead match the source reads. The fresh export matches the corrected local
branches, while the complete page-3/4 graph, transistor polarity and T3
connections still need source review, not a human reading or physical
measurement.

These are independent completion failures, not just one T3 issue. The
[device-model coverage report](reference/k7222-11/device-model-coverage.json)
records the A2 gap, and the [design point](reference/k7222-11/design-point.json)
explicitly remains partial rather than a calibration freeze. The
[Phase A evidence log](phase-a-evidence.md) records conditional stage results,
not a completed connected A3 score. Resolving the T3 connection review would
unblock the A5 calculation, but it would not by itself close A2, A3 or A6.
The tracked goal can be marked complete only after each row above has its
required evidence and the final results are documented, committed and pushed.

The former `LM709_FAMILY` P09A substitute failed a basic isolated DC follower:
the [reproducible check](reference/k7222-11/lm709-dc-follower-check.json) gives
12.54258 V output for a +1 V input at ±15 V and 2 kΩ load. It has been
replaced in the live assembly by the labelled `P09A_EQUIV` fallback, keeping
the source compensation connections. The
[isolated class check](reference/k7222-11/p09a-equivalent-class-check.json)
passes eight nominal LM709C-class response and rail-current checks, with
provisional parameter bounds in A2/A6. The printed P09A identity is still
unknown. The [connected diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic-p09a-equivalent.json)
passes loaded TP7 at 2.159 Vpp. Its archived TP8 comparison treated 25.767
Vpp as a failure against 17 Vpp; that total-swing target was misread from the
manual figure. Y1 is still not field-periodic. A3 and the remaining
A2 qualification therefore stay open; the failed transistor proxy is kept
only as historical evidence.

This blocks declaring the tracked goal complete; it does not require human
review, hardware or permission. Another independent source read may resolve
T3; otherwise its possible connection graphs must remain explicit, conditional
alternatives while the stage is tested. The bounded `class-typical` fallback
applies to unprinted electrical parameters, not proof of wiring. Keep the
unverified graph and sign candidates labelled conditional until the remaining
Phase A evidence is recorded. The detailed evidence and route to completion
follow.

The latest page-4 review at 300 and 600 dpi confirms only the external T3
drive path already checked by the
[flyback-sign comparison](reference/k7222-11/t3-flyback-sign-filter.json):
X2:7 meets V18's collector and V17's cathode, V18's emitter and V17's anode
return to ground, and X2:4 is the other drive-winding endpoint. That comparison
does not independently establish the internal tap order or the X1:3-to-X2:3
return. The [winding graph](reference/k7222-11/t3-winding-hypothesis.json)
therefore remains a hypothesis; its eight surviving sign candidates cannot
serve as evidence that A1 or A5 is complete. The next source review must settle
or explicitly bound those connections before the T3 design point can be frozen.
The [return-variant check](reference/k7222-11/t3-return-variants.json) now
records two external X1:3/X2:3 graphs. A fresh KiCad export confirms the
current tied model. With a 1 V isolated collector pulse, V21-class diode,
1 nF EHT load and the current magnetic parameters, all eight sign-compatible
flux candidates charge the tied EHT node to 20.30–21.90 V after five pulses;
the open alternative reaches only 0.0044–0.0045 V under the current
floating-cold hypothesis. The page-4 scan has not proved historical
continuity. The
[cold-return matrix](reference/k7222-11/t3-cold-return-matrix.json)
also tests grounding X1:16, motivated by firsthand K7222 repair accounts whose
revision is unspecified. Across the same eight candidates, an open X1:3/X2:3
return then charges the isolated EHT load to about 21.10 V after five pulses.
The apparent tied-return requirement is therefore conditional on the active
HV cold-end connection, which also lacks independent source closure. The
xspice tied bench aborts near 6 µs at a tiny timestep, so no second magnetic
backend corroborates this loaded comparison.
Neither result is a connected 11–12 kV prediction or an A1 source closure.

The decisive technical uncertainty within A1 is the T3 winding topology.
Manual page 19 names
X1:1 and X1:16 as the high-voltage winding terminals; schematic page 4 puts
V21 between X1:1 and the X1:2 EHT output. The model now uses those terminal
roles, with X1:2 outside the magnetic graph. The provisional X1:3-to-X2:3
return and other tap continuity and polarity still lack an independent
pin-to-pin source check. A page-4 functional read now matches T3 X2:7 to
V18's collector and V17's cathode. An isolated positive collector pulse
selects eight of sixteen relative-polarity candidates in both magnetic
backends. This screens only the HV sign within the current unverified tap
graph. The A5 winding ratios, remaining polarities and candidate list
therefore cannot be frozen. The isolated startup
trials in `phase-a-evidence.md` neither resolve the remaining pin map nor
demonstrate the documented 11–12 kV sustained EHT.
The [isolated HV-ratio sweep](reference/k7222-11/t3-hv-ratio-sweep.json)
compares the active 1000-turn HV winding against the conditional A5 EHT
ratio. With the present assumed 64 total drive turns, the ideal active
ratio is 15.625, below the 28.2–35.9 ratio calculated from the candidate
60–70 V boost and 11–12 kV target. Candidate HV counts of 1808–2300
turns bracket that ideal ratio, but remain conditional on the unmeasured
drive winding and boost case. A 1 V open-circuit pulse shows the current
model's 5–15 µs mean HV ratio is 14.62, also below that target; the
2035-turn candidate's corresponding mean is 29.97, below its 31.80 ideal
ratio. No active T3
parameter is changed by this diagnostic; loaded EHT and the return/tap
graph must be established before a winding freeze.
An independent [K7222 repairer comparator](reference/k7222-11/t3-collector-eht-comparator.json)
reports 370–420 V collector pulses and 11.5–12.5 kV EHT, giving an effective
EHT-to-collector amplitude range of 27.38–33.78. The post does not identify a
K7222.11 board or document its measurement method. Its range overlaps the
conditional design-point ratio and is well above the active 15.625 ideal
turns ratio, but rectifier loading and collector baseline prevent treating
that effective voltage ratio as measured turns. It supplies a useful
cross-revision operating comparator for the connected candidate sweep, not a
factory winding specification.
The [prescribed-drive output-stage sweep](reference/k7222-11/t3-output-stage-sweep.json)
now connects the source-transcribed V18/T3, damper, boost, yoke and EHT-load
branches while holding the 41 V feed and base pulse ideal. With the optional
passive AC-loss transformer hypothesis, 30 of 32 runs finish over eight
sign-compatible candidates and four HV turn counts; two hit timestep
failures. None of the completed 4–5 ms windows jointly reaches the repairer
collector and EHT ranges; none reaches even the manual's 11–12 kV EHT range.
The active no-AC-loss baseline aborts. In the representative 1,768-turn case,
the 1 nF load gives 383 V collector peak,
9.62 kV EHT and a 15.59 µs flyback pulse; sweeping the declared 0.25–4 nF
tube-capacitance range gives 8.46–9.86 kV EHT. This narrows the next parameter
and topology search, but the ideal base/feed drive, 65 V initial boost,
omitted loads and nonperiodic EHT prevent an A3/A5 score or a winding freeze.
The [T3 winding comparator](reference/k7222-11/t3-hv-winding-comparator.json)
adds two firsthand, cross-revision ÜHA78 reports: a K7222.25 repair uses a
1,768-turn replacement winding with about 440 Ω measured resistance, while a
separate repair account reports 2,409 turns of 0.08 mm wire for an original
ÜHA78 HV winding. A broad copper-geometry estimate for the latter is
649–1,298 Ω at 20 °C, so the active 1 kΩ resistance is plausible, while its
1,000-turn count is below both reports. The isolated loaded model changes
materially across these turn counts. Neither report identifies the K7222.11
factory winding map, and the K7222.25 repair changes the cold-end connection.
The A2 row is therefore an explicit provisional gap record, not a qualified
T3 model or evidence that A5 is complete. Extend the stage comparison to the
source-connected drive and feedback loads, and retain explicit return/tap
alternatives until the independent page-4 read settles them.
The page-4 HV source edges now have a fresh KiCad-export comparison: T3 X1:1
meets V21's anode, V21's cathode reaches EHT, and X1:16 remains a separate
winding terminal. This partial check leaves the return and winding questions
above open.

The immediate route to resolution is A1's independent pin-to-pin transcription
of schematic pages 3–4 and 9–10, plus the remaining panel-control interconnect
checks on page 18, diffed against the KiCad exports and re-read where they differ.
Page 16 already has a complete pin comparison; its source-observation check
remains open. The source readings must settle the remaining T3 connector and
return paths before the T3 portion of A5 can be frozen. Where the
documents cannot settle a parameter, the A1/A5 bounded `class-typical` route
applies; the plan does not require a human or a physical measurement.
A source-first page-9 read now matches all 16 pins in the seven-part 5.1 V
reference branch, including the zener, transistor and capacitor polarities.
A separate source-first read matches all eight endpoints of R3/C2/C1/R20 in
the vertical sync input. Its enlarged crossing review confirms that SYNC does
not join the 0 V return bus. The remaining page-9 circuit and page 10 still
lack a complete second netlist.
A page-10 driver-and-output read now matches 26 terminals of
V18/V19/V20/V21/V26/V27/V28/R27/R29/R48 and X2 in a fresh KiCad export. It
checks all six V27/V28 terminals, all three bias-diode directions, R48's feed
to the V20/V21 junction, and the R29 shunt/R27 sense return between Y1, Y2
and 0 V. Printed arrows confirm the modeled upper NPN/lower PNP assignment;
the contradictory handwritten BD labels remain unverified. The rest of page
10 and its connected-stage function check are still open. A separate A3 read
now matches all eight active physical amplifier pins and seven C26/C27/R54/R48
compensation/output terminals in a fresh KiCad export. The functional symbol's
1–8 pin numbering is explicitly mapped to physical 3, 4, 5, 6, 9, 10, 11,
12. This closes that local connection check, not P09A model qualification or
the remaining page-10 netlist.
An additional page-10 feedback read matches ten scoped terminals of
A3/R43/R45/R46/R47/R27/X2 in the
[fresh comparison](reference/k7222-11/page10-feedback-comparison.json).
The page-14 parts list confirms the three checked feedback resistances.
R44 is already the 160 Ω ramp-output divider resistor on page 9, not a
second page-10 feedback part. The rest of the page-10 input, supply and
feedback paths remain outside this partial check; the TP8 failure is still
unexplained.
The page-18 source transcription now has all 18 labelled board-cable pairs
compared at both physical connector pins in fresh KiCad exports. Fifteen signal
nets occur on both corresponding functional board models; three have model-scope
gaps after the vertical-board centring chokes connected X1/X2. Vertical-board X2's six pins, four yoke terminal labels and assembled
winding endpoints match a separate page-18 comparison. A source-first panel
read now matches R1's represented topology and R2's corrected two-wire
rheostat between the board R4 left/wiper node and V1 emitter. All six main-board
X1 physical pins match a fresh KiCad export. The three gaps are the excluded
vertical-board converter 41P/SYNCH paths and the held-thermal-state 10.7P
heater branch. A [scoped page-3/4 source read](reference/k7222-11/page3-4-intens-seam-source-read.json)
separates incoming X9:5 INTENS, V5's IS output to neck X3:2, and the HRS
wiper at V1's base. The earlier direct INTENS-to-neck passthrough and its
measured contrast effect were erroneous. With these nets corrected, the short
powered input/neck bench has effectively no cathode or provisional held-warm
beam response across R2's range. The IS high-state bias, service-meter path
and sustained native-grid response remain unqualified, so contrast function remains unresolved;
A1 page 18 therefore stays open.
An independent page-16 neck-board read now matches all 39 component pins and
six diode directions in a fresh KiCad export. Three audit-only connector
symbols now expose all 17 physical pins in that export, and every pin matches
the source read. The page-16 source graph has DC routes and an isolated bench
shows plausible transistor switching and cathode response. The A1 neck-board
schematic mark is closed; its separate service-observation check still awaits
CRT emission and
uses a fixed beam load. The page-16 measuring-cable inset contains an unvalued
series capacitor and shunt elements; a direct X3 DC voltage cannot reproduce
the cable-coupled 0.1 mV rise and 3.6 mV setup readings.
The current audit flags 26 frame-path part entries; all 26 now have agent
readings or bounded class-typical decisions. T3's two page-4 reads establish
its line-transformer identity, not its turns, internal winding connections or
polarity. V18, V21, V27 and V28 now have bounded `class-typical` candidates,
while their full connection reviews remain open on pages 4 and 10; the local
driver, bias-diode and output-pair pin check above is complete.
Seven converter-only entries are
outside the A1 gate.

Other required close-out work is also missing. The A2 coverage report counts
64 frame-path device instances in 30 printed-type families. All 64 have
provisional device-model register coverage, now including T3, both page-9
centring chokes, T1, T2's primary, horizontal-feed L1, output L3 and the three
L4 sections. V19 on 012-6921 and L1/L2 on 012-6931
are now assembled. None of the 64 instances yet closes all A2 parameter
checks. The [isolated L3/R35 check](reference/k7222-11/horizontal-l3-design.json)
uses the documented 82 Ω ±5% shunt and 16 µs retrace. Its provisional
95 µH ceiling keeps the shunt current below 25% of L3 current at the
31.25 kHz retrace half-cycle frequency, even with R35 at its low tolerance
endpoint. The 20 µH nominal and 1 µH lower bound are exploratory. The page-4
branch has no complete independent source comparison; original L3 values and
connected T3/yoke sensitivity remain open. The V18 horizontal-output model now
has a [conditional L4 base-path check](reference/k7222-11/horizontal-l4-design.json):
two parallel 50 µH/1 Ω chokes reach 0.533 A within one third of the
46.5 µs trace if 1 V is available directly across the branch. The assumed E2
setting and loaded T2
secondary response remain unverified; the third L4 section is bridged in
the selected configuration. The V18 model passes a BU508AF-class DC gain and
saturation proxy; its inductive switching, parameter bounds and connected-stage
stress remain unchecked. A separate current-fed turn-off
diagnostic shows that its transfer interval is sensitive to model TF and TR;
it does not reproduce the data-sheet inductive timing test.
The page-9 V3 reference zener now passes a BZX84-C5V1-class 5 mA voltage and
differential-resistance comparison. Its original ZC5.1 rating, omitted TT
parameter and connected-stage stress remain open.
The three other active frame-path zeners now pass corresponding BZX84-C6V2,
C9V1 and C16 class comparisons at 5 mA. Their CJO and TT model parameters
are explicit and bounded, but historical identities, the TT range and
connected-stage sensitivity are not qualified.
The horizontal 1AL25 signal diodes and four 1YL1 flyback rectifiers now have
explicit breakdown models and nominal class comparisons for forward voltage,
reverse leakage, capacitance and recovery. The three printed 1YL1 suffixes
still share one provisional model; their factory ratings and connected-stage
stress are not established.
The V13 horizontal-driver model now passes broad SF128-family DC gain and
saturation comparisons and a 15 MHz transition-frequency proxy. The printed
SF1280 suffix is unresolved; inductive storage/fall, other simulator defaults
and connected-stage stress are still unqualified.
V10 now has its own SC237E group-E model instead of sharing V12's lower-gain
`HOR_N`. At the historical bias points, its gain, typical saturation and
transition-frequency proxies agree with the group-E data; V12's `HOR_N`
passes broad SF126-family gain, saturation and frequency checks. The second
SF1260 instance in the 5.1 V reference branch uses a separate `REG5_NPN`
alias; its provisional family gain, saturation and frequency checks now pass.
The printed suffix, connected-stage stress, joint parameter bounds and
implicit simulator defaults remain open for these transistors.
The two original-type KFY18 PNP instances now have a shared bounded model
entry. Its isolated gain, 150 mA saturation, 50 mA frequency and reverse-bias
junction-capacitance checks match the
[1987 Tesla catalog](https://teslakatalog.cz/download/tesla_katalog_2_1987_bw.pdf)
test points. The
connected-stage current, voltage and thermal stress, joint bounds and implicit
SPICE defaults remain unqualified.
Vertical V18 now has a separate `SF127C_N` model rather than sharing the
unidentified `1SA20C` oscillator alias. Its isolated group-C gain, saturation
and frequency proxies pass the historical SF127 family limits; the rest of
the page-10 pin review, connected stress, joint bounds and simulator defaults
remain open.
The active MAA723 ramp-amplifier proxy now has a provisional register entry
linked to the Robotron `MAA723H`/`uA723` family comparison and TI's 723-family
limits. Its former 200 µA drive ceiling let a 5 V class fixture collapse to
2.31 V at a 50 mA load. Bounded error-amplifier drive now gives 4.988 V at
50 mA, 4.985 V at 150 mA, 7.15 V reference and 2.30 mA standby in the
[isolated check](reference/k7222-11/maa723-model-check.json). The printed type
lacks the cross-reference's H suffix; internal device
defaults, dynamic response, current limiting, connected-stage stress and joint
bounds remain unqualified. The earlier TP7/TP8 diagnostic below predates this
model revision; the refreshed diagnostic is described after it.
The waveform scorer now supports separately loaded SPICE solves for the bounded
EO 203 probe equivalent and records an explicit grid stimulus choice. The
[earlier vertical-stage diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic.json)
records trims and separate TP7/TP8 probe solves at the native 19.5 ms field
period. The archived scorer marked TP8's loaded 18.31 Vpp as passing a 17 Vpp
target now known to be misread; both shapes pass;
TP7's loaded 1.74 Vpp fails its 2.5 V guideline. The stimulus is a synthetic
field pulse, and a 2.29 V Y1 reset difference remains between late adjacent
fields. This is not a grid-stimulus or sustained connected-stage A3 score;
the remaining points and complete A3 comparison stay open.
The [refreshed loaded diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic-maa723.json)
uses the revised MAA723 proxy with the same nominal trims and synthetic
19.5 ms field pulse. TP7 rises to 1.8718 Vpp, just below the 1.875 Vpp lower
bound of the manual's ±25% guideline; the archived 18.7763 Vpp TP8 pass used
the same misread full-swing target. Both shapes
pass. Adjacent late fields still differ by 2.61 V at Y1 reset (13.9% of its
swing), so periodic steady state is not established. These are conditional
stage diagnostics, not a native-grid A3 score.
That diagnostic still used the failed `LM709_FAMILY` P09A proxy. With the
labelled `P09A_EQUIV` fallback, the latest
[pre-class-model loaded diagnostic](reference/k7222-11/vertical-a3-loaded-stage-diagnostic-p09a-equivalent.json)
at the native 19.5 ms period gives TP7 2.1594 Vpp (pass) and TP8 25.7674 Vpp
(fail against the former 17 Vpp target); both shapes pass. Y1's late-field
reset differs by
0.5972 V, or 2.32% of its 25.768 V swing. This remains synthetic-sync and
nonperiodic, not the complete connected grid-stimulus A3 comparison.
A fresh rerun with the current small-transistor models and nominal 11 kΩ
height trim, scored over 0.234–0.2535 s with separate EO 203-equivalent
circuit-loaded probes, gives TP7 2.1599 Vpp and TP8 25.7855 Vpp; both
registered shape checks pass. The adjacent Y1 reset differs by about 0.59 V,
and the stimulus is still synthetic. The
[TP8 source reread](reference/k7222-11/tp8-waveform-source-read.json) shows
that 17 V is crest-to-zero, not full peak-to-peak. The
[source-corrected loaded score](reference/k7222-11/vertical-a3-tp8-source-corrected-diagnostic.json)
measures a 14.5803 V crest, inside the 17 V ±25% guideline. The 10 V
shoulder-to-trough arrow has unresolved node attribution, so TP8 remains
`reference-incomplete` rather than a full-swing pass or failure.
The [dual-node loaded diagnostic](reference/k7222-11/tp8-dual-node-loaded-diagnostic.json)
now records X2:3 and the distinct R48/V20 junction in separate probe solves.
Their full traces differ by at most 0.768 V in the final field. An exploratory
long-descent feature gives 6.83 V at X2:3 and 7.75 V at R48/V20 with 128 phase
bins, but the R48/V20 value falls to 7.41 V with 256 bins, crossing the 7.5 V
lower guideline. The short reset undershoot makes this feature definition
resolution-sensitive; these numbers neither settle the annotation's node nor
qualify its 10 V comparison.
An independent [long-line fit sensitivity check](reference/k7222-11/tp8-ramp-feature-sensitivity.json)
now excludes that spike reproducibly: synthetic reset-spike tests recover a
known 10 V ramp across 64–256 bins. In the loaded stage, R48/V20's fitted
excursion is 7.59–7.74 V with a 2% fit-error allowance, but only 6.80–7.11 V
or undefined with 1%. The manual does not prescribe this fit threshold, so
the result remains diagnostic and TP8 stays `reference-incomplete`.
The class-typical register collects
300 cited bounded entries, but tube cold resistance, thermal and emission
parameters, T3 parasitics, yoke
sensitivity and other frame-path model values still lack sourced bounds (A6).
All three A4 controls are now bound in the ideal-rail
assembly: horizontal-centering R4 uses the conditional page-9 bridge,
R5 uses a declared rail equivalent, and external R1 uses the
page-3/4/18 pot connections. Their effects have not been measured on a grid;
the A1 independent netlist check may revise provisional connections.
The partial A5 calculation also exposes a narrow tube/yoke geometry constraint:
the default 40 mm yoke field clips before the documented half-width, while a
12 mm internal neck aperture exceeds a B31-G family outline's outside radius.
A 34.7 mm active-field trial narrowly reaches the width in the reduced model,
but the inner tube clearance and yoke extent remain unverified. These are
recorded in `phase-a-evidence.md`; the connected grid startup traces do not
establish a sustained-state solution.
A separate reduced-geometry vertical calculation now finds about 0.281 A peak
current for the documented 145 mm picture height at 11.5 kV, with an ideal
linear-ramp yoke voltage swing of about 13.7 V. Its height-only range is
0.254–0.307 A at the manual's ±15 mm tolerance. The current is conditional on
the assumed 40 mm field, 10 mm internal neck aperture and 20 mH/10 Ω yoke;
TP7/TP8 are separate terminal-voltage guidelines and do not measure that
differential waveform. The source-checked 3.9 Ω R27 converts the TP7 2.5 Vpp
guideline to 0.641 App of total sense current (0.471–0.818 App with TP7 and
R27 tolerances). R29 and the feedback network also return through R27, so
this is not a direct yoke-current target. The calculation advances A5 but
cannot freeze it.

To clear the completion blocker, finish the independent pin-to-pin comparison
of pages 3–4, 9–10 and 18, close page 16's source-observation check, resolve
the T3 terminal and return-path differences from source evidence, and record
bounded assumptions where the scan cannot settle winding parameters.
Then complete and verify the A2 device
models, A3 probe/stimulus scoring, A5 design point, and A6 bounded register
against their done conditions above. This requires more implementation and
source review, not an external dependency or a human measurement; the ground
rule and fallbacks above still apply.
