#ifndef DAC_RUNTIME_PC1715_H
#define DAC_RUNTIME_PC1715_H
#include "session.h"
#include "../../machines/robotron1715/pc1715.h"
/* Native model attachment, kind 3 only, power off. Borrowed context survives
 * power/reset; the host must keep it alive until detached or destroyed. */
int dac_pc1715_attach(dac_session *, const pc1715_card *);
#endif
