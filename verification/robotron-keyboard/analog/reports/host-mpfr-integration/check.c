/* Exercise the actual NIintegrate adapter, including the disabled branch. */
#include "ngspice/ngspice.h"
#include "ngspice/cktdefs.h"
#include "ngspice/sperror.h"
#include <string.h>
char *errMsg;
int main(int argc, char **argv)
{
    CKTcircuit ckt;
    double states[8][2] = {{0}}, geq = 0, ceq = 0;
    int i, status;
    if (argc != 2) return 1;
    memset(&ckt, 0, sizeof(ckt));
    for (i = 0; i < 8; ++i) {
        ckt.CKTstates[i] = states[i];
        states[i][0] = 1;
    }
    ckt.CKTintegrateMethod = GEAR;
    ckt.CKTorder = 2;
    ckt.CKTag[0] = 1e16;
    ckt.CKTag[1] = 1;
    ckt.CKTag[2] = -1e16;
    status = NIintegrate(&ckt, &geq, &ceq, .5, 0);
    if (!strcmp(argv[1], "invalid")) return status == E_BADPARM ? 0 : 2;
    if (status || geq != 5e15 || ceq != -1e16) return 3;
    if (states[0][1] != (!strcmp(argv[1], "256") ? 1 : 0)) return 4;
    puts("NIintegrate adapter arithmetic and state write verified");
    return 0;
}
