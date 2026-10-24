/**********
Copyright 1990 Regents of the University of California.  All rights reserved.
Author: 1985 Thomas L. Quarles
**********/

#include "ngspice/ngspice.h"
#include "ngspice/cktdefs.h"

#define ccap (qcap+1)


void
CKTterr(int qcap, CKTcircuit *ckt, double *timeStep)
{ 
    double volttol;
    double chargetol;
    double tol;
    double del;
    double diff[8];
    double deltmp[8];
    double factor=0;
    int i;
    int j;
    static double gearCoeff[] = {
        .5,
        .2222222222,
        .1363636364,
        .096,
        .07299270073,
        .05830903790
    };
    static double trapCoeff[] = {
        .5,
        .08333333333
    };

    volttol = ckt->CKTabstol + ckt->CKTreltol * 
            MAX( fabs(ckt->CKTstate0[ccap]), fabs(ckt->CKTstate1[ccap]));
            
    chargetol = MAX(fabs(ckt->CKTstate0[qcap]),fabs(ckt->CKTstate1[qcap]));
    chargetol = ckt->CKTreltol * MAX(chargetol,ckt->CKTchgtol)/ckt->CKTdelta;
    tol = MAX(volttol,chargetol);
    /* now divided differences */
    for(i=ckt->CKTorder+1;i>=0;i--) {
        diff[i] = ckt->CKTstates[i][qcap];
    }
    for(i=0 ; i <= ckt->CKTorder ; i++) {
        deltmp[i] = ckt->CKTdeltaOld[i];
    }
    j = ckt->CKTorder;
    for (;;) {
        for(i=0;i <= j;i++) {
            diff[i] = (diff[i] - diff[i+1])/deltmp[i];
        }
        if (--j < 0) break;
        for(i=0;i <= j;i++) {
            deltmp[i] = deltmp[i+1] + ckt->CKTdeltaOld[i];
        }
    }
    switch(ckt->CKTintegrateMethod) {
        case GEAR:
            factor = gearCoeff[ckt->CKTorder-1];
            break;

        case TRAPEZOIDAL:
            factor = trapCoeff[ckt->CKTorder - 1] ;
            break;
    }
    del = ckt->CKTtrtol * tol/MAX(ckt->CKTabstol,factor * fabs(diff[0]));
    if(ckt->CKTorder == 2) {
        del = sqrt(del);
    } else if (ckt->CKTorder == 3) {
        del = cbrt(del);
    } else if (ckt->CKTorder > 3) {
        del = exp(log(del)/ckt->CKTorder);
    }
    if (((getenv("ROBOTRON_LIVE_AUDIT") && ckt->CKTtime > .001005011 && ckt->CKTtime < .001005014) || (((getenv("ROBOTRON_SWITCH_AUDIT") && ckt->CKTtime > .00106603 && ckt->CKTtime < .00106605) || (getenv("ROBOTRON_INDUCTOR_MONITOR") && ckt->CKTtime > .00106603 && ckt->CKTtime < .00106605 && ckt->CKTstat->STATnumIter % 2048 < 8)))) && del < *timeStep)
        fprintf(stderr, "TRUNC_AUDIT error time=%a state=%d delta=%a dt0=%a dt1=%a dt2=%a order=%d proposed=%a tol=%a difference=%a q0=%a q1=%a q2=%a q3=%a\n", ckt->CKTtime, qcap, ckt->CKTdelta, ckt->CKTdeltaOld[0], ckt->CKTdeltaOld[1], ckt->CKTdeltaOld[2], ckt->CKTorder, del, tol, diff[0], ckt->CKTstates[0][qcap], ckt->CKTstates[1][qcap], ckt->CKTstates[2][qcap], ckt->CKTstates[3][qcap]);
    if (getenv("ROBOTRON_STARTUP_TRUNC_AUDIT") && ckt->CKTtime >= .75e-6 && ckt->CKTtime <= 1.05e-6 && del < *timeStep)
        fprintf(stderr, "STARTUP_TRUNC error time=%a state=%d delta=%a dt0=%a dt1=%a dt2=%a order=%d before=%a proposed=%a currenttol=%a chargetol=%a abstol=%a reltol=%a chgtol=%a difference=%a q0=%a q1=%a q2=%a q3=%a\n", ckt->CKTtime, qcap, ckt->CKTdelta, ckt->CKTdeltaOld[0], ckt->CKTdeltaOld[1], ckt->CKTdeltaOld[2], ckt->CKTorder, *timeStep, del, volttol, chargetol, ckt->CKTabstol, ckt->CKTreltol, ckt->CKTchgtol, diff[0], ckt->CKTstates[0][qcap], ckt->CKTstates[1][qcap], ckt->CKTstates[2][qcap], ckt->CKTstates[3][qcap]);
    *timeStep = MIN(*timeStep,del);
    return;
}
