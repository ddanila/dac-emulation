#include <limits.h>
#define SCENARIO_CYCLES 220000u
static const struct { unsigned cycle, index, closed; } contact_events[] = {
{4000, 71, 1},
{29000, 71, 0},
{45000, 69, 1},
{70000, 69, 0},
{90000, 71, 1},
{115000, 71, 0},
{135000, 69, 1},
{160000, 69, 0},
{180000, 61, 1},
{205000, 61, 0},
{UINT_MAX, 0, 0}
};
static const struct { unsigned cycle, asserted; } reset_events[] = {
{UINT_MAX, 0}
};
