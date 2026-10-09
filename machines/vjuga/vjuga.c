#include "vjuga.h"
#include <errno.h>
#include <string.h>
static int overlay(vjuga *m, uint16_t a) {
  if (m->decode_mode)
    return a < 0x4000;
  switch (m->portc & 3) {
  case 0:
    return a < 0x4000;
  case 1:
    return a >= 0xd800;
  case 2:
    return a >= 0xd800 || (a >= 0x4000 && a < 0xc000);
  default:
    return 0;
  }
}
uint8_t vjuga_read(void *p, uint16_t a) {
  vjuga *m = p;
  if (!m->decode_mode && (m->portc & 3) == 2 && a >= 0x4000 && a < 0xc000)
    return 0xff;
  if (overlay(m, a))
    return m->rom[((m->portc & 3) == 0 ? a : 0x1800 + (a - 0xd800)) & 0x3fff];
  return m->ram[a];
}
void vjuga_write(void *p, uint16_t a, uint8_t d) {
  vjuga *m = p;
  if (overlay(m, a) ||
      (!m->decode_mode && (m->portc & 3) == 2 && a >= 0x4000 && a < 0xc000))
    return;
  m->ram[a] = d;
  if (a >= 0xd800)
    m->video_writes++;
}
static uint8_t input(void *p, uint16_t a) {
  return ((vjuga *)p)->ports[a & 255];
}
static void output(void *p, uint16_t a, uint8_t d) {
  vjuga *m = p;
  a &= 255;
  m->ports[a] = d;
  if (a == 6)
    m->portc = d;
  if (a == 7) {
    if (d & 128)
      m->portc = 0;
    else {
      unsigned bit = (d >> 1) & 7;
      m->portc = (m->portc & ~(1u << bit)) | ((d & 1) << bit);
    }
  }
}
void vjuga_init(vjuga *m, unsigned mode) {
  memset(m, 0, sizeof(*m));
  m->decode_mode = mode != 0;
  dac_z80_init(&m->cpu,
               (dac_z80_bus){m, vjuga_read, vjuga_write, input, output, 0});
}
int vjuga_load_rom(vjuga *m, const void *p, size_t n) {
  if (!m || !p || n != sizeof(m->rom))
    return -EINVAL;
  if (m->cpu.cycles)
    return -EBUSY;
  memcpy(m->rom, p, n);
  return 0;
}
void vjuga_run(vjuga *m, unsigned n) {
  while (n--)
    dac_z80_tick(&m->cpu, 0, 0);
}
