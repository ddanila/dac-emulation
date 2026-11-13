/* SPDX-License-Identifier: MIT. Timed FDC and board wiring regression. */
#include "machines/kaypro2/kaypro2.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static void out(kaypro2 *m,uint8_t port,uint8_t v){
 uint8_t code[]={0x3e,v,0xd3,port,0xc3,4,0x40};
 memcpy(m->ram+0x4000,code,sizeof code);m->cpu.pins=z80_prefetch(&m->cpu.cpu,0x4000);m->io_active=0;kaypro2_run(m,30);
}
int main(void){
 kaypro2 *m=calloc(1,sizeof(*m));uint8_t *a=malloc(204800),*b=malloc(204800);assert(m&&a&&b);
 memset(a,0x31,204800);memset(b,0x72,204800);kaypro2_init(m);
 assert(!kaypro2_mount(m,0,dac_memory_storage(a,204800,1),1));
 assert(!kaypro2_mount(m,1,dac_memory_storage(b,204800,0),0));
 out(m,0x1c,0x11);assert(m->selected_drive==0 && m->fdc.motor_on && (m->system&0x10));
 kaypro2_run(m,KAYPRO2_CLOCK_HZ/2);out(m,0x12,0);out(m,0x10,0x80);assert(m->fdc.status&2);
 assert(wd179x_read(&m->fdc,3)==0x31);assert(!(m->fdc.status&2));
 kaypro2_run(m,80);assert(m->fdc.status&2);kaypro2_run(m,90);assert(m->fdc.status&4);
 out(m,0x10,0xd0);assert(!(m->fdc.status&1));
 out(m,0x1c,0x12);assert(m->selected_drive==1);
 out(m,0x12,0);out(m,0x10,0xa0);assert(m->fdc.status&0x40);assert(b[0]==0x72);
 out(m,0x10,0xd0);kaypro2_eject(m,1);out(m,0x10,0x80);assert(m->fdc.status&0x80);
 out(m,0x1c,0x11);out(m,0x12,10);out(m,0x10,0x80);
 kaypro2_run(m,KAYPRO2_CLOCK_HZ);assert(!(m->fdc.status&1) && (m->fdc.status&0x10));
 /* Write Track must accept sector ID zero, with a separate invalid sentinel. */
 out(m,0x10,0xd0);out(m,0x11,0);
 wd179x_write(&m->fdc,0,0xf0);assert(m->fdc.status&2);
 wd179x_write(&m->fdc,3,0x4e);
 wd179x_index(&m->fdc,0);wd179x_index(&m->fdc,1);
 /* Feed an entire track at the controller boundary; guest timing is covered
    by cpm-plus-kaypro/tests/check_format.py with the real Z80 formatter. */
 unsigned count=1;
 #define BYTE(v) do {wd179x_write(&m->fdc,3,(v));count+=((v)==0xf7?2:1);} while(0)
 for(unsigned sector=0;sector<10;sector++) {
  BYTE(0xf5);BYTE(0xf5);BYTE(0xf5);BYTE(0xfe);
  BYTE(0);BYTE(0);BYTE(sector);BYTE(2);BYTE(0xf7);
  BYTE(0x4e);BYTE(0xf5);BYTE(0xf5);BYTE(0xf5);BYTE(0xfb);
  for(unsigned i=0;i<512;i++){BYTE(0xe5);}
  BYTE(0xf7);BYTE(0x4e);
 }
 while(count<6250){BYTE(0x4e);}
 #undef BYTE
 assert(!(m->fdc.status&0xfd));
 for(unsigned i=0;i<5120;i++)assert(a[i]==0xe5);
 assert(a[5120]==0x31 && b[0]==0x72);
 /* HALT+INTRQ causes the board NMI, not a direct guest-register shortcut. */
 m->ram[0x66]=0x3e;m->ram[0x67]=0xa5;m->ram[0x68]=0x32;m->ram[0x69]=0;m->ram[0x6a]=0x50;m->ram[0x6b]=0x18;m->ram[0x6c]=0xfe;
 m->ram[0x4000]=0x76;m->cpu.cpu.sp=0x7000;m->cpu.pins=z80_prefetch(&m->cpu.cpu,0x4000);m->fdc.intrq=1;
 kaypro2_run(m,100);assert(m->ram[0x5000]==0xa5);
 kaypro2_reset(m);assert(m->disks[0].media.storage.read && !m->fdc.disk);
 free(a);free(b);free(m);puts("Kaypro FDC pacing, lost data, drive isolation, write protection, missing media, RNF and HALT/NMI PASS");
}
