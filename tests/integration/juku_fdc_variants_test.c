/* CPU-visible DAL polarity: FD1791 versus FD1793, independent of ROM identity. */
#include "juku_internal.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t io(juku *j, int write, unsigned reg, uint8_t logical) {
  j->ram[0x4000] = write ? 0xd3 : 0xdb;
  j->ram[0x4001] = (uint8_t)(0x1c + reg);
  j->cpu.pc = 0x4000;
  j->cpu.a = j->fdc_bus_invert ? (uint8_t)~logical : logical;
  unsigned long start = j->cpu.cyc;
  do { juku_step(j); } while (j->cpu.io_pending && j->cpu.cyc-start < 2000000);
  assert(!j->cpu.io_pending && j->cpu.pc == 0x4002);
  return j->fdc_bus_invert ? (uint8_t)~j->cpu.a : j->cpu.a;
}
static void ready(juku *j) {
  unsigned long start = j->cpu.cyc;
  while (!(io(j,0,0,0) & 2) && j->cpu.cyc-start < 2000000) {}
  assert(j->fdc.status & 2);
}
int main(void) {
  uint8_t *disk = malloc(819200); assert(disk);
  for (unsigned i=0;i<819200;i++) disk[i]=(uint8_t)(i^(i>>8));
  for (unsigned inverted=0;inverted<2;inverted++) {
    juku *j=juku_create(); assert(j);
    assert(!juk_disk_bind(&j->disk,dac_memory_storage(disk,819200,1),2,1));
    juku_fdc_init(&j->fdc,&j->disk);j->fdc_enabled=1;j->mode=3;
    j->fdc_bus_invert=(int)inverted;j->cpu.iff=0;
    juku_fdc_portc(&j->fdc,4);
    /* Data, sector and track registers exercise every DAL pattern. */
    for (unsigned reg=1;reg<4;reg++) for (unsigned value=0;value<256;value++) {
      io(j,1,reg,(uint8_t)value);assert(io(j,0,reg,0)==value);
    }
    io(j,1,1,0);io(j,1,2,1);io(j,1,0,0x80);
    assert(j->fdc.command==0x80);
    for (unsigned i=0;i<512;i++) {ready(j);assert(io(j,0,3,0)==disk[i]);}
    assert(!(io(j,0,0,0)&0x1d));
    uint8_t expected[512];for(unsigned i=0;i<512;i++)expected[i]=(uint8_t)(i*13+inverted);
    io(j,1,2,2);io(j,1,0,0xa0);
    assert(j->fdc.command==0xa0);
    for(unsigned i=0;i<512;i++){ready(j);io(j,1,3,expected[i]);}
    assert(!(io(j,0,0,0)&0x1d));assert(!memcmp(disk+512,expected,512));
    io(j,1,2,2);io(j,1,0,0x80);
    for(unsigned i=0;i<512;i++){ready(j);assert(io(j,0,3,0)==expected[i]);}
    assert(!(io(j,0,0,0)&0x1d));juku_destroy(j);
  }
  free(disk);puts("PASS: FD1791/1793 CPU bus polarity, all DAL patterns and sector read/write");
}
