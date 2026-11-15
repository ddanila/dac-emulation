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
and handwritten semiconductor annotation. These need review, not guessed values.

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

The earlier reference now has enough published information to begin a traceable
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
