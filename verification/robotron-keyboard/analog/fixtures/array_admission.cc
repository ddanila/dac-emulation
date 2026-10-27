#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <new>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*dense)(FILE*);static int(*compact)(FILE*);static unsigned round_id;
static std::string snapshot(int(*fn)(FILE*),bool refused=false){
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);int rc=fn(f);if(fclose(f))exit(2);
 if(refused){if(rc>=0||n)exit(2);}else if(rc||!n)exit(2);
 std::string result(p,n);free(p);return result;
}
static void image(const char*name,const std::string&s){printf("IMAGE %s%u\n%sIMAGE_END\n",name,round_id,s.c_str());}
struct Derived:public vvp_vector4array_sa {Derived():vvp_vector4array_sa(8,2){}};
static PLI_INT32 run(PLI_BYTE8*){
 ++round_id;printf("ROUND %u\n",round_id);const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 if(strcmp(mode,"on")){printf("RESTORED %u\n",round_id);return 0;}
 dense=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_inventory");compact=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_compact_inventory");
 auto toggle=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_array_storage_toggle");auto validate=(int(*)(const void*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_storage_validate");
 if(!dense||!compact||!toggle||!validate)exit(2);
 alignas(vvp_vector4array_sa) unsigned char storage[sizeof(vvp_vector4array_sa)];
 for(unsigned i=0;i<2;++i){
  auto p=new(storage)vvp_vector4array_sa(8+i,2);
  if(validate(p))exit(2);p->set_word(1,vvp_vector4_t(8+i,BIT4_1));if(validate(p))exit(2);
  p->~vvp_vector4array_sa();if(validate(p)>=0)exit(2);
 }
 {Derived subclass;if(validate(&subclass)>=0)exit(2);}
 if(validate((void*)1)>=0)exit(2);printf("LIFETIME %u\n",round_id);
 auto memory=dynamic_cast<__vpiArray*>(vpi_handle_by_name("test.memory",0));if(!memory)exit(2);
 auto scope=memory->get_scope();auto original=memory->vals4;
 auto before=snapshot(dense);auto compact_before=snapshot(compact);image("before",before);image("compact",compact_before);
 for(unsigned field=0;field<9;++field){
  auto members=scope->intern;
  if(field<5){if(toggle(field)!=1)exit(2);}
  if(field==5)memory->vals4=(vvp_vector4array_t*)1;
  if(field==6)scope->intern.push_back((vpiHandle)1);
  if(field==7){for(auto it=scope->intern.begin();it!=scope->intern.end();++it)if(*it==static_cast<vpiHandle>(memory)){scope->intern.erase(it);break;}}
  if(field==8)scope->intern.push_back(static_cast<vpiHandle>(memory));
  snapshot(dense,true);snapshot(compact,true);printf("REFUSED %u %u\n",round_id,field);
  if(field<5){if(toggle(field)!=1)exit(2);}
  memory->vals4=original;scope->intern=members;
  if(snapshot(dense)!=before||snapshot(compact)!=compact_before)exit(2);
 }
 if(toggle(5)!=-1)exit(2);image("restored",snapshot(dense));printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$array_admission";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
