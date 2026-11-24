/* Internal snapshot contract plus public runtime execution. */
#include "juku_internal.h"
#include "../../common/runtime/session.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned save(dac_session *s,uint8_t **bytes) {
 unsigned n=dac_state_size(s);*bytes=malloc(n);assert(*bytes);
 assert(!dac_state_save(s,*bytes,n));return n;
}
int main(void) {
 for(unsigned write=0;write<2;write++) {
  uint8_t rom[16384]={0};uint8_t code[]={0x3e,4,0xd3,6,0x3e,1,0xd3,0x1e,0x3e,0x84,0xd3,0x1c,0xdb,0x1f,0xc3,14,0};
  if(write){code[9]=0xa4;code[12]=0xd3;}
  memcpy(rom,code,sizeof(code));uint8_t *disk=calloc(819200,1);assert(disk);
  dac_session *s=dac_create(0);assert(s);assert(!dac_load(s,0,rom,sizeof rom));
  assert(!dac_mount(s,disk,819200,1));free(disk);assert(!dac_power(s,1));
  uint8_t *snap=NULL;unsigned n=0;
  for(unsigned i=0;i<100;i++) {
   assert(dac_run(s,1));free(snap);n=save(s,&snap);
   juku j;memcpy(&j,snap+32,sizeof j);
   if(j.cpu.io_pending && j.cpu.io_port==0x1f)break;
  }
  juku j;memcpy(&j,snap+32,sizeof j);assert(j.cpu.io_pending && j.cpu.io_port==0x1f);
  unsigned consumed=dac_run(s,70000);uint8_t *one;assert(save(s,&one)==n);
  assert(!dac_state_load(s,snap,n));unsigned elapsed=0;
  while(elapsed<consumed)elapsed+=dac_run(s,1);
  uint8_t *many;assert(save(s,&many)==n);assert(elapsed==consumed&&!memcmp(one,many,n));
  assert(!dac_state_load(s,snap,n));assert(!dac_reset(s));
  uint8_t *reset;assert(save(s,&reset)==n);memcpy(&j,reset+32,sizeof j);assert(!j.cpu.io_pending);
  // Reject snapshots from another timing configuration even with valid CRC.
  ((uint32_t*)snap)[1]=21;assert(dac_state_load(s,snap,n)<0);
  free(snap);free(one);free(many);free(reset);dac_destroy(s);
 }
 puts("Juku pending read/write snapshots, chunk invariance, reset and configuration rejection PASS");
}
