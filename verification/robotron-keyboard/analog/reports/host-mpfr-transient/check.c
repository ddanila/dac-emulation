/* Analytic checks of the actual Sparse-to-MPFR adapter, including reuse. */
#include <math.h>
#include <stdio.h>
#include "ngspice/smpdefs.h"
extern int SMPmpfrSolve(SMPmatrix *, double *, double, int);
int main(void)
{
    SMPmatrix matrix;
    if (SMPnewMatrix(&matrix, 0)) return 1;
    double *a = SMPmakeElt(&matrix, 1, 1), *b = SMPmakeElt(&matrix, 1, 2);
    double *c = SMPmakeElt(&matrix, 2, 1), *d = SMPmakeElt(&matrix, 2, 2);
    for (int trial = 0; trial < 4; ++trial) {
        double rhs[3] = {0, 2, 3};
        SMPclear(&matrix);
        *a = 0; *b = 1; *c = 1; *d = 1;
        double gmin = trial == 3 ? 1 : 0;
        if (gmin) { *a = 2; *b = *c = 0; *d = 3; rhs[1] = 3; rhs[2] = 8; }
        if (trial == 1) {
            if (SMPpreOrder(&matrix) || SMPreorder(&matrix, 1e-13, .001, 0)) return 2;
            SMPclear(&matrix);
            *a = 0; *b = 1; *c = 1; *d = 1;
        }
        if (SMPmpfrSolve(&matrix, rhs, gmin, trial % 2 ? 512 : 256)) return 3;
        if (rhs[1] != 1 || rhs[2] != 2) return 4;
    }
    SMPdestroy(&matrix);
    puts("pivot, reordered external coordinates, precision changes, reuse and diagonal Gmin pass");
    return 0;
}
