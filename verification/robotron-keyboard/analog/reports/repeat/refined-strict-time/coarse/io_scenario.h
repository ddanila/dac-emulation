#include <limits.h>
#define SCENARIO_CYCLES 1600000u
static const struct { unsigned cycle, index, closed; } contact_events[] = {
{4000, 61, 1},
{30000, 70, 1},
{1500000, 70, 0},
{1510000, 61, 0},
{UINT_MAX, 0, 0}
};
static const struct { unsigned cycle, asserted; } reset_events[] = {
{UINT_MAX, 0}
};
