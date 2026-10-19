/* Experimental real linear solve; MPFR round-to-nearest, partial row pivoting.
 * Stamped inputs and returned simulator states remain binary64.
 */
#ifndef ROBOTRON_MPFR_LINEAR_SOLVER_H
#define ROBOTRON_MPFR_LINEAR_SOLVER_H
#include <mpfr.h>
#include <math.h>
#include <stdlib.h>

typedef struct {
    int n;
    mpfr_prec_t precision;
    mpfr_t *cells;
    int *rows, *tail;
    mpfr_t factor, product, sum;
} RobotronMpfr;

static void robotron_mpfr_destroy(RobotronMpfr *s)
{
    if (!s->cells) return;
    for (size_t i = 0; i < (size_t)s->n*(s->n+1); ++i) mpfr_clear(s->cells[i]);
    mpfr_clears(s->factor, s->product, s->sum, (mpfr_ptr)0);
    free(s->cells); free(s->rows); free(s->tail);
    s->cells = NULL;
}

static int robotron_mpfr_init(RobotronMpfr *s, int n, mpfr_prec_t precision)
{
    if (n < 1 || n > 4096 || precision < 64 || precision > 2048) return 1;
    if (s->cells && s->n == n && s->precision == precision) return 0;
    robotron_mpfr_destroy(s);
    s->n = n; s->precision = precision;
    s->cells = calloc((size_t)n*(n+1), sizeof(mpfr_t));
    s->rows = calloc((size_t)n, sizeof(int));
    s->tail = calloc((size_t)n+1, sizeof(int));
    if (!s->cells || !s->rows || !s->tail) {
        free(s->cells); free(s->rows); free(s->tail); s->cells = NULL;
        return 1;
    }
    for (size_t i = 0; i < (size_t)n*(n+1); ++i) mpfr_init2(s->cells[i], precision);
    mpfr_inits2(precision, s->factor, s->product, s->sum, (mpfr_ptr)0);
    return 0;
}

static void robotron_mpfr_reset(RobotronMpfr *s)
{
    for (size_t i = 0; i < (size_t)s->n*(s->n+1); ++i) mpfr_set_zero(s->cells[i], 1);
    for (int i = 0; i < s->n; ++i) s->rows[i] = i;
}

static int robotron_mpfr_set(RobotronMpfr *s, int row, int col, double value)
{
    if (row < 0 || row >= s->n || col < 0 || col > s->n || !isfinite(value)) return 1;
    mpfr_set_d(s->cells[(size_t)row*(s->n+1)+col], value, MPFR_RNDN);
    return 0;
}

static int robotron_mpfr_solve(RobotronMpfr *s, double *solution)
{
    int n = s->n;
    for (int k = 0; k < n; ++k) {
        int pivot = k;
        for (int i = k+1; i < n; ++i)
            if (mpfr_cmpabs(s->cells[(size_t)s->rows[i]*(n+1)+k],
                            s->cells[(size_t)s->rows[pivot]*(n+1)+k]) > 0) pivot = i;
        if (mpfr_zero_p(s->cells[(size_t)s->rows[pivot]*(n+1)+k])) return 2;
        int swap = s->rows[k]; s->rows[k] = s->rows[pivot]; s->rows[pivot] = swap;
        mpfr_t *upper = s->cells+(size_t)s->rows[k]*(n+1);
        int count = 0;
        for (int j = k+1; j <= n; ++j) if (!mpfr_zero_p(upper[j])) s->tail[count++] = j;
        for (int i = k+1; i < n; ++i) {
            mpfr_t *row = s->cells+(size_t)s->rows[i]*(n+1);
            if (mpfr_zero_p(row[k])) continue;
            mpfr_div(s->factor, row[k], upper[k], MPFR_RNDN);
            mpfr_set_zero(row[k], 1);
            for (int index = 0; index < count; ++index) {
                int j = s->tail[index];
                mpfr_mul(s->product, s->factor, upper[j], MPFR_RNDN);
                mpfr_sub(row[j], row[j], s->product, MPFR_RNDN);
            }
        }
    }
    for (int i = n-1; i >= 0; --i) {
        mpfr_t *row = s->cells+(size_t)s->rows[i]*(n+1);
        mpfr_set(s->sum, row[n], MPFR_RNDN);
        for (int j = i+1; j < n; ++j) {
            if (mpfr_zero_p(row[j])) continue;
            mpfr_mul(s->product, row[j], s->cells[(size_t)s->rows[j]*(n+1)+n], MPFR_RNDN);
            mpfr_sub(s->sum, s->sum, s->product, MPFR_RNDN);
        }
        mpfr_div(row[n], s->sum, row[i], MPFR_RNDN);
        solution[i+1] = mpfr_get_d(row[n], MPFR_RNDN);
        if (!isfinite(solution[i+1])) return 3;
    }
    return 0;
}
#endif
