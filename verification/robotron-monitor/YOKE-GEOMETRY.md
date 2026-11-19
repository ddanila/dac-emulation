# Reduced yoke geometry and its limits

Production steady-supply experiments now default to
`profiles/k7222-11-yoke-geometry.json`. The historical independent R/L/field model
remains available explicitly with `--yoke-profile profiles/k7222-11-yoke.json`
(relative to the monitor directory, or supply its full repository path).
Neither profile is calibrated to a museum specimen.

The new model solves the two-dimensional m=1 vector potential for orthogonal
cosine current sheets in a concentric air bore, air gap, linear ferrite annulus
and exterior air. In each region, A_z = (u r + v/r) cos(theta). Continuity of
A_z and tangential H, with the sheet-current jump, determines six coefficients.
The bore field is uniform, so the existing Python and C++ trajectory integrators
can consume the derived field-per-ampere directly without a field-map approximation.
They terminate neck intersections before electrons can leave that bore domain.

K(theta) = N I cos(theta)/(2a), where a is sheet radius. Flux linkage gives
L = pi mu0 N² u0 (3 length/2)/4 in dimensionless radial coordinates. An independent
radial integration of B²/mu gives the energy-derived inductance. Quadrature is
refined from 128 to 256 samples per radial region, and the exterior integration
boundary doubles from 64 to 128 core radii. Agreement must be within 1%.
The exact harmonic boundary solution does not require a spatial field mesh.

The axial envelope remains g(z) = 2 sin²(pi z/length). Its squared integral,
3 length/2, is used in both energy and generalized flux linkage. This is a
separable reduced field/end-return assumption, not a solved three-dimensional
coil end field. Ferrite is linear and lossless; frequency-dependent loss,
saturation and hysteresis are not reconstructed by this profile.

Integer turns are selected from the declared inductance constraint. Wire area
is selected from resistance, copper resistivity and the declared ideal saddle
return length. Peak cosine winding fill, neck/core clearance and winding-region
overlap are checked. Finite packing regions are represented magnetically by thin
sheets. The electrical targets are hypotheses, not measured constraints.

The initial narrower winding regions failed packing. The frozen default uses:

- Assumed neck radius: 10 mm.
- Horizontal sheet: radius 16 mm, packing thickness 9 mm, 333 turns.
- Vertical sheet: radius 27 mm, packing thickness 10 mm, 644 turns.
- Ferrite annulus: radii 34–42 mm, relative permeability 2000.
- Active axial length: 40 mm.

An archived [B31-G family outline](https://www.elektroncso.hu/cikkek/crt_m31.gif)
shows a 20 mm outside neck diameter (+0.8/-0.5 mm). A 12 mm internal trajectory
aperture is incompatible with that family outline. A 34.7 mm active-field hypothesis
can narrowly reach the manual's 105 mm half-width at the present assumed
10 mm internal aperture while staying below the ideal packing ceiling; the
calculation and its limitations are in `reference/k7222-11/design-point.json`.
The default remains 40 mm until inner glass clearance and yoke extent can be
bounded. Neither the outside dimension nor the reduced field trial establishes
the installed tube's physical aperture.

Derived horizontal/vertical field factors are 7.979/12.196 mT/A; inductances are
4.0069/19.9868 mH. Peak fill fractions are 0.599/0.331. These dimensions were
chosen to satisfy electrical, clearance and packing constraints before rendering,
not to make the image fill the screen. Changing geometry requires a new frozen
experiment; independent R/L overrides are refused in this mode.

`inductance_field_relationship_verified` means agreement inside this reduced
mathematical model. It does not establish the real yoke's dimensions, actual field
map, warm resistance or historical winding construction.
