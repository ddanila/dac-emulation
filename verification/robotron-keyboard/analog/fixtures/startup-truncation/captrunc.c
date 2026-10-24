/**********
Copyright 1990 Regents of the University of California.  All rights reserved.
Author: 1985 Thomas L. Quarles
Modified: September 2003 Paolo Nenzi
**********/
/*
 */

#include "ngspice/ngspice.h"
#include "ngspice/cktdefs.h"
#include "capdefs.h"
#include "ngspice/sperror.h"
#include "ngspice/suffix.h"


int
CAPtrunc(GENmodel *inModel, CKTcircuit *ckt, double *timeStep)
{
    CAPmodel *model = (CAPmodel*)inModel;
    CAPinstance *here;

    for( ; model!= NULL; model = CAPnextModel(model)) {
        for(here = CAPinstances(model); here != NULL ;
                here = CAPnextInstance(here)) {

            double audit_previous = *timeStep;
            CKTterr(here->CAPqcap,ckt,timeStep);
            if (((getenv("ROBOTRON_LIVE_AUDIT") && ckt->CKTtime > .001005011 && ckt->CKTtime < .001005014) || (((getenv("ROBOTRON_SWITCH_AUDIT") && ckt->CKTtime > .00106603 && ckt->CKTtime < .00106605) || (getenv("ROBOTRON_INDUCTOR_MONITOR") && ckt->CKTtime > .00106603 && ckt->CKTtime < .00106605 && ckt->CKTstat->STATnumIter % 2048 < 8)))) && *timeStep < audit_previous)
                fprintf(stderr, "TRUNC_AUDIT instance time=%a name=%s state=%d before=%a proposed=%a q0=%a q1=%a\n", ckt->CKTtime, here->CAPname, here->CAPqcap, audit_previous, *timeStep, ckt->CKTstate0[here->CAPqcap], ckt->CKTstate1[here->CAPqcap]);
        }
    }
    return(OK);
}
