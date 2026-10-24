/* Pure single-bit slew state. The caller owns accepted/trial snapshots. */
#ifndef ROBOTRON_DAC_ANCHOR_H
#define ROBOTRON_DAC_ANCHOR_H
#include <math.h>
typedef struct { double origin, value, target; } RobotronDacRamp;
static double robotron_dac_value(const RobotronDacRamp *r, double time,
                                double rise, double fall)
{
    double elapsed = fmax(0.0, time - r->origin);
    if (r->value < r->target)
        return fmin(r->target, r->value + rise * elapsed);
    return fmax(r->target, r->value - fall * elapsed);
}
static RobotronDacRamp robotron_dac_trial(const RobotronDacRamp *accepted,
    double time, double changed, double target, double rise, double fall)
{
    RobotronDacRamp trial = *accepted;
    if (target != accepted->target && changed <= time) {
        trial.value = robotron_dac_value(accepted, changed, rise, fall);
        trial.origin = changed;
        trial.target = target;
    }
    return trial;
}
#endif
