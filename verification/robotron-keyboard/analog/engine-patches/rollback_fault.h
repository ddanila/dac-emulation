/* Diagnostic injection for one fresh transient run, not a physical model.
 * Route one otherwise converged trial through the existing Newton retry path. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int robotron_force_newton_reject(int result, double time, int *fired)
{
    const char *enabled = getenv("ROBOTRON_FORCE_NEWTON_REJECT");
    if (result == 0 && !*fired && time >= 0.0010025 &&
        enabled && strcmp(enabled, "1") == 0) {
        *fired = 1;
        fprintf(stderr, "ROLLBACK_FAULT kind=newton time=%a original=%d injected=%d\n",
                time, result, E_ITERLIM);
        return E_ITERLIM;
    }
    return result;
}
