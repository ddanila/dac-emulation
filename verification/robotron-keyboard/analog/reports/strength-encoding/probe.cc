#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <map>
#include <vector>
#include <vpi_user.h>
#include "vvp_net.h"
static unsigned raw(vvp_scalar_t value) {
 static_assert(sizeof(vvp_scalar_t)==1,"Expected single-byte scalar with no padding");
 unsigned char byte;memcpy(&byte,&value,1);return byte;
}
static PLI_INT32 inspect(p_cb_data) {
 std::map<unsigned,vvp_scalar_t> states;
 for(unsigned bit=0;bit<4;bit++)for(unsigned s0=0;s0<8;s0++)for(unsigned s1=0;s1<8;s1++) {
  vvp_scalar_t value(static_cast<vvp_bit4_t>(bit),s0,s1);states.emplace(raw(value),value);
  printf("STRENGTH_SEED %u %u %u %u\n",bit,s0,s1,raw(value));
 }
 for(;;){
  auto old=states;
  for(auto a:old)for(auto b:old){auto value=resolve(a.second,b.second);states.emplace(raw(value),value);}
  if(old.size()==states.size())break;
  if(states.size()>256)exit(2);
 }
 for(auto a:states)printf("STRENGTH_STATE %u %u %u %u\n",a.first,unsigned(a.second.value()),a.second.strength0(),a.second.strength1());
 for(auto a:states)for(auto b:states)printf("STRENGTH_RESOLVE %u %u %u\n",a.first,b.first,raw(resolve(a.second,b.second)));
 for(auto a:states)for(auto b:states)if(a.first<b.first && a.second.value()==b.second.value() && a.second.strength0()==b.second.strength0() && a.second.strength1()==b.second.strength1()) {
  vvp_vector8_t av(1),bv(1);av.set_bit(0,a.second);bv.set_bit(0,b.second);
  printf("STRENGTH_COLLISION %u %u %d %d\n",a.first,b.first,a.second.eeq(b.second),av.eeq(bv));
 }
 printf("STRENGTH_DONE %zu\n",states.size());return 0;
}
static void setup(){s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=inspect;if(!vpi_register_cb(&cb))exit(2);}
extern "C" { void (*vlog_startup_routines[])(void)={setup,0}; }
