#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static unsigned round_id;
static int(*inventory)(FILE*);
static std::string snapshot(){
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=inventory(f);if(fclose(f)||rc||!n)exit(2);std::string result(p,n);free(p);return result;
}
static std::string value(vpiHandle p,unsigned i){
 s_vpi_value v={};v.format=i==2?vpiRealVal:i==3?vpiStringVal:vpiHexStrVal;vpi_get_value(p,&v);
 if(i==2){if(v.value.real!=1.5)exit(2);return "1.5";}
 return v.value.str;
}
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);bool enabled=!strcmp(mode,"on");++round_id;
 if(enabled){inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_inventory");if(!inventory)exit(2);}
 std::string before=enabled?snapshot():"";printf("ROUND %u\n",round_id);
 const char*names[]={"test.P","test.W","test.R","test.S"};const char*expected[]={"3","123456789abcdef01234","1.5","A B"};
 for(unsigned i=0;i<4;++i){
  auto p=vpi_handle_by_name(names[i],0);if(!p||vpi_get(vpiType,p)!=vpiParameter||value(p,i)!=expected[i])exit(2);
  int size=vpi_get(vpiSize,p);auto scope=vpi_handle(vpiScope,p);
  for(unsigned api=0;api<2;++api){
   int rc=api?vpi_release_handle(p):vpi_free_object(p);
   auto again=vpi_handle_by_name(names[i],0);
   if(rc!=1||again!=p||value(again,i)!=expected[i]||vpi_get(vpiSize,again)!=size||vpi_handle(vpiScope,again)!=scope)exit(2);
   if(enabled&&snapshot()!=before)exit(2);
   printf("RELEASE %u %s %u %d SAME\n",round_id,names[i],api,rc);
  }
 }
 if(enabled){printf("IMAGE before%u\n%sIMAGE_END\n",round_id,before.c_str());auto after=snapshot();printf("IMAGE after%u\n%sIMAGE_END\n",round_id,after.c_str());}
 return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$parameter_handle_release";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
