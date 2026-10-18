#include <limits.h>
#define SCENARIO_CYCLES 29000u
static const struct { unsigned cycle, index, closed; } contact_events[] = {
{4000, 61, 1},
{UINT_MAX, 0, 0}
};
static const struct { unsigned cycle, asserted; } reset_events[] = {
{UINT_MAX, 0}
};
