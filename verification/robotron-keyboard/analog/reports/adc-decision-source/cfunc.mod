#include <stdlib.h>
/*.......1.........2.........3.........4.........5.........6.........7.........8
================================================================================

FILE adc_bridge/cfunc.mod

Public Domain

Georgia Tech Research Corporation
Atlanta, Georgia 30332
PROJECT A-8503-405

AUTHORS
    6 June 1991     Jeffrey P. Murray

MODIFICATIONS
    26 Sept 1991    Jeffrey P. Murray

SUMMARY

    This file contains the functional description of the adc_bridge code model.

INTERFACES

    FILE                 ROUTINE CALLED

    CM.c                 void *cm_analog_alloc()
                         void *cm_analog_get_ptr()

    CMevt.c              void *cm_event_alloc()
                         void *cm_event_get_ptr()
                         int  cm_event_queue()

REFERENCED FILES
    Inputs from and outputs to ARGS structure.

NON-STANDARD FEATURES
    NONE

===============================================================================*/

/*=== INCLUDE FILES ====================*/
#include <math.h>
#include <stdlib.h>

/*=== CONSTANTS ========================*/

/*=== MACROS ===========================*/

/*=== LOCAL VARIABLES & TYPEDEFS =======*/                         

/*=== FUNCTION PROTOTYPE DEFINITIONS ===*/

/*==============================================================================

FUNCTION cm_adc_bridge()

AUTHORS
    6 June 1991     Jeffrey P. Murray

MODIFICATIONS
    26 Sept 1991    Jeffrey P. Murray

SUMMARY
    This function implements the adc_bridge code model.

INTERFACES

    FILE                 ROUTINE CALLED

    CM.c                 void *cm_analog_alloc()
                         void *cm_analog_get_ptr()

    CMevt.c              void *cm_event_alloc()
                         void *cm_event_get_ptr()
                         int  cm_event_queue()

RETURNED VALUE
    Returns inputs and outputs via ARGS structure.

GLOBAL VARIABLES
    NONE

NON-STANDARD FEATURES
    NONE

==============================================================================*/

/*=== CM_ADC_BRIDGE ROUTINE ===*/

/************************************************
*      The following is the model for the       *
*   analog-to-digital nodebridge for the        *
*   ATESSE Version 2.0 system.                  *
*                                               *
*   Created 6/6/91                              *
*   Last Modified 7/26/91         J.P.Murray    *
************************************************/

static Digital_State_t get_out_value(double in, double low, double high)
{
    if (low <= high) {
        /* Normal operation. */

        if (in >= high)
            return ONE;
        else if (in <= low)
            return ZERO;
    } else {
        /* (low > high)! Schmitt triger. */

        if (in >= low)
            return ONE;
        else if (in <= high)
            return ZERO;
    }
    return UNKNOWN;
}

void cm_adc_bridge(ARGS)
{
    double         in_low,  /* analog output value corresponding to '0'
                               digital input    */
                  in_high;  /* analog output value corresponding to '1' 
                               digital input    */
    int                 i,  /* generic loop counter index */
                  size_in,  /* number of input ports */
                 size_out;  /* number of output ports */

   Digital_State_t   *out,  /* base address of array holding all output
                               values plus their previous values */
                     test;  /* temp holding variable for digital states */

    in_high = PARAM(in_high);
    in_low = PARAM(in_low);

    /* determine "width" of the node bridge... */

    size_in = PORT_SIZE(in);
    size_out = PORT_SIZE(out);

    if (INIT) {  /*** Test for INIT == TRUE. If so, allocate storage, etc. ***/
        if (size_in != size_out) {
            if (size_in != 1) {
                cm_message_printf("Error: %d input ports with %d outputs",
                                  size_in, size_out);
            } else if (in_low >= in_high) {
                cm_message_printf("Error: bad threshold values (low > high)");
            }
        }

        /* Optional rollback-aware analog history; default-off diagnostic. */
        if (getenv("ROBOTRON_ADC_CROSSINGS") && size_in == size_out) {
            cm_analog_alloc(0, size_in * (int)sizeof(double));
            double *values = (double *)cm_analog_get_ptr(0, 0);
            for (i = 0; i < size_in; ++i) values[i] = INPUT(in[i]);
        }

        /* Allocate storage for outputs */

        cm_event_alloc(0, size_out * (int) sizeof(Digital_State_t));

        /* Get discrete addresses */

        out = (Digital_State_t *) cm_event_get_ptr(0,0);

        /* Ensure output on first call. */

        for (i = 0; i < size_out; i++)
            out[i] = UNKNOWN + 1;
        return;
    }

    /*** This is not an initialization pass...retrieve storage
         addresses and calculate new outputs, if required. ***/

    out = (Digital_State_t *) cm_event_get_ptr(0, 0);

    if (size_in != size_out) {
        if (size_in != 1) {
            if (size_in < size_out)
                size_out = size_in;
            else
                size_in = size_out;
        } else {
            double in;

            /* Single-input, multi-bit output option. */

            in = (INPUT(in[0]) - in_low) / (in_high - in_low);
            switch (CALL_TYPE) {
            case ANALOG:
                for (i = 0; i < size_out; i++) {
                    test = (in >= 0.5);
                    if (test != out[i]) {
                        /* call for event breakpoint... */

                        cm_event_queue(TIME);
                        break;
                    }
                    if (test)
                        in -= 0.5;
                    in *= 2.0;
                }
                break;

            case EVENT:    /** discrete call...lots to do **/
                for (i = 0; i < size_out; i++) {
                    test = (in >= 0.5);
                    if (test != out[i]) {
                        switch (test) {
                        case ZERO:
                            OUTPUT_DELAY(out[i]) = PARAM(fall_delay);
                            break;
                        case ONE:
                            OUTPUT_DELAY(out[i]) = PARAM(rise_delay);
                            break;
                        default:
                            break;
                        }
                        out[i] = test;
                        OUTPUT_STATE(out[i]) = test;
                        OUTPUT_STRENGTH(out[i]) = STRONG;
                    } else {
                        OUTPUT_CHANGED(out[i]) = FALSE;
                    }
                    if (test)
                        in -= 0.5;
                    in *= 2.0;
                }
                break;
            default:
                break;
            }
            return;
        }
    }

    /* Normal, multiple single-bit conversion output option. */

    if (getenv("ROBOTRON_ADC_CROSSINGS")) {
        double *values = (double *)cm_analog_get_ptr(0, 0);
        double *previous = (double *)cm_analog_get_ptr(0, 1);
        double earliest = TIME;
        for (i = 0; i < size_in; ++i) {
            double now = INPUT(in[i]);
            if (CALL_TYPE == ANALOG) values[i] = now;
            if (TIME > 0.0 && T(1) < TIME && isfinite(now) && isfinite(previous[i])) {
                double thresholds[2] = {in_low, in_high};
                for (int j = 0; j < 2; ++j) {
                    double level = thresholds[j];
                    if ((previous[i] <= level && now > level) ||
                        (previous[i] >= level && now < level)) {
                        double fraction = (level - previous[i]) / (now - previous[i]);
                        double crossing = T(1) + fraction * (TIME - T(1));
                        /* Step just beyond equality without changing voltage thresholds. */
                        crossing = nextafter(crossing, TIME);
                        if (crossing <= T(1) || previous[i] == level) crossing = (T(1) + TIME) / 2.0;
                        if (crossing > T(1) && crossing < earliest) earliest = crossing;
                    }
                }
            }
        }
        if (earliest < TIME && !cm_analog_set_temp_bkpt(earliest)) {
            if (CALL_TYPE == EVENT)
                for (i = 0; i < size_out; ++i) OUTPUT_CHANGED(out[i]) = FALSE;
            return;
        }
    }


    switch (CALL_TYPE) {
        case ANALOG:    /** analog call...check for breakpoint calls. **/
            /* loop through all inputs... */

            for (i = 0; i < size_out; i++) {
                test = get_out_value(INPUT(in[i]), in_low, in_high);
                if (getenv("ROBOTRON_LIVE_EVENTS") && TIME > .001005011 && TIME < .001005014 && test != out[i])
                    cm_message_printf("ADC_LIVE time=%a node=%s value=%a old=%d new=%d call=%d", TIME, cm_get_node_name("in", i), INPUT(in[i]), out[i], test, CALL_TYPE);
                if (test != out[i]) {
                    /* call for event breakpoint... */

                    cm_event_queue(TIME);
                    break;
                }
            }
            break;

        case EVENT:    /** discrete call...lots to do **/
            /* loop through all inputs... */

            for (i = 0; i < size_out; i++) {
                test = get_out_value(INPUT(in[i]), in_low, in_high);
                if (getenv("ROBOTRON_LIVE_EVENTS") && TIME > .001005011 && TIME < .001005014 && test != out[i])
                    cm_message_printf("ADC_LIVE time=%a node=%s value=%a old=%d new=%d call=%d", TIME, cm_get_node_name("in", i), INPUT(in[i]), out[i], test, CALL_TYPE);
                if (test != out[i]) {
                    if (getenv("ROBOTRON_ADC_TRACE"))
                        cm_message_printf("ADC_CROSS time=%a node=%s value=%a old=%d new=%d", TIME, cm_get_node_name("in", i), INPUT(in[i]), out[i], test);
                    /* Post changed value. */

                    OUTPUT_STATE(out[i]) = test;
                    switch (test) {
                    case ZERO:
                        OUTPUT_DELAY(out[i]) = PARAM(fall_delay);
                        break;
                    case ONE:
                        OUTPUT_DELAY(out[i]) = PARAM(rise_delay);
                        break;
                    default:
                        if (in_low > in_high) {
                            /* Input is in hysteresis band. */

                            OUTPUT_CHANGED(out[i]) = FALSE;
                            continue;
                        }
                        if (out[i] == ZERO)
                            OUTPUT_DELAY(out[i]) = PARAM(rise_delay);
                        else
                            OUTPUT_DELAY(out[i]) = PARAM(fall_delay);
                        break;
                    }
                    out[i] = test;
                    /* Regardless, output the strength */

                    OUTPUT_STRENGTH(out[i]) = STRONG;
                } else {
                    /* no change since last time */

                    OUTPUT_CHANGED(out[i]) = FALSE;
                }
            }
            break;
        default:
            break;
    }
}
