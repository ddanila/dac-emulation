# K7222 reference evidence

The internet search found a substantially more complete **K7222.11/.21** set.
This is a documented reference candidate, not identification of the museum's
monitor. Source bytes are identified in `sources.json`; page numbers below are
one-based PDF pages, not the printed page numbering. No values from these boards
are silently applied to the separate experimental fixture.

## Primary scans

| Source | Useful pages | Scope |
| --- | --- | --- |
| [K7222.11/.21 schematic set](https://www.tiffe.de/Robotron/Monitore/Monitore_2/K7222.11_.21_sch.pdf) | 3–4 schematic, 6–8 parts | Horizontal/video board 012-6921; parts document 1.12.516921.8/01 |
| Same set | 9–10 schematic, 12–15 parts | Vertical/power board 012-6931; parts document 1.12.516931.4/01 |
| Same set | 16 schematic, 17 parts/layout | Neck board 012-6891; parts document 1.12.516891.0/01 |
| Same set | 18 | Assembly wiring |
| [Matching K7222.11/.21 operating manual](https://www.tiffe.de/Robotron/Monitore/Monitore_2/Monitor_K7222_11_21_Betriebsdokumentation.pdf) | 9–21 | Functional explanation and circuit/waveform figures |
| Same operating manual | 29–32 | Adjustments and test patterns |
| [K7222.13/.23 description](https://www.sax.de/~zander/zubehoer/k7222/k7222_61.pdf) | Throughout | Later revision's circuit operation; not a BOM |
| [Later service manual](https://www.tiffe.de/Robotron/Monitore/Monitore_2/Monitor_K_7222.13_und_23_Betriebsvorschrift_mit_Einstellungen.pdf) | Throughout | Later revision's calibration and assembly spares |

The older schematic has handwritten modifications and connector mappings. Treat
those separately from the printed design. Its board list is much more useful
than the later topology-only scan, but does not specify complete transformer
equivalent circuits. SP2's listed V1/V5 are 1SC60A, V6 is 1SA20C, V12/V13
are SF1260/SF1280; substituting a generic modern transistor does not qualify
those devices. The board-level SP2 BOM omits some assembly-level items such as
the flyback T3 and output transistor V18. Neck C2 is given as a part designation,
not a directly usable capacitance. SP3 has a duplicated-looking C5/C6 scan entry
and handwritten semiconductor annotation. The [plan](PLAN.md) closes such gaps
with agent reads and bounded class-typical values.

The museum CAD's K7222.25 comparison and the later .13/.23 diagrams do not establish
that any of these is the installed specimen. The earlier boards are a separate
reference; a verified mapping is required before reusing their values for .13/.23.

## Flyback information

[Daniel Auerbach's ÜHA78 repair report](https://www.sax.de/~zander/zubehoer/k7222/uha78rep.pdf)
describes his **replacement** high-voltage winding: 26 layers × 68 turns, about
0.10 mm copper wire, and about 440 ohms measured resistance. These are useful
facts about that repair, not factory winding data. The report changes the cold-end
connection and describes sensitivity to winding placement. It supplies neither a
complete original multiwinding model nor the core's magnetic characteristic.

A [2026 K7222 parts-list discussion](https://www.robotrontechnik.de/html/forum/thwb/showtopic.php?threadid=24259&time=1265141096)
contains a semiconductor-list excerpt, but not a complete downloadable parts list
with an established board revision. Keep it as a lead. No owner has been contacted.

## What this unblocks

The printed assembly drawing (schematic-set PDF page 18, drawing
1.11.017260.0/17) identifies **B31G22** and **AE9VT 6802.01, TGL 200-7102**.
These are the reference identities; a later B31G1 or museum specimen must not be
silently substituted. The drawing does not provide a calibrated yoke field,
electron-gun geometry, phosphor decay or transformer equivalent circuit.

The [board inventory](reference/k7222-11/inventory.json) now records 260 entries,
including individually designated diode/capacitor sections and known
schematic-only parts. Descriptions are normalized transcriptions, not verbatim
quotes.
[Assembly identities, neck connector pins and annotations](reference/k7222-11/assembly.json)
are separate. In particular, handwritten voltage/current/control notes are not
promoted to manufacturer specifications. The duplicated-looking SP3 C5 entry is
assigned C6 with `inferred` evidence. Unknown capacitances and transformer
properties remain unknown in the inventory.

### Power-board transcription corrections

Review against the matching schematic, layout and operating manual corrected
these entries before connecting the power stage:

- **012-6931:V22 is a power transistor**, not a diode. Schematic PDF page 10,
  the three-terminal heatsink-mounted part on layout page 11, and operating
  manual PDF page 9 (converter V10/V22) contradict the earlier diode-BOM range
  expansion. Its semiconductor type remains unresolved. It retains its board
  identity; there is no second assembly V22.
- V27/V28 belong to the vertical output stage (operating manual PDF page 14),
  not the converter. Their device types remain unresolved.
- The EDVU-Z entries C6, C10, C18 and C25 are interpreted as **10 nF, 2.2 nF,
  33 nF and 33 nF**, replacing the earlier pF normalization. The printed codes
  are on schematic-set PDF page 12. Corroboration is the
  [AFE12 instructions transcription](https://www.dl0bn.de/dc7xj/Anleitungen/RFT_AFE12-Anleitung.pdf),
  PDF page 22: EDVU-Z-10/50-63 is explicitly expanded as 10 nF, with 22 and 100
  likewise in nF. This is DC7XJ's edited 2023 transcription, not an original
  TGL specification. These corrections therefore retain **inferred** evidence;
  C6 also retains its designator uncertainty.
- C15's printed `EDVU-N150/5-63` does not establish 5 pF. That earlier value
  has been removed. N150 may denote temperature coefficient and the code lacks
  an unambiguous capacitance. Its value is explicitly unresolved.

The source manifest preserves the new document's hash and provenance. Existing
published experiment artifacts retain their historical input snapshots; these
corrections do not retroactively validate those experiments. Converter timing
designators/values, winding polarities and device types still require review;
the model must not tune them to force a desired rail voltage.

The 19-entry neck board now has an editable KiCad transcription and a bounded
electrical bench. Its six-diode network retains both the Baker clamp and the
oppositely directed intensity paths. The generic device-family parameters are
assumptions, **not** fitted SSY20A or 1AD50 datasheet models. The newly archived
DDR semiconductor compilation is a research lead, not the provenance of those
assumed values. Board inventory coverage is separate from model qualification.

The [service observation register](reference/k7222-11/service-observations.json)
separates specified input/supply limits from approximate waveform amplitudes.
The manual labels the latter *Richtwerte*. They are not yet evaluated against a
complete circuit, and no numerical acceptance tolerance is invented for them.

The earlier reference has enough published information to continue a traceable
component/topology transcription and compare simulated nodes to the matching
manual's service waveforms. [Selected parts](reference-parts.csv) preserve a small
set of directly read values, grouped exactly by board and source page. They are
research records, **not a complete BOM or solver input**; units and type notation
remain as printed where ambiguous.

Historical qualification still requires full topology review, device models,
transformer polarity/taps/inductance/leakage/capacitance/core characteristics,
yoke parameters and tube/phosphor calibration. An oscillator driven by an ideal
source or a guessed transformer can demonstrate the pipeline but cannot satisfy
that qualification.


### Vertical amplifier and regulator review

The A3 reconstruction uses operating-manual PDF p15 Fig.12 to disambiguate the
feedback chain: V23 connects the lower threshold to the upper threshold; V24/V25
connect the upper threshold to the amplifier input. C23 decouples the 7.15 V
reference. Source-set p10 identifies C21 on the negative rail and R29 across the
yoke. The BOM sets C26 to 220 pF. These are circuit connections, independent of
whether the assumed LM709-family and power-transistor models match the specimen.

The 5 V regulator output capacitor is **C5, 1000 µF**, not C8, 47 µF. Enlarged
source-set p9 and operating-manual p9 (printed p7) resolve the designator: the
latter explicitly assigns C8 to the converter soft-start network with R18/R12.
The earlier regulator sheet and recordings used the wrong source identity/value;
they are superseded. C8 remains unimplemented until the converter is connected.
