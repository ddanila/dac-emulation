"""Parameterized paraxial CRT model. SI units; no specimen calibration claimed."""
import math

ELECTRON_CHARGE = 1.602176634e-19
ELECTRON_MASS = 9.1093837139e-31

DEFAULTS = {
    "screen_width_m": .210, "screen_height_m": .145,
    "screen_radius_m": .45, "drift_m": .20, "yoke_length_m": .04,
    "horizontal_tesla_per_amp": .0012, "vertical_tesla_per_amp": .0012,
    "focus_ratio": .12, "spot_sigma_m": .00025,
    "phosphor_tau_s": .025, "light_efficiency": .08,
}


def landing(anode_v, focus_v, horizontal_a, vertical_a, parameters=None):
    """Magnetic momentum kick followed by intersection with spherical phosphor.

    The finite-length yoke uses a uniform-field approximation. No field solve,
    space charge, astigmatism or tube-specific lens transfer has been measured.
    Missing/low EHT yields no landing, not an artificially centered bright spot.
    """
    p = DEFAULTS | (parameters or {})
    if not all(math.isfinite(v) for v in (anode_v, focus_v, horizontal_a, vertical_a)):
        raise ValueError("non-finite electrical input")
    if anode_v <= 100:
        return 0., 0., p["spot_sigma_m"], False
    momentum = math.sqrt(2 * ELECTRON_MASS * ELECTRON_CHARGE * anode_v)
    scale = ELECTRON_CHARGE * p["yoke_length_m"] / momentum
    ax = scale * p["horizontal_tesla_per_amp"] * horizontal_a
    ay = scale * p["vertical_tesla_per_amp"] * vertical_a
    # Paraxial model must not masquerade as a solution at arbitrary angles.
    if math.hypot(ax, ay) > .8:
        return 0., 0., p["spot_sigma_m"], False
    sx, sy = math.tan(ax), math.tan(ay)
    z = p["drift_m"]
    for _ in range(8):
        r2 = (z * sx)**2 + (z * sy)**2
        if r2 >= p["screen_radius_m"]**2:
            return 0., 0., p["spot_sigma_m"], False
        z = p["drift_m"] - p["screen_radius_m"] + math.sqrt(p["screen_radius_m"]**2-r2)
    x, y = z * sx, z * sy
    sigma = p["spot_sigma_m"] * (1 + 30 * abs(focus_v/anode_v-p["focus_ratio"]))
    visible = sigma <= .01 and abs(x) <= p["screen_width_m"]/2 and abs(y) <= p["screen_height_m"]/2
    return x, y, sigma, visible


def deposit(image, width, height, x, y, sigma, joules, parameters=None):
    """Conserve deposited energy, including clipping at the screen boundary."""
    p = DEFAULTS | (parameters or {})
    px = (x/p["screen_width_m"]+.5)*width-.5
    py = (.5-y/p["screen_height_m"])*height-.5
    sx = max(.45, sigma/p["screen_width_m"]*width)
    sy = max(.45, sigma/p["screen_height_m"]*height)
    weights = []
    for iy in range(math.floor(py-3*sy), math.ceil(py+3*sy)+1):
        for ix in range(math.floor(px-3*sx), math.ceil(px+3*sx)+1):
            weights.append((ix, iy, math.exp(-.5*(((ix-px)/sx)**2+((iy-py)/sy)**2))))
    total = sum(w for _, _, w in weights)
    retained = 0.
    for ix, iy, w in weights:
        if 0 <= ix < width and 0 <= iy < height:
            energy = joules*w/total
            image[iy*width+ix] += energy
            retained += energy
    return retained
