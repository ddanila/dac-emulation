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


## Provisional P09A amplifier family

`lm709-family.cir` transcribes the LM709 manufacturer internal circuit in
TI/National SNOS659A PDF p4 (printed p3); PDF p2 gives the package pin mapping.
The model has 15 transistors and 15 resistors, with external input/output
compensation ports. There is no ideal voltage-source output amplifier.
The board wrapper uses DIP pins 3/4/5/6/9/10/11/12 as compensation-A, inverting,
noninverting, negative rail, output compensation, output, positive rail and
compensation-B respectively. The manufacturer circuit labels metal-can pins;
these are explicitly mapped, not treated as board DIP numbers.

Only the topology and resistor values come from that diagram. NPN/PNP gains
100/50, Early voltages 100/50 V, IS 1e-14 A, junction capacitances 4/2 pF,
forward transit times .2/20 ns and reverse times 20/100 ns are engineering
assumptions stated in the file. No P09A equivalence, production spread, thermal
drift, breakdown, output short-circuit protection or SOA qualification is claimed.

`test_lm709.py` exercises the manufacturer's compensated voltage-follower
arrangement with its 51 ohm isolating resistor. It checks both polarities,
settled supply/load KCL, a heavier load, timestep refinement and slower response
with increased input compensation. The connected vertical bench uses its own
source C26 (220 pF), C27 (18 pF), R54 (1.5 kohm), current feedback and power stage.
Passing the follower test does not establish the historical amplifier's bandwidth.
