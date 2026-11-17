# Computer output and monitor input evidence

Source: original 1715W archive recorded in `sources.json`, drawing
`teil_b/Stromlauf CRT-Steuerung B.jpg`, 1.93.310412.6/04. Monitor references are
K7222.11/.21 `older.pdf` sheets on PDF pages 3–4 (012-6921) and 9 (012-6931).
Do not substitute later .13/.23 boards or the unrelated MON 3 drawings.

| Connector | Source | Meaning |
|---|---|---|
| X1:A5 | E03 74S37 unit 2, pin 6 | VIDEO |
| X1:A1 | E03 unit 1, pin 3 | INTENS, inverse HGLT |
| X1:A3 | E03 unit 4, pin 11 | BSYN |
| X1:B1 | E03 unit 3, pin 8 | intermediate VSYN, not BSYN |
| X1:B2 | drawing return | 0 V |

HRTC triggers E05's first nominal 5.9 µs one-shot; its ending triggers the
second. HRTC also shifts VRTC through four E07 DL175 stages. The E08/E04
edge network sets an RS latch on VRTC rising; the fourth E07 stage resets it.
With active pulse states UV1/UV2, the traced equations are
`VSYN = !(vertical_latch && !UV1)` and `BSYN = VSYN && !UV2`.
Outside vertical sync, BSYN goes low 5.9 µs after HRTC rising for 5.9 µs.
The vertical latch produces positive UV1 serrations for four HRTC edges.
The logical edge detector is instantaneous; its 100 Ω/1 nF network and actual
DL123 tolerances are not transistor-level simulated. Timing vectors test these
relations independently of the emulator raster.

012-6921 A1 is a four-NAND T200. VIDEO uses pins 1/2→3→12/13→11;
BSYN uses 4/5→6; INTENS uses 9/10→8. Each connector line has its original
160 Ω pull-down, 270 Ω pull-up and diode clamp. Source IDs on every KiCad
component retain the inventory identity; generated reference numbers are unique
across sheets. V5/V1 and the diode/contrast network condition intensity. V6
buffers sync; the 012-6931 R3/C2/C1/R20/R28/V6/C12 input filter is connected.
The oscillator and horizontal phase-control circuits remain outside this bench.

The assembler remaps monitor sheet ground to `mreturn`, connected to computer
zero through the declared cable return resistance. It adds bounded cable R/C,
external supplies, contrast potentiometer and downstream loads explicitly in
the archived deck; these are not claimed as transcribed component values.

`signal_path.BOUNDS` stores nominal/minimum/maximum engineering assumptions.
Resistance is in ohms, capacitance in farads, time constants in seconds,
voltage levels/threshold/span in volts, and contrast position is a fraction.
These ranges explore sensitivity, not measured tolerances or probability.
74S37/T200 thresholds, input currents, impedance and edge response are functional
approximations. Input 1SC60A/1SA20C transistors currently use the generic bounded
NPN family named SSY20A_BOUND; that name does not mean their device curves have
been characterized. Cable values, external contrast pot value/setting and omitted
oscillator loads need specimen evidence. The digital PWL uses a 100 ps numerical
edge before finite electrical driver response. The simulation starts from a DC
operating point, without retained analogue prehistory.

Numerical acceptance is local to the tested stimulus, window and parameters.
It does not validate unknown topology, specimen identity, supply/deflection
coupling, thermal drift or the cause of the museum monitor's pale expanding image.
