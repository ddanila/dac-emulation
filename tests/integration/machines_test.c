#include "../../machines/robotron1715m/robotron.h"
#include "../../machines/vjuga/vjuga.h"
#include "../../runners/browser/dac.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void banks(void) {
  robotron *m = malloc(sizeof(*m));
  assert(m);
  robotron_init(m);
  m->prom[128 + 16 + 4] = 13; /* bank1 page4 -> physical RAM1 */
  robotron_output(m, 0x24, 0x11);
  robotron_write(m, 0x4000, 0xa5);
  assert(m->ram[65536 + 0x4000] == 0xa5);
  assert(robotron_read(m, 0x4000) == 0xa5);
  robotron_output(m, 0x24, 0x01);
  robotron_write(m, 0x4000, 0x5a);
  assert(m->ram[0x4000] == 0x5a);
  assert(robotron_read(m, 0x4000) == 0xa5);
  robotron_output(m, 0x24, 0);
  m->rom[4] = 0x42;
  robotron_write(m, 4, 0xff);
  assert(robotron_read(m, 4) == 0x42);
  robotron_write(m, 0x3000, 0x44);
  assert(m->vram[0] == 0x44);
  free(m);
}
static void floppy(void) {
  robotron *m = malloc(sizeof(*m));
  uint8_t *data = calloc(1, 819200);
  assert(m && data);
  robotron_init(m);
  for (unsigned i = 0; i < 1024; i++)
    data[i] = (uint8_t)i;
  assert(robotron_disk(m, dac_memory_storage(data, 819200, 1), 1) == 0);
  const uint8_t read[] = {0x46, 0, 0, 0, 1, 3, 1, 0x1b, 0xff};
  for (unsigned i = 0; i < sizeof(read); i++)
    robotron_output(m, 0x1d, read[i]);
  m->cpu.cycles = m->fdc.ready_at;
  assert((robotron_input(m, 0x1c) & 0xc0) == 0xc0);
  for (unsigned i = 0; i < 1024; i++) {
    m->cpu.cycles = m->fdc.ready_at;
    assert(robotron_input(m, 0x1d) == (uint8_t)i);
  }
  assert(m->disk_reads == 1);
  assert(robotron_input(m, 0x1d) == 0x40);
  assert(robotron_input(m, 0x1d) == 0x80); /* EOT without TC */
  for (unsigned i = 0; i < 5; i++)
    robotron_input(m, 0x1d);
  const uint8_t write[] = {0x45, 0, 0, 0, 1, 3, 1, 0x1b, 0xff};
  for (unsigned i = 0; i < sizeof(write); i++)
    robotron_output(m, 0x1d, write[i]);
  m->cpu.cycles = m->fdc.ready_at;
  for (unsigned i = 0; i < 1024; i++) {
    m->cpu.cycles = m->fdc.ready_at;
    robotron_output(m, 0x1d, 0xa5);
  }
  assert(m->disk_writes == 1);
  for (unsigned i = 0; i < 1024; i++)
    assert(data[i] == 0xa5);
  for (unsigned i = 0; i < 7; i++)
    robotron_input(m, 0x1d);
  uint8_t scan[9];
  memcpy(scan, write, 9);
  scan[0] = 0x51;
  for (unsigned i = 0; i < 9; i++)
    robotron_output(m, 0x1d, scan[i]);
  m->cpu.cycles = m->fdc.ready_at;
  for (unsigned i = 0; i < 1024; i++) {
    m->cpu.cycles = m->fdc.ready_at;
    robotron_output(m, 0x1d, 0xa5);
  }
  assert(robotron_input(m, 0x1d) == 0);
  assert(robotron_input(m, 0x1d) == 0);
  assert(robotron_input(m, 0x1d) == 8);
  for (unsigned i = 0; i < 4; i++)
    robotron_input(m, 0x1d);

  for (unsigned i = 0; i < 7; i++)
    robotron_input(m, 0x1d);
  assert(robotron_disk(m, dac_memory_storage(data, 819200, 0), 0) == 0);
  for (unsigned i = 0; i < sizeof(write); i++)
    robotron_output(m, 0x1d, write[i]);
  assert(robotron_input(m, 0x1d) & 0x40);
  assert(robotron_input(m, 0x1d) == 2);
  /* An invalid size code must return an error, never shift/overflow. */
  for (unsigned i = 0; i < 5; i++)
    robotron_input(m, 0x1d);
  uint8_t invalid[9];
  memcpy(invalid, read, 9);
  invalid[5] = 255;
  for (unsigned i = 0; i < 9; i++)
    robotron_output(m, 0x1d, invalid[i]);
  assert(robotron_input(m, 0x1d) & 0x40);
  assert(robotron_input(m, 0x1d) == 4);
  free(data);
  free(m);
}
static void z80_instances(void) {
  vjuga *a = malloc(sizeof(*a)), *b = malloc(sizeof(*b));
  assert(a && b);
  vjuga_init(a, 0);
  vjuga_init(b, 0);
  /* LD IX,C000; LD (IX+2),5A; BIT 0,(IX+2); HALT: Z80-only prefixes. */
  const uint8_t p[] = {0xdd, 0x21, 0x00, 0xc0, 0xdd, 0x36, 2,
                       0x5a, 0xdd, 0xcb, 2,    0x46, 0x76};
  memcpy(a->rom, p, sizeof(p));
  memcpy(b->rom, p, sizeof(p));
  b->rom[7] = 0xa5;
  vjuga_run(a, 100);
  vjuga_run(b, 100);
  assert(a->ram[0xc002] == 0x5a && b->ram[0xc002] == 0xa5);
  assert((a->cpu.cpu.f & Z80_ZF) && !(b->cpu.cpu.f & Z80_ZF));
  assert(a->cpu.pins & Z80_HALT);
  uint64_t n = a->cpu.cycles;
  vjuga_run(a, 31);
  assert(a->cpu.cycles == n + 31);
  free(a);
  free(b);
}
int main(void) {
  banks();
  floppy();
  z80_instances();
  puts("PASS: Z80 isolation/prefixes/HALT, Robotron banking and FDC "
       "read/write/errors");
}
