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
| Regulated reference | 8.4 V, 5 ohms output impedance | Typical voltage; assumed impedance |
| Feedback reference | 3.72 V | Manufacturer typical value |
| Error amplifier | 10 mS, 3 mA limit, 12 kilohms output resistance | Assumed functional approximation; not a fitted transistor circuit |
| Undervoltage | enable 9.8 V, disable 9.3 V | Assumed threshold within documented 8.85–10.8 V range; typical 0.5 V hysteresis |
| Logic transition | 1.4 V | Assumed within logic low/high limits |
| DFM discharge | 100 ohms disabled; 1 kilohm to lower ramp level when FB < 0.6 V | Manufacturer block diagram |
| CM / SAT thresholds | 0.48 / 0.6 V | Manufacturer typical values; latch behavior not implemented |
| QC → QE current | smooth 40 mA plateau | Assumed drive approximation, not a manufacturer maximum-current claim |
| PWM transition | 20 ns RC | Numerical regularization, not measured device switching time |
| Internal supply current | 5 mA plus modeled reference/timing draw | Assumed, not an energy-qualified transistor implementation |

Use is restricted to component characterization within ratings. In particular,
this current-output approximation **does not clamp QE to its 5 V rating**. The
test load keeps it below that rating; arbitrary converter loads can exceed the
model's valid domain. No historical converter result is qualified by this file.

Unsupported mechanisms include latched overcurrent recovery/dead time,
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
and undervoltage inhibition. Solver-error logs are rejected even if ngspice
returns exit status zero and produces a padded `linearize` output. All tests
remain component tests; none establish a cause for a pale, expanding raster.
