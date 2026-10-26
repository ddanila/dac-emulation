/* Exact floor(target/tick) for nonnegative finite binary64 values.
 * Integer arithmetic avoids history-dependent subtraction before truncation.
 * No epsilon, upward rounding, or clock-grid alignment is applied. */
#include <math.h>
#include <stdint.h>
static int robotron_absolute_ticks(double target, double tick, uint64_t *result)
{
    if (!result || !isfinite(target) || !isfinite(tick) || target<0 || tick<=0) return -1;
    if (target==0) { *result=0; return 0; }
    int te, ue;
    uint64_t tm=(uint64_t)ldexp(frexp(target,&te),53);
    uint64_t um=(uint64_t)ldexp(frexp(tick,&ue),53);
    int shift=te-ue;
    if (shift<0) { *result=0; return 0; }
    if (shift>64) return -1;
    __uint128_t quotient=((__uint128_t)tm<<shift)/um;
    if (quotient>UINT64_MAX) return -1;
    *result=(uint64_t)quotient;
    return 0;
}
