/* Experimental NIintegrate arithmetic; stored states and coefficients remain doubles.
 * Caller must serialize access (the experimental runtime disables OpenMP).
 * method: 0 = trapezoidal, 1 = Gear. Results: derivative, companion RHS, diagonal.
 */
#ifndef ROBOTRON_MPFR_INTEGRATION_H
#define ROBOTRON_MPFR_INTEGRATION_H
#include <math.h>
#include <mpfr.h>

static int robotron_mpfr_integrate(int method, int order, const double *ag,
                                  const double *q, double previous_derivative,
                                  double capacitance, double result[3])
{
    static int initialized;
    static mpfr_t history, product, left, right, derivative;
    int i;
    double values[3];
    if ((method != 0 && method != 1) || order < 1 || order > (method ? 6 : 2)
        || !isfinite(capacitance) || !isfinite(previous_derivative)) return 1;
    for (i = 0; i <= order; ++i)
        if (!isfinite(ag[i]) || !isfinite(q[i])) return 1;
    if (!initialized) {
        mpfr_inits2(256, history, product, left, right, derivative, (mpfr_ptr)0);
        initialized = 1;
    }
    mpfr_set_zero(history, 0);
    if (!method && order == 2) {
        mpfr_set_d(left, ag[1], MPFR_RNDN);
        mpfr_set_d(right, previous_derivative, MPFR_RNDN);
        mpfr_mul(history, left, right, MPFR_RNDN);
        mpfr_neg(history, history, MPFR_RNDN);
        mpfr_set_d(left, ag[0], MPFR_RNDN);
        mpfr_set_d(right, q[1], MPFR_RNDN);
        mpfr_mul(product, left, right, MPFR_RNDN);
        mpfr_sub(history, history, product, MPFR_RNDN);
    } else {
        for (i = order; i >= 1; --i) {
            mpfr_set_d(left, ag[i], MPFR_RNDN);
            mpfr_set_d(right, q[i], MPFR_RNDN);
            mpfr_mul(product, left, right, MPFR_RNDN);
            mpfr_add(history, history, product, MPFR_RNDN);
        }
    }
    mpfr_set_d(left, ag[0], MPFR_RNDN);
    mpfr_set_d(right, q[0], MPFR_RNDN);
    mpfr_mul(product, left, right, MPFR_RNDN);
    mpfr_add(derivative, history, product, MPFR_RNDN);
    values[0] = mpfr_get_d(derivative, MPFR_RNDN);
    values[1] = mpfr_get_d(history, MPFR_RNDN);
    mpfr_set_d(right, capacitance, MPFR_RNDN);
    mpfr_mul(product, left, right, MPFR_RNDN);
    values[2] = mpfr_get_d(product, MPFR_RNDN);
    for (i = 0; i < 3; ++i) if (!isfinite(values[i])) return 2;
    for (i = 0; i < 3; ++i) result[i] = values[i];
    return 0;
}
#endif
