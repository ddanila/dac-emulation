/* SPDX-License-Identifier: MIT. Independent expected board/serial contracts. */
#include "machines/kaypro2/kaypro2.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
static unsigned sent;static uint8_t bytes[4];
static void tx(void *p,unsigned n,uint8_t v){(void)p;assert(n==0);bytes[sent++]=v;}
/* Execute OUT instructions through the real shared CPU, including I/O aliases. */
static void out(kaypro2 *m,uint8_t port,uint8_t value){
 uint8_t code[]={0x3e,value,0xd3,port,0x76};
 memcpy(m->ram+0x4000,code,sizeof code);
 m->cpu.pins=z80_prefetch(&m->cpu.cpu,0x4000);m->io_active=0;
 kaypro2_run(m,30);
}
int main(void){
 kaypro2 *m=calloc(1,sizeof(*m));assert(m);kaypro2_init(m);
 uint8_t rom[4096];memset(rom,0xa5,sizeof rom);assert(!kaypro2_load(m,rom,sizeof rom));
 m->ram[0x100]=0x42;assert(kaypro2_read(m,0x100)==0xa5);
 kaypro2_write(m,0x100,0x55);assert(m->ram[0x100]==0x42);
 kaypro2_write(m,0x3000,0x31);assert(m->video[0]==0x31&&m->ram[0x3000]==0);
 out(m,0x7c,0x40);assert(kaypro2_read(m,0x100)==0x42); /* A5/A6 aliases */
 kaypro2_write(m,0x3000,0x99);assert(m->ram[0x3000]==0x99&&m->video[0]==0x31);
 out(m,0x9c,0x80);assert(m->system==0x40); /* A7 inhibits decode */
 out(m,6,4);out(m,6,0x44);out(m,6,3);out(m,6,0xc1);out(m,6,5);out(m,6,0xea);out(m,0,15);
 assert(kaypro2_baud(m,0)==19200&&kaypro2_character_ticks(m,0)==1303);
 assert(!kaypro2_receive(m,0,1));assert(!kaypro2_receive(m,0,2));assert(!kaypro2_receive(m,0,3));
 assert(kaypro2_receive(m,0,4)==-ENOSPC);assert(m->sio[0].errors&0x20);
 out(m,6,0x30);assert(!m->sio[0].errors&&m->sio[0].count==3);
 m->transmit=tx;out(m,4,0x11);out(m,4,0x22);assert(sent==0&&m->sio[0].holding);
 kaypro2_run(m,3000);assert(sent==2&&bytes[0]==0x11&&bytes[1]==0x22);
 out(m,6,0x18);out(m,6,4);out(m,6,0x45);assert(m->sio[0].wr[4]==0x45);
 out(m,6,5);out(m,6,0xea);assert(kaypro2_character_ticks(m,0)==1433);
 kaypro2_reset(m);assert(m->system==0x80&&!m->sio[0].count&&m->ram[0x100]==0x42);
 /* All 1920 visible cells must be distinct; high-column aliases are physical. */
 unsigned used[2048]={0};
 for(unsigned y=0;y<24;y++)for(unsigned x=0;x<80;x++){
  unsigned i=kaypro2_video_index(0x3000+y*128+x);assert(i<2048&&!used[i]);used[i]=1;
 }
 assert(kaypro2_video_index(0x3040)==kaypro2_video_index(0x3050));
 assert(kaypro2_video_index(0x3040)==0x600);
 assert(kaypro2_video_index(0x3800)==0x400);
 assert(kaypro2_video_index(0x3440)==0x610);
 uint8_t font[2048]={0},*pixels=calloc(560*240,1);assert(pixels);
 font[(65+128)*8]=0x15;assert(!kaypro2_load_chargen(m,font,sizeof font));
 m->video[0]=65;kaypro2_render(m,pixels,0);
 assert(!pixels[0]&&pixels[1]&&!pixels[2]&&pixels[3]&&!pixels[4]&&pixels[5]&&!pixels[6]);
 m->video[0]=65|128;kaypro2_render(m,pixels,0);assert(!pixels[1]);
 kaypro2_render(m,pixels,1);assert(pixels[1]);free(pixels);
 free(m);puts("Kaypro memory, aliases, SIO FIFO/timing and reset PASS");return 0;
}
