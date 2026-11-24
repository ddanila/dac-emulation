#include "juku_internal.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void advance(juku *j, unsigned long cycles) {
  j->cpu.cyc += cycles;
  juku_video_advance(j);
}
static void count(juku *j, unsigned port, unsigned value) {
  juku_pit_write(j, (uint8_t)port, (uint8_t)value);
}
static void setup(juku *j, unsigned blank, unsigned vertical_blank) {
  count(j,0x13,0x15); count(j,0x10,0x64);
  count(j,0x13,0x53); count(j,0x11,blank);
  count(j,0x13,0x93); count(j,0x12,0x08);
  count(j,0x17,0x34); count(j,0x14,0x39); count(j,0x14,0x01);
  count(j,0x17,0x73); count(j,0x15,vertical_blank); count(j,0x15,0);
  count(j,0x17,0x93); count(j,0x16,0x25);
}
static void geometry_and_pixels(void) {
  juku *j=juku_create(); assert(j);
  for(unsigned i=0;i<10240;i++) j->ram[VRAM_BASE+i]=(uint8_t)(i*13+7);
  setup(j,0x24,0x72);
  advance(j,40064*4);
  unsigned stride,lines;uint64_t seq;
  const uint8_t *f=juku_frame(j,&stride,&lines,&seq);
  assert(f && stride==40 && lines==241 && seq>=2);
  assert(!memcmp(f,j->ram+VRAM_BASE,stride*lines));
  uint64_t old=seq;advance(j,40064);
  juku_frame(j,NULL,NULL,&seq);assert(seq==old+1);
  /* Neither width nor height is a known mode; write the vertical count
   * before the horizontal count, without ever writing front-porch last. */
  count(j,0x15,0x70);count(j,0x15,0);count(j,0x11,0x23);
  advance(j,40064*3);
  f=juku_frame(j,&stride,&lines,NULL);
  assert(f && stride==41 && lines==243);
  assert(!memcmp(f,j->ram+VRAM_BASE,stride*lines));
  count(j,0x11,0x16);count(j,0x15,0x12);count(j,0x15,0x01);
  advance(j,40064*3);
  juku_frame(j,&stride,&lines,NULL);assert(stride==48&&lines==201);
  count(j,0x11,0x14);count(j,0x15,0x20);count(j,0x15,0x01);
  advance(j,40064*3);
  juku_frame(j,&stride,&lines,NULL);assert(stride==50&&lines==193);
  juku_destroy(j);
}
static void counter_semantics(void) {
  juku *j=juku_create();
  count(j,0x13,0x30);count(j,0x10,4); /* incomplete LSB/MSB */
  advance(j,20);assert(!j->pit_counters[0][0].armed);
  count(j,0x10,0);advance(j,2);
  assert(juku_pit_read(j,0x10)==4);
  advance(j,4);count(j,0x13,0); /* latch 2 */
  advance(j,2);count(j,0x13,0); /* cannot replace pending latch */
  assert(juku_pit_read(j,0x10)==2);assert(juku_pit_read(j,0x10)==0);
  advance(j,2);assert(j->pit_counters[0][0].output);
  count(j,0x13,0x31);count(j,0x10,0);count(j,0x10,0);advance(j,2);
  assert(j->pit_counters[0][0].counter==10000);
  advance(j,2);assert(juku_pit_read(j,0x10)==0x99);assert(juku_pit_read(j,0x10)==0x99);
  juku_destroy(j);
}
static void chunking(void) {
  juku *a=juku_create(),*b=juku_create();setup(a,0x24,0x72);setup(b,0x24,0x72);
  advance(a,200320);
  for(unsigned i=0;i<200320;i++) advance(b,1);
  assert(!memcmp(&a->scanout,&b->scanout,sizeof(a->scanout)));
  assert(!memcmp(a->pit_counters,b->pit_counters,sizeof(a->pit_counters)));
  /* Saving/restoring all timing state mid-count must reproduce scanout. */
  juku *copy=malloc(sizeof(*copy));assert(copy);memcpy(copy,a,sizeof(*copy));
  advance(a,80000);advance(copy,80000);
  assert(!memcmp(&a->scanout,&copy->scanout,sizeof(a->scanout)));
  free(copy);juku_destroy(a);juku_destroy(b);
}
static void bcd_vertical_and_irq(void) {
  juku *j=juku_create();setup(j,0x24,0x72);
  /* Monitor 3.3 uses BCD 0312, not binary 0312 (786). */
  count(j,0x17,0x35);count(j,0x14,0x12);count(j,0x14,0x03);
  advance(j,39936*4);
  assert(j->scanout.frame_stride==40&&j->scanout.frame_lines==240);
  assert(j->scanout.irq_pending);
  j->cpu.iff=0;juku_step_devices(j);assert(j->scanout.irq_pending);
  j->cpu.iff=1;j->cpu.interrupt_delay=1;juku_step_devices(j);
  assert(j->scanout.irq_pending&&!j->frame_irq_count);
  j->cpu.interrupt_delay=0;j->pic_mask=0;j->cpu.halted=1;
  juku_step_devices(j);
  assert(!j->scanout.irq_pending&&j->frame_irq_count==1&&!j->cpu.halted);
  juku_destroy(j);
}
static void atomic_frame(void) {
  juku*j=juku_create();setup(j,0x24,0x72);
  memset(j->ram+VRAM_BASE,0x80,9640);advance(j,40064*3);
  uint8_t saved[9640];memcpy(saved,juku_frame(j,NULL,NULL,NULL),sizeof(saved));
  memset(j->ram+VRAM_BASE,0,9640);
  /* A RAM change must not retrospectively alter the completed frame. */
  assert(!memcmp(saved,juku_frame(j,NULL,NULL,NULL),sizeof(saved)));
  advance(j,40064*2);
  const uint8_t*p=juku_frame(j,NULL,NULL,NULL);
  for(unsigned i=0;i<9640;i++)assert(!p[i]);
  juku_destroy(j);
}
static void reload_and_square_wave(void) {
  juku*j=juku_create();count(j,0x13,0x14);count(j,0x10,8);
  advance(j,2);assert(j->pit_counters[0][0].counter==8);
  advance(j,4);count(j,0x10,4); /* rate-generator rewrite waits for reload */
  assert(j->pit_counters[0][0].counter==6);
  advance(j,10);assert(!j->pit_counters[0][0].output);
  advance(j,2);assert(j->pit_counters[0][0].output&&j->pit_counters[0][0].counter==4);
  count(j,0x13,0x16);count(j,0x10,5);advance(j,2);
  advance(j,4);assert(j->pit_counters[0][0].output);
  advance(j,2);assert(!j->pit_counters[0][0].output);
  advance(j,2);assert(!j->pit_counters[0][0].output);
  advance(j,2);assert(j->pit_counters[0][0].output);
  count(j,0x13,0x18);count(j,0x10,3);advance(j,2);
  advance(j,4);assert(j->pit_counters[0][0].output);
  advance(j,2);assert(!j->pit_counters[0][0].output);
  advance(j,2);assert(j->pit_counters[0][0].output);
  juku_destroy(j);
}
int main(void){counter_semantics();geometry_and_pixels();chunking();bcd_vertical_and_irq();atomic_frame();reload_and_square_wave();puts("PASS: Juku clocked video, arbitrary geometry, pixels, latch, BCD and chunk invariance");}
