/* Experimental binary64 time/step consistency; no circuit or tolerance changes. */
#ifndef ROBOTRON_REPRESENTED_TIME_STEP_H
#define ROBOTRON_REPRESENTED_TIME_STEP_H
#include <math.h>

static int robotron_represented_step(double base, double requested, double minimum,
                                    double *next, double *effective)
{
    double candidate, interval;
    if (!next || !effective || !isfinite(base) || base < 0 ||
        !isfinite(requested) || requested <= 0 || !isfinite(minimum) || minimum <= 0)
        return 1;
    /* Do not lower the configured floor for a request at or above it.
       Preserve intentionally smaller requests (e.g. exact breakpoints). */
    double floor = fmin(requested, minimum);
    candidate = base + requested;
    interval = candidate - base;
    if (interval < floor) {
        candidate = nextafter(candidate, INFINITY);
        interval = candidate - base;
    }
    if (!isfinite(candidate) || !isfinite(interval) || interval < floor || interval <= 0)
        return 1;
    *next = candidate;
    *effective = interval;
    return 0;
}
#endif
