#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*inventory)(FILE*);static unsigned round_id;
static std::string snapshot(int(*fn)(FILE*),bool refused=false){
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=fn(f);if(fclose(f))exit(2);
 if(refused){if(rc>=0||n)exit(2);}else if(rc||!n)exit(2);
 std::string text(p,n);free(p);return text;
}
static void image(const char*label,const std::string&s){printf("IMAGE %s%u\n%sIMAGE_END\n",label,round_id,s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 auto handle=vpi_handle_by_name("test.memory",0);auto memory=dynamic_cast<__vpiArray*>(handle);if(!memory)exit(2);
 auto scope=memory->get_scope();const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 ++round_id;printf("ROUND %u\n",round_id);
 if(strcmp(vpi_get_str(vpiName,handle),"memory"))exit(2);
 if(strcmp(mode,"on")){printf("RESTORED %u\n",round_id);return 0;}
 inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_memory_metadata_inventory");
 auto arrays=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_inventory");if(!inventory||!arrays)exit(2);
 printf("IDENTITY %u %p %p %p\n",round_id,(void*)handle,(void*)memory,(void*)scope);
 auto before=snapshot(inventory);auto values=snapshot(arrays);image("before",before);
 char*name=const_cast<char*>(memory->name);name[0]^=1;
 if(!strcmp(vpi_get_str(vpiName,handle),"memory"))exit(2);
 image("changed",snapshot(inventory));if(snapshot(arrays)!=values)exit(2);
 name[0]^=1;if(snapshot(inventory)!=before)exit(2);image("restored",before);
 const char*original=memory->name;
 for(unsigned field=0;field<5;++field){
  auto members=scope->intern;
  if(field==0)memory->name="memory";
  if(field==1)memory->name=(const char*)1;
  if(field==2){for(auto it=scope->intern.begin();it!=scope->intern.end();++it)if(*it==handle){scope->intern.erase(it);break;}}
  if(field==3)scope->intern.push_back(handle);
  if(field==4)scope->intern.push_back((vpiHandle)1);
  snapshot(inventory,true);printf("REFUSED %u %u\n",round_id,field);
  memory->name=original;scope->intern=members;
  if(snapshot(inventory)!=before||snapshot(arrays)!=values)exit(2);
 }
 if(strcmp(vpi_get_str(vpiName,handle),"memory"))exit(2);
 printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$memory_metadata";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
