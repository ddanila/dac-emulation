#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <dlfcn.h>
#include "vpi_priv.h"
#include "array_common.h"
struct Owner:public __vpiArrayBase {
 unsigned count;explicit Owner(unsigned n):count(n){}
 unsigned get_size()const override{return count;}
 vpiHandle get_left_range()override{return 0;}vpiHandle get_right_range()override{return 0;}
 __vpiScope*get_scope()const override{return 0;}
 int get_word_size()const override{return 8;}
 char*get_word_str(__vpiArrayWord*,int)override{return 0;}
 void get_word_value(__vpiArrayWord*,p_vpi_value)override{}
 void put_word_value(__vpiArrayWord*,p_vpi_value,int)override{}
 vpiHandle get_iter_index(__vpiArrayIterator*,int)override{return 0;}
};
static unsigned round_id;
static PLI_INT32 run(PLI_BYTE8*){
 ++round_id;printf("ROUND %u\n",round_id);const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  auto validate=(int(*)(const __vpiArrayBase*,unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_array_cache_validate");if(!validate)exit(2);
  alignas(Owner) unsigned char storage[sizeof(Owner)];__vpiArrayWord*previous=0;
  for(unsigned cycle=0;cycle<2;++cycle){
   unsigned count=2+cycle;auto p=new(storage)Owner(count);if(p->vals_words||validate(p,count))exit(2);
   if(previous){p->vals_words=previous;if(validate(p,count)>=0)exit(2);p->vals_words=0;printf("STALE %u\n",round_id);}
   p->make_vals_words();auto words=p->vals_words;if(!words||validate(p,count))exit(2);
   if(words[-1].parent!=p)exit(2);for(unsigned i=0;i<count;++i)if(words[i].word0!=words)exit(2);
   printf("OWNER %u %u %p %p %u\n",round_id,cycle,(void*)p,(void*)words,count);
   if(validate(p,count+1)>=0)exit(2);
   p->vals_words=(__vpiArrayWord*)1;if(validate(p,count)>=0)exit(2);p->vals_words=words;
   {Owner other(count);other.vals_words=words;if(validate(&other,count)>=0)exit(2);other.vals_words=0;}
   if(validate(p,count))exit(2);printf("REFUSED %u %u 3\n",round_id,cycle);
   p->~Owner();if(previous)delete[](previous-1);previous=words;
  }
  delete[](previous-1);
 }
 printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$array_cache_lifecycle";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
