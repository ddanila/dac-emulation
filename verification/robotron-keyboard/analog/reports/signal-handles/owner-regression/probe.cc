#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <dlfcn.h>
#include <vpi_user.h>
#include "vvp_net_sig.h"
#include "compact.h"
static vvp_wire_vec4*owners[2];static void*storage[2];static unsigned generations[2],stage;
static bool early,observe;
static void create(unsigned slot,unsigned width,vvp_bit4_t bit){
 if(owners[slot])exit(2);if(!storage[slot])storage[slot]=::operator new(sizeof(vvp_wire_vec4));
 owners[slot]=::new(storage[slot])vvp_wire_vec4(width,bit);++generations[slot];
 if(observe)printf("OWN_BIND %u %u %p\n",slot,generations[slot],(void*)static_cast<vvp_vpi_callback*>(owners[slot]));
}
static void destroy(unsigned slot){
 if(!owners[slot])exit(2);owners[slot]->~vvp_wire_vec4();owners[slot]=0;
 printf("OWN_DROP %u %u\n",slot,generations[slot]);
}
static void inspect(){
 printf("OWN_STAGE %u\n",stage);
 if(observe){
  auto api=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_inventory");if(!api)exit(2);
  for(int i=0;i<2;i++){
   char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);int r=api(f);if(fclose(f)||r)exit(2);
   compact_check(r);printf("OWN_%s\n%s",i?"REPEAT":"BEFORE",p);free(p);
  }
 }
 for(unsigned i=0;i<2;i++)if(owners[i]){
  s_vpi_value v={};v.format=vpiBinStrVal;owners[i]->get_value(&v);
  printf("OWN_VALUE %u %u %u %s\n",i,generations[i],owners[i]->filter_size(),v.value.str);
 }
 printf("OWN_DONE %u\n",stage++);
}
static PLI_INT32 advance(PLI_BYTE8*){
 if(!stage){const char*m=getenv("K7658_OWNER_MODE"),*t=getenv("K7658_OWNER_TIMING");if(!m||!t)exit(2);observe=strcmp(m,"off");early=!strcmp(t,"early");if(early)create(0,1,BIT4_0);}
 else if(stage==1){if(!early)create(0,1,BIT4_0);vvp_vector4_t value(1,BIT4_1),rep;owners[0]->filter_vec4(value,rep,0,1);}
 else if(stage==2)create(1,9,BIT4_X);
 else if(stage==3)destroy(0);
 else if(stage==4)create(0,80,BIT4_Z);
 else if(stage==5)destroy(1);
 else if(stage==6)destroy(0);
 else exit(2);
 inspect();if(stage==7)for(auto p:storage)::operator delete(p);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$owner_step";t.calltf=advance;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
