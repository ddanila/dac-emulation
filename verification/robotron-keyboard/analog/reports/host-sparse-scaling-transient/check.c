/* Independent analytic control for the actual experimental Sparse helpers. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include "ngspice/smpdefs.h"
extern int SMPdiagnosticScale(SMPmatrix *, double *, double);
extern int SMPdiagnosticUnscale(SMPmatrix *, double *);

int main(int argc, char **argv)
{
    SMPmatrix matrix;
    double rhs[3] = {0, 1099511627778.0, 3}, spare[3] = {0};
    (void)argv;
    if (SMPnewMatrix(&matrix, 0)) return 2;
    *SMPmakeElt(&matrix, 1, 1) = 1099511627776.0;
    *SMPmakeElt(&matrix, 1, 2) = 1;
    *SMPmakeElt(&matrix, 2, 1) = 1;
    *SMPmakeElt(&matrix, 2, 2) = 1;
    if (SMPpreOrder(&matrix)) return 3;
    int mode = SMPdiagnosticScale(&matrix, rhs, argc > 1 ? 1e-12 : 0);
    if (argc > 1) return mode < 0 ? 0 : 4;
    if (mode < 0 || SMPreorder(&matrix, 1e-13, .001, 0)) return 5;
    SMPsolve(&matrix, rhs, spare);
    if (SMPdiagnosticUnscale(&matrix, rhs)) return 6;
    if (fabs(rhs[1]-1) > 1e-9 || fabs(rhs[2]-2) > 1e-9) return 7;
    printf("x1=%a x2=%a\n", rhs[1], rhs[2]);
    SMPdestroy(&matrix);
    return 0;
}
