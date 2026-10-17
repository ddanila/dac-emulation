# Reference analog simulation

Use the standard S600 ROM and published reference circuit independently of specimen
photographs, replacement firmware and measured timing. Those observations can
calibrate the model later; they are not prerequisites for circuit-model development.

`sense_probe.py` generates the sensing resistor networks and transistor connections
from the pinned KiCad netlist and runs an ngspice DC sweep. It is a backend
feasibility experiment, not a complete board model. The generic PNP parameters,
ideal supply, unloaded outputs and contact resistance are explicit in its report;
they are not claimed SC308 specifications or measured tolerances.

```sh
python3 verification/robotron-keyboard/analog/sense_probe.py
python3 verification/robotron-keyboard/analog/sense_probe.py --beta 50 --contact-ohms 1000 --out /tmp/sense-experiment
```

The output directory contains the generated deck, raw sweep, solver log and report
with input/tool provenance. Changing beta/contact resistance explores assumptions;
it does not qualify a production tolerance range.

The intended full-board backend is ngspice/XSPICE plus Icarus through `d_cosim`.
The [ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf),
section 10.3, documents Icarus and Verilator integration. Icarus needs a build with
`--enable-libvvp`; the currently installed Homebrew Icarus lacks that shared
runtime. The ngspice installation supplies `ivlng.so` and `ivlng.vpi`.
Verilator is an alternative after explicitly validating its X/Z, tri-state and
bridge behavior; it is not an interchangeable replacement for the current tests.

Next implement the reset and TTL oscillator as electrical circuits, qualify device
models and voltage-domain interfaces, and close the feedback loop with TV80, ROM,
matrix contacts and cable load. Keep the original Icarus reference comparison as
an independent regression. CPU internals remain an HDL model unless a separately
qualified transistor-level CPU model is explicitly introduced.
