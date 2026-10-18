#include <limits.h>
#define SCENARIO_CYCLES 130000u
static const struct { unsigned cycle, index, closed; } contact_events[] = {
{4000, 65, 1},
{6000, 61, 1},
{40000, 61, 0},
{42000, 65, 0},
{70000, 61, 1},
{100000, 61, 0},
{UINT_MAX, 0, 0}
};
static const struct { unsigned cycle, asserted; } reset_events[] = {
{UINT_MAX, 0}
};
