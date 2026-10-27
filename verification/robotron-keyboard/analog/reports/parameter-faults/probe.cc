#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_user.h"
static int(*inventory)(FILE*),(*toggle)(unsigned);static unsigned round_id;
static std::string snapshot(bool refuse=false){
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=inventory(f);if(fclose(f))exit(2);std::string s(p,n);free(p);if(refuse?(rc>=0||n):rc!=0)exit(2);return s;
}
static void image(const std::string&label,const std::string&s){printf("IMAGE %s%u\n%sIMAGE_END\n",label.c_str(),round_id,s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 ++round_id;printf("ROUND %u\n",round_id);
 if(!strcmp(mode,"on")){
  inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_inventory");
  toggle=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_toggle");if(!inventory||!toggle)exit(2);
  auto before=snapshot();image("before",before);if(toggle(16)!=-1||snapshot()!=before)exit(2);
  for(unsigned field=0;field<16;++field){
   if(toggle(field)!=1||toggle((field+1)%16)!=-1)exit(2);
   if(field<9){auto changed=snapshot();if(changed==before)exit(2);image("changed"+std::to_string(field)+"_",changed);}
   else{snapshot(true);printf("REFUSED %u %u\n",round_id,field);}
   if(toggle(field)!=1||snapshot()!=before)exit(2);image("restored"+std::to_string(field)+"_",snapshot());
  }
 }
 printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$parameter_faults";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
