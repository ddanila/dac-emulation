/* Operational capture limit only. Never changes equations or timesteps. */
#ifndef ROBOTRON_ACCEPTED_BUDGET_H
#define ROBOTRON_ACCEPTED_BUDGET_H
#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
    unsigned long limit, count;
    double after;
} RobotronAcceptedBudget;
static int robotron_budget_init(RobotronAcceptedBudget *b, const char *limit,
                                const char *after) {
    char *end;
    b->limit = b->count = 0;
    b->after = 0;
    if (!limit && !after) return 0;
    if (!limit || !after || !*limit || !*after ||
        strspn(limit, "0123456789") != strlen(limit)) return -1;
    errno = 0;
    b->limit = strtoul(limit, &end, 10);
    if (errno || *end || !b->limit) return -1;
    errno = 0;
    b->after = strtod(after, &end);
    if (errno || *end || !isfinite(b->after) || b->after < 0) return -1;
    return 0;
}
static int robotron_budget_hit(RobotronAcceptedBudget *b, double time) {
    if (!b->limit || time < b->after) return 0;
    if (b->count < b->limit) ++b->count;
    return b->count == b->limit;
}
#endif
