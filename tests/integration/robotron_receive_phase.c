/* MIT. Independent asynchronous peer: receiver edge phase and 1% clock skew.
 * x1 is not a supported independent-clock configuration; x16 must tolerate it. */
#include "../../machines/robotron1715m/robotron.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static unsigned trial(unsigned mult,unsigned offset){
 robotron *m=calloc(1,sizeof(*m));assert(m);robotron_init(m);
 m->sio_regs[1][3]=0xc1;m->sio_regs[1][4]=mult==16?0x44:0x04;m->v24.signals=3;
 const unsigned bytes[]={0x55,0xaa,0,255,0x81,0x7e};unsigned got=0,bad=0;
 unsigned period=mult==16?26:416;
 for(unsigned t=0;t<offset+6*12*412+832;t++){
  unsigned level=1;
  if(t>=offset){unsigned bit=(t-offset)/412,ch=bit/12,pos=bit%12;if(ch<6){if(pos==0)level=0;else if(pos<=8)level=(bytes[ch]>>(pos-1))&1;}}
  if(t%period==0)robotron_v24_receive_clock(m,level);
  if(m->rx_b.count){if(m->rx_b.errors)bad=1;unsigned value=robotron_v24_read(m,0);if(got>=6||value!=bytes[got])bad=1;got++;}
 }
 bad|=got!=6;free(m);return bad;
}
int main(void){unsigned failed_x1=0;for(unsigned phase=0;phase<416;phase++){failed_x1+=trial(1,phase);assert(!trial(16,phase));}assert(failed_x1);printf("independent RX phase: x16 416/416 pass; x1 %u/416 fail\n",failed_x1);return 0;}
