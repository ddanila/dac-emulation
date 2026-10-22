/* External memory/fetch phases around the C instruction engine. Internal
 * instruction state and external drive values are deliberately separate. */
#include "cpu_bus_half.h"
typedef struct {
 cpu_bus_half core;
 uint64_t pins;
 unsigned kind,phase,address,data;
} cpu_bus_pins;
static inline void cpu_pins_reset(cpu_bus_pins *c) {
 cpu_bus_reset(&c->core);c->pins=0;c->kind=c->phase=c->address=c->data=0;
}
static inline uint64_t cpu_pins_value(cpu_bus_pins *c,int falling,uint64_t raw) {
 if(c->core.busack)return raw&~Z80_CTRL_PIN_MASK;
 if(c->kind){
  uint64_t p=raw&~(Z80_M1|Z80_MREQ|Z80_RD|Z80_WR|Z80_RFSH);
  Z80_SET_ADDR(p,c->address);
  if(c->kind==4){
   p&=~Z80_IORQ;
   if(c->phase<=4){p|=Z80_M1;if((c->phase==3&&falling)||c->phase==4)p|=Z80_IORQ;}
   else if(c->phase<=6){p|=Z80_RFSH;if((c->phase==5&&falling)||(c->phase==6&&!falling))p|=Z80_MREQ;}
  }else if(c->kind==3){
   if(c->phase<=2){
    p|=Z80_M1;
    if(c->phase==2 || falling)p|=Z80_MREQ|Z80_RD;
   }else if(c->phase<=4){
    p|=Z80_RFSH;
    if((c->phase==3&&falling)||(c->phase==4&&!falling))p|=Z80_MREQ;
   }
  }else {
   if(c->kind==2)Z80_SET_DATA(p,c->data);
   if((c->phase==1&&falling)||c->phase==2||(c->phase==3&&!falling)){
    p|=Z80_MREQ;if(c->kind==1)p|=Z80_RD;
   }
   if(c->kind==2&&((c->phase==2&&falling)||(c->phase==3&&!falling)))p|=Z80_WR;
  }
  return p;
 }
 return raw;
}
static inline uint64_t cpu_pins_rise(cpu_bus_pins *c,uint64_t input,int request) {
 unsigned previous=c->core.core.cpu.step;
 uint64_t raw=cpu_bus_rise(&c->core,input,request);
 if(!c->core.busack){
  int memory=cpu_bus_memory_kind(&c->core.core.cpu);
  unsigned state=c->core.core.cpu.step;
  if(state==Z80_INT_IM0_STEP||state==Z80_INT_IM1_STEP||state==Z80_INT_IM2_STEP){
   c->kind=4;c->phase=1;c->address=c->core.core.cpu.pc;
  }else if((raw&Z80_M1)&&!(raw&Z80_IORQ)&&!fetch_waiting(previous)){
   c->kind=3;c->phase=1;c->address=(uint16_t)(Z80_GET_ADDR(raw)+!!(raw&Z80_HALT));
  }else if(memory && previous!=c->core.core.cpu.step){
   k7658_z80_t preview=c->core.core.cpu;
   uint64_t bus=k7658_z80_tick(&preview,raw&~Z80_WAIT);
   c->kind=memory;c->phase=1;c->address=Z80_GET_ADDR(bus);c->data=Z80_GET_DATA(bus);
  }else if(c->core.core.pending==6)c->phase=2;
  else if(c->kind==3 && (raw&Z80_RFSH)){c->phase=3;c->address=Z80_GET_ADDR(raw);}
  else if(c->kind==4 && (raw&Z80_RFSH)){c->phase=5;c->address=Z80_GET_ADDR(raw);}
  else if(c->kind==4 && fetch_waiting(previous))c->phase=4;
  else if(c->kind==3 && (previous==Z80_M1_T2||previous==Z80_DDFD_M1_T2||previous==Z80_CB_M1_T2||previous==Z80_ED_M1_T2))c->phase=2;
  else if(c->kind){
   c->phase++;
   if(c->kind==3&&c->phase==3)c->address=Z80_GET_ADDR(raw);
   if(c->kind==4&&c->phase==5)c->address=Z80_GET_ADDR(raw);
   if(c->phase>(c->kind==4?7u:c->kind==3?4u:3u))c->kind=0;
  }
 }
 return c->pins=cpu_pins_value(c,0,raw);
}
static inline uint64_t cpu_pins_fall(cpu_bus_pins *c,uint64_t input) {
 uint64_t raw=cpu_bus_fall(&c->core,input);
 return c->pins=cpu_pins_value(c,1,raw);
}
