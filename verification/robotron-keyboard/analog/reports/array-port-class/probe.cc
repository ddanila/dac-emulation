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

 auto arrays=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_inventory");
 auto compact=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_compact_inventory");
 auto toggle=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_array_port_class_toggle");
 if(!arrays||!compact||!toggle)exit(2);
 auto before=snapshot(arrays);auto packed=snapshot(compact);image("before",before);image("compact",packed);
 for(unsigned kind=0;kind<2;++kind){
  if(toggle(kind)!=1||toggle(1-kind)!=-1||toggle(2)!=-1)exit(2);
  if(kind){snapshot(arrays,true);snapshot(compact,true);printf("REFUSED %u\n",round_id);}
  else{image("base",snapshot(arrays));image("basecompact",snapshot(compact));}
  if(toggle(kind)!=1||snapshot(arrays)!=before||snapshot(compact)!=packed)exit(2);
 }
 image("restored",snapshot(arrays));
 printf("RESTORED %u\n",round_id);return 0;
}
static PLI_INT32 index_word(PLI_BYTE8*){
 auto handle=vpi_handle_by_name("test.memory",0);auto word=vpi_handle_by_index(handle,1);if(!word)exit(2);
 s_vpi_value value={};value.format=vpiIntVal;vpi_get_value(word,&value);
 if(value.value.integer!=5)exit(2);printf("INDEXED %d\n",value.value.integer);return 0;
}

static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$array_port_class";t.calltf=run;vpi_register_systf(&t);t.tfname="$index_memory";t.calltf=index_word;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
