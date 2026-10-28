#define _GNU_SOURCE
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static unsigned round_id;
static int(*control)(unsigned,unsigned);
static int(*inventories[3])(FILE*);
static std::string snapshot(unsigned refused){
 std::string all;
 for(unsigned i=0;i<3;++i){
  char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);int rc=inventories[i](f);if(fclose(f))exit(2);
  bool reject=refused==2||(refused==1&&i==0);
  if(reject){if(rc>=0||n)exit(2);}else{if(rc||!n)exit(2);all+=std::string(p,n);}
  free(p);
 }
 return all;
}
static void image(const std::string&label){printf("IMAGE %s\n%sIMAGE_END\n",label.c_str(),snapshot(0).c_str());}
static vpiHandle value(const char*name,unsigned kind){
 auto p=vpi_handle_by_name(name,0);if(!p||vpi_get(vpiType,p)!=vpiParameter)exit(2);
 s_vpi_value v={};v.format=kind==0?vpiBinStrVal:kind==1?vpiRealVal:vpiStringVal;vpi_get_value(p,&v);
 if(kind==0&&std::string(v.value.str)!=std::string(79,'x')+"1")exit(2);
 if(kind==1&&v.value.real!=2.5)exit(2);
 if(kind==2&&std::string(v.value.str)!="G R")exit(2);
 return p;
}
static void destroy(vpiHandle p,bool enabled,unsigned phase){
 auto scope=dynamic_cast<__vpiScope*>(vpi_handle(vpiScope,p));if(!scope)exit(2);
 auto entry=std::find(scope->intern.begin(),scope->intern.end(),p);if(entry==scope->intern.end())exit(2);
 // Invoke the real virtual destructor and free the diagnostic allocation.
 if(phase==0){if(!control||control(1,atoi(getenv("K7658_PARAMETER_KIND")))!=1)exit(2);}
 else delete p;
 if(enabled){snapshot(2);printf("STALE_REFUSED %u %u 3\n",round_id,phase);}
 if(phase==0){if(control(2,atoi(getenv("K7658_PARAMETER_KIND")))!=1)exit(2);}
 else scope->intern.erase(entry);
}
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_PAYLOAD");const char*k=getenv("K7658_PARAMETER_KIND");if(!mode||!k)exit(2);unsigned kind=atoi(k);if(kind>2)exit(2);bool enabled=!strcmp(mode,"on");++round_id;printf("ROUND %u\n",round_id);
 control=(int(*)(unsigned,unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_refusal_cycle");auto add=control;auto normal=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_add");
 if(enabled){const char*names[]={"robotron_vvp_parameter_inventory","robotron_vvp_scope_metadata_inventory","robotron_vvp_scope_metadata_reference_inventory"};for(unsigned i=0;i<3;++i){inventories[i]=(int(*)(FILE*))dlsym(RTLD_DEFAULT,names[i]);if(!inventories[i])exit(2);}if(!add||!normal)exit(2);image("before"+std::to_string(round_id));}
 if(add){
  if(!normal||control(99,kind)!=-1||control(0,3)!=-1||control(1,kind)!=-1||control(2,kind)!=-1||control(0,kind)!=1||control(0,kind)!=-1||control(1,(kind+1)%3)!=-1||control(2,kind)!=-1||normal(kind)!=-1)exit(2);
  char name[100];snprintf(name,sizeof(name),"test.__unsupported_%u_%u",kind,round_id);auto unsupported=value(name,kind);
  printf("UNSUPPORTED %u %u\n",round_id,kind);
  if(enabled){snapshot(1);printf("REFUSED %u\n",round_id);}
  destroy(unsupported,enabled,0);if(enabled)image("recovered"+std::to_string(round_id));
  if(normal(kind)!=1)exit(2);snprintf(name,sizeof(name),"test.__growth_%u_%u",kind,round_id);auto supported=value(name,kind);
  printf("SUPPORTED %u %u\n",round_id,kind);if(enabled)image("supported"+std::to_string(round_id));
  destroy(supported,enabled,1);if(enabled)image("restored"+std::to_string(round_id));
 }
 return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$parameter_refusal_recovery";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
