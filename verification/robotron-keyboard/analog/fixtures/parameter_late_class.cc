#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static unsigned round_id;
static int(*inventory)(FILE*);
static void snapshot(bool refuse){
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);int rc=inventory(f);if(fclose(f))exit(2);
 if(refuse){if(rc>=0||n)exit(2);printf("REFUSED %u\n",round_id);}
 else{if(rc||!n)exit(2);printf("IMAGE initial\n%sIMAGE_END\n",p);}
 free(p);
}
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_PAYLOAD");const char*k=getenv("K7658_PARAMETER_KIND");if(!mode||!k)exit(2);unsigned kind=atoi(k);if(kind>2)exit(2);bool enabled=!strcmp(mode,"on");++round_id;printf("ROUND %u\n",round_id);
 auto add=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_add_unsupported");
 auto normal=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_add");
 auto count=(unsigned(*)())dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_unsupported_count");
 if(enabled){inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_inventory");if(!inventory||!add)exit(2);if(round_id==1)snapshot(false);}
 if(add){
  if(!count||!normal)exit(2);
  if(round_id==1){if(count()!=0||add(3)!=-1||add(kind)!=1)exit(2);printf("ADDED %u\n",kind);}
  if(count()!=1||add(kind)!=-1||normal(kind)!=-1)exit(2);
  char name[100];snprintf(name,sizeof(name),"test.__unsupported_%u_1",kind);auto p=vpi_handle_by_name(name,0);if(!p||vpi_get(vpiType,p)!=vpiParameter)exit(2);
  s_vpi_value v={};v.format=kind==0?vpiBinStrVal:kind==1?vpiRealVal:vpiStringVal;vpi_get_value(p,&v);
  if(kind==0&&std::string(v.value.str)!=std::string(79,'x')+"1")exit(2);
  if(kind==1&&v.value.real!=2.5)exit(2);
  if(kind==2&&std::string(v.value.str)!="G R")exit(2);
  printf("VALUE %u %u UNCHANGED\n",round_id,kind);
  if(enabled)snapshot(true);
 }
 return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$parameter_late_class";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
