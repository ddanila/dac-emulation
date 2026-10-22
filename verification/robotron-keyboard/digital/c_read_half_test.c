#define CHIPS_IMPL
#include "c_read_half.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 /* IN A,(80); OUT (81),A; HALT. Change input only between T3 rising/falling. */
 const unsigned char mem[]={0xdb,0x80,0xd3,0x81,0x76};
 for(int waits=0;waits<2;waits++)for(int interrupt_sample=0;interrupt_sample<2;interrupt_sample++){
  c_read_half c;c_read_reset(&c);uint64_t p=c.pins;int wrote=0,waited=0,left=0,cancelled=0,samples=0;
  for(int cycle=0;cycle<300;cycle++){
   if(left){p|=Z80_WAIT;left--;}else p&=~Z80_WAIT;
   p=c_read_rise(&c,p);
   if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){unsigned a=Z80_GET_ADDR(p);Z80_SET_DATA(p,a<sizeof mem?mem[a]:0);}
   if((p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD)){
    Z80_SET_DATA(p,0x12);
    if(waits&&!waited){left=3;waited=1;}
   }
   if(c.pending){
    if(interrupt_sample&&!cancelled){c_read_reset(&c);p=c.pins;cancelled=1;assert(!c.pending);continue;}
    assert((p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD));
    Z80_SET_DATA(p,0x34);samples++;
   }
   if((p&(Z80_IORQ|Z80_WR))==(Z80_IORQ|Z80_WR)){assert(Z80_GET_DATA(p)==0x34);wrote=1;}
   int sampled=c.pending;p=c_read_fall(&c,p);
   if(sampled)assert(!(p&(Z80_IORQ|Z80_RD)));
  }
  assert(wrote&&samples==1&&cancelled==interrupt_sample);
  printf("PASS waits=%d reset_between_edges=%d data=34\n",waits,interrupt_sample);
 }
 return 0;
}
