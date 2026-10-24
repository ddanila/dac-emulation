/**********
Copyright 1990 Regents of the University of California.  All rights reserved.
Author: 1985 Thomas L. Quarles
**********/
/*
 */

#include "ngspice/ngspice.h"
#include "ngspice/cktdefs.h"
#include "inddefs.h"
#include "ngspice/sperror.h"
#include "ngspice/suffix.h"


int
INDtrunc(GENmodel *inModel, CKTcircuit *ckt, double *timeStep)
{
    INDmodel *model = (INDmodel*)inModel;
    INDinstance *here;
    for( ; model!= NULL; model = INDnextModel(model)) {
        for(here = INDinstances(model); here != NULL ;
                here = INDnextInstance(here)) {

            double audit_previous = *timeStep;
            CKTterr(here->INDflux,ckt,timeStep);
            if (getenv("ROBOTRON_STARTUP_TRUNC_AUDIT") && ckt->CKTtime >= .75e-6 && ckt->CKTtime <= 1.05e-6 && *timeStep < audit_previous)
                fprintf(stderr, "STARTUP_TRUNC instance time=%a name=%s state=%d before=%a proposed=%a\n", ckt->CKTtime, here->INDname, here->INDflux, audit_previous, *timeStep);
            if (((getenv("ROBOTRON_LIVE_AUDIT") && ckt->CKTtime > .001005011 && ckt->CKTtime < .001005014) || (((getenv("ROBOTRON_SWITCH_AUDIT") && ckt->CKTtime > .00106603 && ckt->CKTtime < .00106605) || (getenv("ROBOTRON_INDUCTOR_MONITOR") && ckt->CKTtime > .00106603 && ckt->CKTtime < .00106605 && ckt->CKTstat->STATnumIter % 2048 < 8)))) && *timeStep < audit_previous)
                fprintf(stderr, "TRUNC_AUDIT instance time=%a name=%s state=%d before=%a proposed=%a q0=%a q1=%a\n", ckt->CKTtime, here->INDname, here->INDflux, audit_previous, *timeStep, ckt->CKTstate0[here->INDflux], ckt->CKTstate1[here->INDflux]);
        }
    }
    return(OK);
}
