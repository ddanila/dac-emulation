/* Experimental board contract: real CPU IN/OUT, no instruction retries. */
#include "juku_internal.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static juku *machine(uint8_t *disk, int writable) {
  juku *j=juku_create();assert(j && j->cpu.io_ready);
  assert(!juk_disk_bind(&j->disk,dac_memory_storage(disk,819200,writable),2,writable));
  juku_fdc_init(&j->fdc,&j->disk);j->fdc_enabled=1;j->mode=3;
  j->cpu.iff=0;juku_fdc_portc(&j->fdc,4);
  return j;
}
static uint8_t io(juku *j, int write, uint8_t port, uint8_t value) {
  j->ram[0x4000]=write?0xd3:0xdb;j->ram[0x4001]=port;
  j->cpu.pc=0x4000;j->cpu.a=value;
  unsigned long start=j->cpu.cyc;juku_step(j);
  assert(j->cpu.io_pending && j->cpu.pc==0x4002);
  while(j->cpu.io_pending && j->cpu.cyc-start<2000000)juku_step(j);
  assert(!j->cpu.io_pending && j->cpu.pc==0x4002);
  return j->cpu.a;
}
static void command(juku *j,uint8_t c,uint8_t sector) {
  io(j,1,0x1e,sector);io(j,1,0x1c,c);
}
static void transfer(juku *j,int write,uint8_t sector,uint8_t *data) {
  command(j,write?0xa0:0x80,sector);
  for(unsigned i=0;i<512;i++) {
    uint8_t value=io(j,write,0x1f,data[i]);if(!write)data[i]=value;
  }
  assert(!(io(j,0,0x1c,0)&0x1d));
}
int main(void) {
  uint8_t *disk=malloc(819200), *original=malloc(819200);assert(disk&&original);
  for(unsigned i=0;i<819200;i++)disk[i]=(uint8_t)(i*37+(i>>9));
  memcpy(original,disk,819200);juku *j=machine(disk,1);
  uint8_t data[512];memset(data,0,sizeof(data));transfer(j,0,1,data);
  assert(!memcmp(data,disk,512));
  for(unsigned clock=0;clock<2;clock++) {
    juku_fdc_portc(&j->fdc,(uint8_t)(4|clock*8));
    for(unsigned i=0;i<512;i++)data[i]=(uint8_t)(i^0xa7^clock);
    unsigned long before=j->cpu.cyc;transfer(j,1,2,data);
    printf("write ticks %lu\n",j->cpu.cyc-before);assert(j->cpu.cyc-before>=1408+510*64);
    uint8_t got[512]={0};transfer(j,0,2,got);assert(!memcmp(got,data,512));
  }
  assert(!memcmp(disk,original,512));assert(!memcmp(disk+1024,original+1024,819200-1024));
  juku_destroy(j);j=machine(disk,1); // remount persistence
  uint8_t got[512]={0};transfer(j,0,2,got);assert(!memcmp(got,data,512));
  command(j,0xc0,1);for(unsigned i=0;i<6;i++)io(j,0,0x1f,0);
  assert(!(j->fdc.status&1));
  command(j,0xe0,1);for(unsigned i=0;i<JUK_MFM_TRACK_SIZE;i++)io(j,0,0x1f,0);
  assert(!(j->fdc.status&0x1d));
  // Multiple record reads cross a sector boundary, then report RNF after
  // the final track ID rather than fabricating an eleventh sector.
  command(j,0x90,9);
  for(unsigned i=0;i<1024;i++)assert(io(j,0,0x1f,0)==disk[4096+i]);
  io(j,0,0x1f,0);assert((j->fdc.status&0x11)==0x10);
  // A missing ID finishes after index events, releasing a pending IN.
  command(j,0x80,11);io(j,0,0x1f,0);
  assert((j->fdc.status&0x11)==0x10 && j->fdc.intrq);
  io(j,0,0x1c,0);assert(!j->fdc.intrq);
  // Lost-data remains visible when the CPU fails to service a byte.
  command(j,0x80,1);j->cpu.cyc+=65;juku_step_devices(j);assert(j->fdc.status&4);
  io(j,1,0x1c,0xd0);assert(!(j->fdc.status&1));
  // A blocked bus cannot acknowledge an interrupt. Force completion at the
  // controller boundary to model an external abort, not a guest OUT in wait.
  command(j,0x84,1);j->ram[0x4000]=0xdb;j->ram[0x4001]=0x1f;j->cpu.pc=0x4000;
  juku_step(j);j->cpu.iff=1;j->scanout.irq_pending=1;j->pic_mask=0;
  unsigned long irq=j->frame_irq_count,cycle=j->cpu.cyc;
  juku_run(j,100);assert(j->cpu.io_pending && j->frame_irq_count==irq && j->cpu.cyc==cycle+100);
  juku_fdc_write(&j->fdc,0,0xd0);juku_step(j);
  assert(!j->cpu.io_pending && j->frame_irq_count>irq);
  juku_destroy(j);j=machine(disk,0);
  command(j,0xa0,2);io(j,1,0x1f,0x11);assert(j->fdc.status&0x40);
  assert(!memcmp(disk+512,data,512));
  juku_fdc_ready(&j->fdc,0);command(j,0x80,1);io(j,0,0x1f,0);assert(j->fdc.status&0x80);
  juku_destroy(j);j=machine(disk,1);
  command(j,0xb0,9);
  for(unsigned i=0;i<1024;i++)io(j,1,0x1f,(uint8_t)(i*13));
  io(j,1,0x1f,0);assert((j->fdc.status&0x11)==0x10);
  for(unsigned i=0;i<1024;i++)assert(disk[4096+i]==(uint8_t)(i*13));
  // A complete formatted track through CPU OUTs, including preload/index
  // waiting and generated CRC tokens. No direct controller buffer mutation.
  command(j,0xf0,1);unsigned count=0;
  #define BYTE(v) do {uint8_t b=(v);io(j,1,0x1f,b);count+=b==0xf7?2:1;} while(0)
  for(unsigned sector=1;sector<=10;sector++) {
    BYTE(0xf5);BYTE(0xf5);BYTE(0xf5);BYTE(0xfe);
    BYTE(0);BYTE(0);BYTE(sector);BYTE(2);BYTE(0xf7);
    BYTE(0x4e);BYTE(0xf5);BYTE(0xf5);BYTE(0xf5);BYTE(0xfb);
    for(unsigned i=0;i<512;i++){BYTE(0xe5);}
    BYTE(0xf7);BYTE(0x4e);
  }
  while(count<JUK_MFM_TRACK_SIZE){BYTE(0x4e);}
  #undef BYTE
  assert(!(j->fdc.status&0x1d));
  for(unsigned i=0;i<5120;i++)assert(disk[i]==0xe5);
  assert(!memcmp(disk+5120,original+5120,819200-5120));
  juku_destroy(j);free(disk);free(original);
  puts("Juku experimental synchronization: reads, writes, pacing, index, errors, interrupt deferral PASS");
}
