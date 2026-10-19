#include <limits.h>
#define SCENARIO_CYCLES 120000u
static const struct { unsigned cycle, index, closed; } contact_events[] = {
{4000, 61, 1},
{30000, 61, 0},
{60000, 61, 1},
{90000, 61, 0},
{UINT_MAX, 0, 0}
};
static const struct { unsigned cycle, asserted; } reset_events[] = {
{UINT_MAX, 0}
};
