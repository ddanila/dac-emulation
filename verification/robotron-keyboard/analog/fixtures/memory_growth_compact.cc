#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static unsigned round_id;
static int(*inventory)(FILE*);
static int(*arrays)(FILE*);
static int(*compact_arrays)(FILE*);
static std::string snapshot(){char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);int rc=inventory(f);if(!rc)rc=arrays(f);if(!rc)rc=compact_arrays(f);if(fclose(f)||rc||!n)exit(2);std::string s(p,n);free(p);return s;}
static void image(const std::string&label){auto s=snapshot();printf("IMAGE %s\n%sIMAGE_END\n",label.c_str(),s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);bool enabled=!strcmp(mode,"on");++round_id;printf("ROUND %u\n",round_id);
 auto original=vpi_handle_by_name("test.memory",0);if(!original||!vpi_handle_by_index(original,0))exit(2);
 auto add=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_memory_add");
 if(enabled){inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_memory_metadata_inventory");arrays=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_inventory");compact_arrays=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_array_compact_inventory");if(!inventory||!arrays||!compact_arrays||!add)exit(2);image("before"+std::to_string(round_id));}
 if(add){
  auto before=enabled?snapshot():"";if(add(2)!=-1||(enabled&&snapshot()!=before))exit(2);printf("REFUSED %u\n",round_id);
  for(unsigned kind=0;kind<2;++kind){
   if(add(kind)!=1)exit(2);char name[100];snprintf(name,sizeof(name),"test.__memory_growth_%u_%u",kind,2*(round_id-1)+kind+1);auto p=vpi_handle_by_name(name,0);if(!p||vpi_get(vpiType,p)!=vpiMemory)exit(2);
   printf("ADDED %u %u\n",round_id,kind);if(enabled)image("after"+std::to_string(round_id)+"_"+std::to_string(kind));
   for(unsigned i=0;i<(kind?3:2);++i){
    auto word=vpi_handle_by_index(p,i+(kind?1:0));if(!word)exit(2);
    s_vpi_value v={};v.format=vpiBinStrVal;vpi_get_value(word,&v);
    if(std::string(v.value.str)!=std::string((kind?80:8)-1,'x')+(i%2?"0":"1"))exit(2);
   }
   printf("CACHED %u %u\n",round_id,kind);if(enabled)image("cached"+std::to_string(round_id)+"_"+std::to_string(kind));
  }
 }
 return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$memory_growth";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
