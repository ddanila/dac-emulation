# Reduced single-frame acceptance

The runner can now perform electrode feedback and signed circuit/beam energy
checks. These are measured acceptance gates, replacing the unconditional
“not implemented” blockers. **A passing reduced-model frame has not yet been
established.** An image or a passing orchestration test does not establish one.
The converter rails, warm heater state, repeating native S550 field and analytic
phosphor initialization remain declared simplifications. All results retain
`full_monitor_qualified=false` and `specimen_validated=false`.

## Charge and collection

`collection.py` assigns each integrated electron packet a collector, terminal
position, arrival time and kinetic energy. Phosphor and offscreen anode arrivals
load the anode. The reduced profile explicitly treats the post-gun neck/funnel as
an absorbing **anode-connected sleeve**; this is an engineering surrogate for
this experiment, not a statement that real glass is conductive. Unsupported gun
or reversed trajectories retain their charge in an unresolved bucket and block
acceptance. Grid-2 capture remains an empirical upstream split.

Periodic linear hat functions deposit arrival charge into two adjacent current
knots, wrapping at the field boundary. Their integrated current preserves packet
charge. The circuit replaces the old assumed anode current with this arrival
current and retains an instantaneous cathode-emission return and the separate
Grid-2 branch. It does not add the new load on top of the old load. The difference
between launch and arrival currents represents electrons in flight; periodic
in-flight charge change is assumed zero and explicitly recorded.

Emission probes use 1 V per microamp, with an explicit conversion back to amps.
Using one volt per amp put the signal near ngspice's voltage tolerance and
produced materially negative samples. Export rejects negative emission beyond
roundoff; it does not hide the error by clipping significant negative current.

`beam_feedback.py` requires a synchronized periodic input state, then iterates
circuit → trajectories → collection → circuit.
Relaxation starts at 0.5, halves when the residual worsens, and stops below 1/64
or after 20 iterations. Two consecutive iterations must agree within 1% in load
and electrical waveforms, and within 0.1% in periodic charge. Synchronization is
an additional requirement. Relaxed predictors are not labelled measured energy
results. A failed collection pass retains the latest completed electrical trial
for diagnostics.

## Signed energy

`energy_ledger.py` expands the actual SPICE deck and inventories every component.
Unsupported primitives/options fail coverage. The manifest binds the component
inventory and instrumented deck by SHA-256. Resistors contribute loss; capacitors,
inductors and mutual inductance contribute independent storage changes. The
shared magnetic core uses the integral of the actual smoothed inverse B–H law.
Numerical temperature and flux-state capacitors are excluded from electrical
energy, with named reasons.

Independent sources and controlled sources contribute signed work. Semiconductor
terminal work includes internal storage and is not labelled heat. Semiconductor terminal
currents are measured with zero-volt series probes. BJT `@ic`/`@ib` queries omit
external base–collector displacement current; direct rectifier probes also avoid
relying on device-state current queries in the switching waveform. All three BJT
terminals are metered, including emitter current with an implicit grounded substrate. The independent
instrumented solve must still agree with the original electrical waveforms.

Circuit residual is normalized to the larger net source delivery or absorbed
work, rather than their sum. Cancelling internal E/F transformer transfers do not
inflate that scale. The circuit, terminal-work and magnetic checks require <1% error. Auxiliary
capacitor/inductor terminal work is compared with independent storage changes
to expose numerical integration loss; it is not counted twice in the ledger.
Beam electrical work is compared separately with trajectory kinetic-energy gain,
using beam work as its own scale; rail power cannot conceal beam imbalance.
The beam check also requires <1% error and accepted charge accounting.

## Final gates and failure behavior

After coupling and energy checks, independent timestep/tolerance refinement and
a second initialization must converge and agree. The refined coupling halves
trajectory/time steps and doubles the arrival-current grid. Optical temporal,
trajectory and image-resolution refinements remain required, with frozen exposure
and geometry. The joint yoke inductance/field relationship must be verified for
the chosen reduced profile.

Only all passing checks produce `accepted-experiment` and exit 0. A completed but
unaccepted experiment exits 2. Incomplete or failing stages retain their evidence;
a diagnostic image never becomes a healthy reference through a status rename.
The latest completed failed electrical validation is used for a diagnostic when
budget allows. No earlier image is substituted if the budget expires.

## Horizontal audit

The local response bench independently varies pulse amplitude (50/25/12.5 mV),
phase perturbation (0.005/0.0025/0.00125 line), and solver steps (100/50/25 ns).
It records pre-perturbation settling and separate amplitude/solver convergence.
A local result that fails any of these checks cannot reject a T3 polarity.
The connected trim scan optionally runs up to three independent solves at once;
each owns its assembly copy. Results retain deterministic trim order and still
require a sampled passing interval, boundary refinement, midpoint validation and
independent initialization.

The original `older.pdf`, page 3 (SHA-256
`3c435063815af483a0fa98823a8a95a4178359e64f759344ee03cc0300e292dd`),
was visually rechecked against the phase detector transcription: V8/D1032 runs
from `h_trim` to `h_pd`, and V9/D1033 from `h_control` to `h_pd` (anode → cathode).
C5 connects the detector to sync; C9 bridges detector and control; R15/C8 and
C17 provide the feedback return. This audit found no supported diode-direction
change. It does not resolve the original T3 winding polarities or validate the
loaded loop response.
