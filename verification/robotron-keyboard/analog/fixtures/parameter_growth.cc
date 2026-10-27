#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static unsigned round_id;
static int(*inventory)(FILE*);
static std::string snapshot(){char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);int rc=inventory(f);if(fclose(f)||rc||!n)exit(2);std::string s(p,n);free(p);return s;}
static void image(const std::string&label){auto s=snapshot();printf("IMAGE %s\n%sIMAGE_END\n",label.c_str(),s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);bool enabled=!strcmp(mode,"on");++round_id;printf("ROUND %u\n",round_id);
 auto add=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_add");
 if(enabled){inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_inventory");if(!inventory||!add)exit(2);image("before"+std::to_string(round_id));}
 if(add){
  auto before=enabled?snapshot():"";if(add(3)!=-1||(enabled&&snapshot()!=before))exit(2);printf("REFUSED %u\n",round_id);
  for(unsigned kind=0;kind<3;++kind){
   if(add(kind)!=1)exit(2);char name[100];snprintf(name,sizeof(name),"test.__growth_%u_%u",kind,3*(round_id-1)+kind+1);auto p=vpi_handle_by_name(name,0);if(!p||vpi_get(vpiType,p)!=vpiParameter)exit(2);
   s_vpi_value v={};v.format=kind==0?vpiBinStrVal:kind==1?vpiRealVal:vpiStringVal;vpi_get_value(p,&v);
   if(kind==0&&std::string(v.value.str)!=std::string(79,'x')+"1")exit(2);
   if(kind==1&&v.value.real!=2.5)exit(2);
   if(kind==2&&std::string(v.value.str)!="G R")exit(2);
   printf("ADDED %u %u\n",round_id,kind);if(enabled)image("after"+std::to_string(round_id)+"_"+std::to_string(kind));
  }
 }
 return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$parameter_growth";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
