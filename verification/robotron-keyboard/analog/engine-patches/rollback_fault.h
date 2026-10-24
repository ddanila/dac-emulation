/* Diagnostic injection for one fresh transient run, not a physical model.
 * Route one otherwise converged trial through the existing Newton retry path. */
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int robotron_force_newton_reject(int result, double time, int *fired)
{
    const char *enabled = getenv("ROBOTRON_FORCE_NEWTON_REJECT");
    const char *requested;
    double start = 0.0010025;
    if (result != 0 || *fired || !enabled || strcmp(enabled, "1") != 0)
        return result;
    requested = getenv("ROBOTRON_NEWTON_REJECT_START");
    if (requested) {
        char *end;
        errno = 0;
        start = strtod(requested, &end);
        if (errno || end == requested || *end || !isfinite(start) || start < 0) {
            fprintf(stderr, "ROLLBACK_FAULT invalid_start\n");
            *fired = 1;
            return result;
        }
    }
    if (time >= start) {
        *fired = 1;
        fprintf(stderr, "ROLLBACK_FAULT kind=newton time=%a original=%d injected=%d\n",
                time, result, E_ITERLIM);
        return E_ITERLIM;
    }
    return result;
}
