#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static unsigned round_id;
static int(*inventories[3])(FILE*);
static std::string snapshot(bool refuse=false){
 std::string all;
 for(unsigned i=0;i<3;++i){
  char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
  int rc=inventories[i](f);if(fclose(f))exit(2);
  if(refuse){if(rc>=0||n)exit(2);}else{if(rc||!n)exit(2);all+=std::string(p,n);}
  free(p);
 }
 return all;
}
static void image(const std::string&label){printf("IMAGE %s\n%sIMAGE_END\n",label.c_str(),snapshot().c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 ++round_id;printf("ROUND %u\n",round_id);
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);bool enabled=!strcmp(mode,"on");
 auto control=(int(*)(unsigned,unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_lifecycle");
 if(enabled){
  const char*names[]={"robotron_vvp_parameter_inventory","robotron_vvp_scope_metadata_inventory","robotron_vvp_scope_metadata_reference_inventory"};
  for(unsigned i=0;i<3;++i){inventories[i]=(int(*)(FILE*))dlsym(RTLD_DEFAULT,names[i]);if(!inventories[i])exit(2);}
  if(!control)exit(2);image("before"+std::to_string(round_id));
 }
 if(control){
  auto before=enabled?snapshot():"";
  if(control(99,0)!=-1||control(1,0)!=-1||control(2,0)!=-1)exit(2);
  printf("INVALID %u\n",round_id);
  for(unsigned cycle=0;cycle<3;++cycle){
   if(control(0,cycle)!=1||control(0,cycle)!=-1)exit(2);
   char name[80];snprintf(name,sizeof(name),"test.__parameter_lifecycle_%u_%u",cycle,3*(round_id-1)+cycle+1);
   auto param=vpi_handle_by_name(name,0);if(!param||vpi_get(vpiType,param)!=vpiParameter)exit(2);
   s_vpi_value v={};v.format=cycle==0?vpiBinStrVal:cycle==1?vpiRealVal:vpiStringVal;vpi_get_value(param,&v);
   if(cycle==0&&std::string(v.value.str)!=std::string(79,'x')+"1")exit(2);
   if(cycle==1&&v.value.real!=2.5)exit(2);
   if(cycle==2&&std::string(v.value.str)!="G R")exit(2);
   printf("CREATED %u %u\n",round_id,cycle);if(enabled)image("created"+std::to_string(round_id)+"_"+std::to_string(cycle));
   if(control(1,cycle)!=1||control(1,cycle)!=-1||control(0,cycle)!=-1)exit(2);
   if(enabled){snapshot(true);printf("REFUSED %u %u 3\n",round_id,cycle);}printf("DESTROYED %u %u\n",round_id,cycle);
   if(control(2,cycle)!=1||control(2,cycle)!=-1)exit(2);
   if(enabled){if(snapshot()!=before)exit(2);image("detached"+std::to_string(round_id)+"_"+std::to_string(cycle));}
   printf("DETACHED %u %u\n",round_id,cycle);
  }
 }
 return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$parameter_lifecycle";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
