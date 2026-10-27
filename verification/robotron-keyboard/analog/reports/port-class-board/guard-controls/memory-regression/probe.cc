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

 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 ++round_id;printf("ROUND %u\n",round_id);
 if(strcmp(vpi_get_str(vpiName,handle),"memory"))exit(2);
 if(strcmp(mode,"on")){printf("RESTORED %u\n",round_id);return 0;}
 inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_memory_metadata_inventory");
 auto arrays=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_inventory");
 auto toggle=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_memory_toggle");
 if(!inventory||!arrays||!toggle)exit(2);
 auto before=snapshot(inventory);auto values=snapshot(arrays);image("before",before);image("arrays",values);
 if(toggle(5)!=-1||snapshot(inventory)!=before||snapshot(arrays)!=values)exit(2);
 for(unsigned field=0;field<5;++field){
  if(toggle(field)!=1||toggle((field+1)%5)!=-1)exit(2);
  if(field==0){image("changed",snapshot(inventory));if(snapshot(arrays)!=values||!strcmp(vpi_get_str(vpiName,handle),"memory"))exit(2);}
  else if(field==1){snapshot(inventory,true);if(snapshot(arrays)!=values)exit(2);}
  else{snapshot(arrays,true);if(snapshot(inventory)!=before)exit(2);}
  if(toggle(field)!=1||snapshot(inventory)!=before||snapshot(arrays)!=values)exit(2);
  printf("FAULT %u %u restored\n",round_id,field);
 }
 image("restored",snapshot(inventory));image("values",snapshot(arrays));
 if(strcmp(vpi_get_str(vpiName,handle),"memory"))exit(2);
 printf("RESTORED %u\n",round_id);return 0;
}
static PLI_INT32 index_word(PLI_BYTE8*){
 auto handle=vpi_handle_by_name("test.memory",0);auto word=vpi_handle_by_index(handle,1);if(!word)exit(2);
 s_vpi_value value={};value.format=vpiIntVal;vpi_get_value(word,&value);
 if(value.value.integer!=5)exit(2);printf("INDEXED %d\n",value.value.integer);return 0;
}

static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$memory_fault_continue";t.calltf=run;vpi_register_systf(&t);t.tfname="$index_memory";t.calltf=index_word;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
