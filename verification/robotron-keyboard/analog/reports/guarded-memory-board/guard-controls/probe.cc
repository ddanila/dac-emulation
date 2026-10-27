#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
#include "array_common.h"
static unsigned round_id;
static std::string snapshot(int(*fn)(FILE*),bool refused=false){
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);int rc=fn(f);if(fclose(f))exit(2);
 if(refused){if(rc>=0||n)exit(2);}else if(rc||!n)exit(2);
 std::string result(p,n);free(p);return result;
}
static void image(const char*name,const std::string&s){printf("IMAGE %s%u\n%sIMAGE_END\n",name,round_id,s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 ++round_id;printf("ROUND %u\n",round_id);const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 if(strcmp(mode,"on")){printf("RESTORED %u\n",round_id);return 0;}
 auto dense=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_inventory");auto compact=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_compact_inventory");
 auto validate=(int(*)(const __vpiArrayBase*,unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_array_cache_validate");if(!dense||!compact||!validate)exit(2);
 auto handle=vpi_handle_by_name("test.memory",0);auto memory=dynamic_cast<__vpiArray*>(handle);if(!memory)exit(2);
 auto prior=memory->vals_words;if((round_id==1 && prior)||(round_id==2&&!prior))exit(2);
 image("before",snapshot(dense));if(memory->vals_words!=prior)exit(2);
 if(!vpi_handle_by_index(handle,0)||!memory->vals_words)exit(2);
 auto cache=memory->vals_words;auto head=memory->ports_;
 if(validate(memory,memory->get_size()) || validate(memory,memory->get_size()+1)>=0)exit(2);
 auto ready=snapshot(dense);auto packed=snapshot(compact);image("ready",ready);image("compact",packed);
 for(unsigned field=0;field<4;++field){
  if(field==0)memory->vals_words=(__vpiArrayWord*)1;
  if(field==1)memory->vals_words=cache+1;
  if(field==2)memory->vals_words=0;
  if(field==3)memory->ports_=(vvp_fun_arrayport*)1;
  snapshot(dense,true);snapshot(compact,true);printf("REFUSED %u %u\n",round_id,field);
  memory->vals_words=cache;memory->ports_=head;
  if(snapshot(dense)!=ready||snapshot(compact)!=packed)exit(2);
 }
 image("restored",snapshot(dense));printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$array_cache_admission";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
