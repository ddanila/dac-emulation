# Provisional controller model

`tda1060.cir` is a functional building block for investigating the converter,
**not a qualified B260D model or a connected monitor simulation**. It is not
selected by any published fault-atlas profile. The manufacturer document is
recorded as `tda1060.pdf` in `../sources.json`; its B260D equivalence cover does
not establish matching electrical characteristics.

The 16 ports follow the pin table on PDF page 3, including MOD at pin 5, CM at
pin 11 and QC at pin 15. The pin-number typo in the output-stage prose is not
used. KiCad subcircuits require an explicit model-name/pin-count contract in the
profile; undeclared devices and missing or extra pins fail export. The model
declaration must agree with the contract.

## Evidence and assumptions

| Quantity | Implementation | Basis |
|---|---|---|
| CX sawtooth thresholds | 1.3 / 5.7 V | Manufacturer typical values |
| Oscillator timing | external RX current and CX charge/discharge | Functional description |
| Timing calibration | RX equivalent 6.83 V, discharge 4.4 mA | Calibrated to 30.5 kHz at 6.4 kilohms / 6.4 nF and approximately 1 microsecond reset per nF; not an independent validation point |
| Regulated reference | 8.4 V pass element, 5 ohms small-signal impedance, 10 mA soft current limit | Typical voltage; impedance and limit assumed |
| Feedback reference | 3.72 V | Manufacturer typical value |
| Error amplifier | 10 mS, 3 mA limit, 12 kilohms output resistance | Assumed functional approximation; not a fitted transistor circuit |
| Undervoltage | enable 9.8 V, disable 9.3 V | Assumed threshold within documented 8.85–10.8 V range; typical 0.5 V hysteresis |
| Logic transition | 1.4 V | Assumed within logic low/high limits |
| DFM discharge | 100 ohms disabled; 1 kilohm to lower ramp level when FB < 0.6 V | Manufacturer block diagram |
| CM thresholds | 0.48 V cycle termination; 0.6 V severe trip | Manufacturer typical values |
| SAT threshold | 0.6 V pulse inhibit | Manufacturer typical value |
| Pulse termination | latch until sawtooth reset, including PWM termination | Manufacturer functional description; 10 ns state regularization is numerical |
| Severe-trip holdoff | about 1 ms after last severe trip, with DFM discharge | Recovery mechanism documented; duration is an uncalibrated engineering assumption |
| QC → QE output | NPN with passive 680/1000 ohm on-divider and 100 ohm off pull-down | All internal drive/device values assumed; not B260D transistor characterization |
| PWM and Schmitt transitions | 20 ns RC; 1 mV Schmitt smoothing | Numerical regularization, checked by two halvings; not measured device switching time |
| Internal supply current | 5 mA plus modeled reference/timing draw | Assumed, not an energy-qualified transistor implementation |

Use is restricted to component characterization within ratings. QC supplies the
output transistor and VZ supplies its base drive; QE is no longer an ideal current
source which can raise an arbitrary load above its rating. This is still not an
output protection or SOA model: the connected load must be checked against the
manufacturer's QE voltage and output-current limits. A disabled oscillator has
an assumed 1 kohm discharge path, avoiding an unphysical negative DC ramp caused
by leakage into a floating timing capacitor. Internal clamp diodes have assumed
10 ohm series resistance, 5 pF junction capacitance and 5 ns transit time; zero-charge
clamps caused rejected solver runs at undervoltage turn-on. These are engineering
parameters, not recovered B260D data. The reference pass element draws its current
from VCC rather than an ideal generated rail with recursive current accounting.

Unsupported mechanisms include calibrated recovery/dead-time behavior,
feed-forward, temperature drift, output storage and synchronization during ramp
reset. The supply draw is approximate. Those omissions preclude using this
model to classify regulation, thermal or short-circuit faults in the monitor.
They must be implemented and bounded before diagnostic publication.

## Reproduction

```
python3 -m unittest discover -s verification/robotron-monitor/tests -p test_controller.py -v
```

Checks cover the calibrated frequency point, doubled timing capacitance,
half-timestep agreement, sawtooth range, output rating under the test load,
feedback shutoff, modulation shutoff, enable shutoff, overcurrent inhibition,
and undervoltage inhibition. Transient checks also verify that removing a mild
overcurrent pulse does not restart the same output pulse, and that a severe trip
discharges DFM, holds off output, and subsequently permits soft-start recovery.
The 1 ms recovery duration is not a B260D timing prediction. Solver-error logs are rejected even if ngspice
returns exit status zero and produces a padded `linearize` output. All tests
remain component tests; none establish a cause for a pale, expanding raster.


## Labelled P09A amplifier equivalent

The page-10 A3 source read maps physical pins 3/4/5/6/9/10/11/12 to the
functional compensation-A, inverting, noninverting, negative rail, output
compensation, output, positive rail and compensation-B ports. The old
`lm709-family.cir` transcribes the National/TI LM709 internal diagram with
generic transistor parameters. Its [isolated DC check](../reference/k7222-11/lm709-dc-follower-check.json)
shows a +1 V follower input driving the output to +12.54 V. That transistor
proxy remains as a failed candidate and is no longer assembled as A3.

The live `p09a-equivalent.cir` is explicitly a functional equivalent, using
the LM709C data sheet as a class comparator rather than identifying P09A.
It keeps the source external C26/R54 and C27 compensation networks, finite
input resistance and bias, gain, slew, output headroom, 2.6 mA quiescent draw,
and rail-fed limited output current. Its local parameters have provisional
bounds in the A2 and A6 registers. The [isolated class check](../reference/k7222-11/p09a-equivalent-class-check.json)
passes eight nominal DC, transient and rail-current checks. It does not prove
the original P09A silicon, thermal limits or joint parameter bounds.

The [connected native-period diagnostic](../reference/k7222-11/vertical-a3-loaded-stage-diagnostic-p09a-equivalent.json)
passes loaded TP7 at 2.159 Vpp but fails loaded TP8 at 25.767 Vpp against its
17 V ±25% guideline. Y1 also differs by 0.597 V between adjacent late fields.
This is a synthetic-sync stage result, not a periodic or grid-stimulus A3
qualification. The other page-10 feedback and output-stage connections still
need source review before interpreting the TP8 failure as a device parameter.
