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

## HDL boundary

Use ngspice 47/XSPICE and Icarus 13 with `--enable-libvvp`. The ordinary Icarus
executable is not enough. Obtain the [ngspice 47 source archive](https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/47/ngspice-47.tar.gz)
(SHA-256 `894e649651f1838a14095e5a5439e7d3aa63e87ede14d283173fda4fcdef675f`)
and [Icarus v13_0](https://github.com/steveicarus/iverilog/tree/v13_0)
(commit `dfeee909ed9f20b4870dd93423156c0170c0e1ff`). In the Icarus source directory,
with autoconf, a C/C++ compiler, flex and Bison 3 on PATH:

```sh
sh autoconf.sh
./configure --enable-libvvp
make -C vvp -j4 libvvp.so
```

On macOS put Homebrew Bison ahead of the system Bison. Build the bridge from the
unmodified sources, passing the resulting shared runtime explicitly:

```sh
python3 verification/robotron-keyboard/analog/build_bridge.py \
  --ngspice-source /path/to/ngspice-47 \
  --icarus-source /path/to/iverilog \
  --libvvp /path/to/iverilog/vvp/libvvp.so
python3 verification/robotron-keyboard/analog/bridge_probe.py
```

The builder preserves symbol visibility (the local Homebrew bridge hid VPI
registration symbols) and applies `icarus-startup.patch`. The patch samples initial
outputs because constant-folded signals may never produce a value-change callback.
It modifies ngspice's GPL-licensed VPI source in the build directory only.

The probe instantiates the existing 7406 HDL model and transports **sink enable**
to an analog conductance with a pullup and capacitive load. It checks initial
release, low drive, later release, X propagation and a known HDL delay at two
analog steps. Reports retain library/source hashes, solver logs and waveforms.
The electrical parameters are exploratory, not calibrated SN7406 characteristics;
the X conductance is a numerical surrogate, not a physical prediction.

`--direct-z --out /tmp/direct-z-diagnostic` reproduces an unresolved failure with
direct Z transport through `bidi_bridge` when refining the timestep. Do not use
that path for the board. A successful ngspice exit alone is insufficient: the
probe also rejects diagnostics, missing ports and incorrect waveforms. The encoded
interface is qualified only for this unidirectional open-collector probe, not for
shared buses or the full feedback loop. Full-board CPU/ROM qualification remains
separate from this test.

Next implement the reset and TTL oscillator as electrical circuits, qualify device
models and voltage-domain interfaces, and close the feedback loop with TV80, ROM,
matrix contacts and cable load. Keep the original Icarus reference comparison as
an independent regression. CPU internals remain an HDL model unless a separately
qualified transistor-level CPU model is explicitly introduced.
