#include "ngspice/ngspice.h"
#include "ngspice/cktdefs.h"
#include <stddef.h>
int main(void) { printf("%zu %zu\n", sizeof(CKTcircuit), offsetof(CKTcircuit, CKTminBreak)); return 0; }
