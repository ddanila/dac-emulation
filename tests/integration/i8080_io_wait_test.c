#include "i8080.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint8_t ram[65536];static unsigned inputs,outputs,polls;static int ready;
static uint8_t read_byte(void *u,uint16_t a){(void)u;return ram[a];}
static void write_byte(void *u,uint16_t a,uint8_t v){(void)u;ram[a]=v;}
static uint8_t in(void *u,uint8_t p){(void)u;assert(p==0x1f);inputs++;return 0xa7;}
static void out(void *u,uint8_t p,uint8_t v){(void)u;assert(p==0x1f&&v==0x53);outputs++;}
static bool wait_ready(void *u,uint8_t p,bool w){(void)u;(void)w;assert(p==0x1f);polls++;return ready;}
static void init(i8080 *c,uint8_t op){i8080_init(c);c->read_byte=read_byte;c->write_byte=write_byte;c->port_in=in;c->port_out=out;c->io_ready=wait_ready;ram[0]=op;ram[1]=0x1f;c->a=0x53;c->sp=0x8000;}
int main(void){
 for(unsigned write=0;write<2;write++)for(unsigned delay=0;delay<50;delay++){
  i8080 c;init(&c,write?0xd3:0xdb);inputs=outputs=polls=0;ready=0;c.iff=1;c.interrupt_delay=1;
  i8080_step(&c);assert(c.cyc==9&&c.pc==2&&c.io_pending&&c.a==0x53&&c.interrupt_delay==1);
  i8080_interrupt(&c,0xff);
  for(unsigned i=0;i<delay;i++){i8080_step(&c);assert(c.pc==2&&c.a==0x53&&c.iff&&c.interrupt_pending);}
  assert(!inputs&&!outputs);ready=1;i8080_step(&c);
  assert(c.cyc==10+delay&&!c.io_pending&&c.pc==2&&!c.interrupt_delay);
  assert(inputs==!write&&outputs==write&&polls==delay+1);assert(c.a==(write?0x53:0xa7));
  i8080_step(&c);assert(c.pc==0x38&&!c.interrupt_pending&&!c.iff);
 }
 i8080 c;init(&c,0xdb);ready=0;i8080_step(&c);for(unsigned i=0;i<100;i++)i8080_step(&c);
 assert(c.io_pending&&c.cyc==109);i8080_init(&c);assert(!c.io_pending&&!c.io_ready);
 puts("8080 resumable I/O, exact-once effects, waits, EI/IRQ and reset PASS");
}
