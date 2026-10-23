/* Experimental exact-rational correction of constant-capacitor additions.
 * Other device stamps and previously stored histories remain binary64.
 * Include once, in spsmp.c after mpfr_linear_solver.h.
 */
#ifndef ROBOTRON_CAPACITOR_ASSEMBLY_H
#define ROBOTRON_CAPACITOR_ASSEMBLY_H
#include <string.h>
#include <stdio.h>

typedef struct { int row, col; mpq_t value; } RobotronCapEntry;
static RobotronCapEntry cap_entries[4096];
static int cap_used, cap_initialized;

int RobotronCapReset(void)
{
    static int mode = -1;
    if (mode == -1) {
        const char *value = getenv("ROBOTRON_CAP_ASSEMBLY");
        mode = (!value || !strcmp(value, "off")) ? 0 : !strcmp(value, "exact") ? 1 : !strcmp(value, "paired-rhs") ? 2 : -2;
        if (mode > 0) {
            const char *bits = getenv("ROBOTRON_MPFR_BITS");
            if (!bits || (strcmp(bits,"256") && strcmp(bits,"512"))) mode = -2;
        }
        fprintf(stderr, "CAP_ASSEMBLY mode=%d\n", mode);
    }
    cap_used = 0;
    return mode;
}

static int robotron_cap_entry(int row, int col, mpq_t exact, int sign,
                              double before, double after)
{
    mpq_t change, old;
    RobotronCapEntry *entry;
    if (!row || !col) return 0; /* Ground; RHS uses column -1. */
    if (row < 0 || col < -1 || cap_used >= 4096 || !isfinite(before) || !isfinite(after)) return 1;
    entry = &cap_entries[cap_used];
    if (cap_used == cap_initialized) { mpq_init(entry->value); ++cap_initialized; }
    ++cap_used;
    entry->row = row; entry->col = col;
    mpq_inits(change, old, NULL);
    mpq_set_d(change, after); mpq_set_d(old, before); mpq_sub(change, change, old);
    mpq_set(entry->value, exact);
    if (sign < 0) mpq_neg(entry->value, entry->value);
    mpq_sub(entry->value, entry->value, change);
    mpq_clears(change, old, NULL);
    return 0;
}

int RobotronCapAdd(int p, int n, int order, double m, double capacitance,
                   double ag0, double ag1, double q1, double i1,
                   const double *before, const double *after)
{
    mpq_t g, b, factor, temp;
    int result = 0;
    if (p == n || p < 0 || n < 0 || (order != 1 && order != 2) || m <= 0 || capacitance <= 0 ||
        !isfinite(m) || !isfinite(capacitance) || !isfinite(ag0) || !isfinite(ag1) ||
        !isfinite(q1) || !isfinite(i1)) return 1;
    mpq_inits(g,b,factor,temp,NULL);
    mpq_set_d(g, ag0); mpq_set_d(factor, capacitance); mpq_mul(g,g,factor);
    mpq_set_d(factor,m); mpq_mul(g,g,factor);
    mpq_set_d(b,ag1); mpq_set_d(temp,order == 1 ? q1 : i1); mpq_mul(b,b,temp);
    if (order == 2) {
        mpq_neg(b,b); mpq_set_d(temp,ag0); mpq_set_d(factor,q1);
        mpq_mul(temp,temp,factor); mpq_sub(b,b,temp);
    }
    mpq_set_d(factor,m); mpq_mul(b,b,factor);
    result |= robotron_cap_entry(p,p,g,1,before[0],after[0]);
    result |= robotron_cap_entry(n,n,g,1,before[1],after[1]);
    result |= robotron_cap_entry(p,n,g,-1,before[2],after[2]);
    result |= robotron_cap_entry(n,p,g,-1,before[3],after[3]);
    result |= robotron_cap_entry(p,-1,b,-1,before[4],after[4]);
    result |= robotron_cap_entry(n,-1,b,1,before[5],after[5]);
    mpq_clears(g,b,factor,temp,NULL);
    return result;
}

/* Preserve only paired RHS additions; integration and conductance stay binary64. */
int RobotronCapPairRhs(int p, int n, double history, const double *before, const double *after)
{
    mpq_t b;
    int result;
    if (!p || !n) return 0;
    if (p == n || p < 0 || n < 0 || !isfinite(history)) return 1;
    mpq_init(b); mpq_set_d(b,history);
    result = robotron_cap_entry(p,-1,b,-1,before[4],after[4]);
    result |= robotron_cap_entry(n,-1,b,1,before[5],after[5]);
    mpq_clear(b);
    return result;
}

static int robotron_cap_apply(RobotronMpfr *solver)
{
    for (int i=0; i<cap_used; ++i) {
        RobotronCapEntry *e = &cap_entries[i];
        int col = e->col == -1 ? solver->n : e->col-1;
        if (e->row > solver->n || col > solver->n) return 1;
        mpfr_set_q(solver->sum, e->value, MPFR_RNDN);
        mpfr_add(solver->cells[(size_t)(e->row-1)*(solver->n+1)+col],
                 solver->cells[(size_t)(e->row-1)*(solver->n+1)+col], solver->sum, MPFR_RNDN);
    }
    return 0;
}
#endif
