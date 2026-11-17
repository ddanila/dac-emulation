/* Experimental controller primitive. All memory belongs to analog timestep
 * history, never a static variable or last Newton evaluation. Finite output
 * transition is a numerical assumption refined separately from thresholds. */
#include <math.h>
#include <string.h>
void cm_crt_schmitt(ARGS)
{
    double *now, *old, input=INPUT(in), target, output, crossing, fraction;
    int changed;
    if (ANALYSIS==MIF_AC) {
        AC_GAIN(out,in).real=0;AC_GAIN(out,in).imag=0;return;
    }
    if (INIT) {
        cm_analog_alloc(0, 5*sizeof(double));
        old=(double *)cm_analog_get_ptr(0,1);
        old[0]=input;old[1]=(input>=PARAM(high));
        old[2]=0;old[3]=old[1];old[4]=old[1];
    }
    now=(double *)cm_analog_get_ptr(0,0);
    old=(double *)cm_analog_get_ptr(0,1);
    memcpy(now,old,5*sizeof(double));
    now[0]=input;
    target=old[1];
    if (input>=PARAM(high))target=1;
    else if(input<=PARAM(low))target=0;
    changed=(target!=old[1]);
    if (ANALYSIS==MIF_DC) {
        now[1]=target;now[2]=0;now[3]=target;now[4]=target;
        OUTPUT(out)=target;PARTIAL(out,in)=0;
        return;
    }
    if(changed) {
        crossing=TIME;
        if (TIME>T(1) && input!=old[0]) {
            fraction=((target?PARAM(high):PARAM(low))-old[0])/(input-old[0]);
            if(fraction>0 && fraction<1) {
                crossing=T(1)+fraction*(TIME-T(1));
                /* Do not repeatedly backtrack onto the same floating-point
                 * crossing. This tolerance is 1e-4 of the explicit edge
                 * duration and is refined with that duration. */
                if(crossing>T(1)+PARAM(edge_s)*1e-4 &&
                   crossing<TIME-PARAM(edge_s)*1e-4)
                    cm_analog_set_temp_bkpt(crossing);
            }
        }
        now[1]=target;now[2]=crossing;now[3]=old[4];
    }
    fraction=fmax(0,fmin(1,(TIME-now[2])/PARAM(edge_s)));
    output=now[3]+fraction*(now[1]-now[3]);
    if (now[2]+PARAM(edge_s)>TIME)cm_analog_set_temp_bkpt(now[2]+PARAM(edge_s));
    now[4]=output;OUTPUT(out)=output;PARTIAL(out,in)=0;
}
