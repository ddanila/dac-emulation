#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <dlfcn.h>
#include "vpi_priv.h"
static std::vector<int(*)(FILE*)> inventories;static unsigned round_id;
static int integer(vpiHandle h){s_vpi_value v={};v.format=vpiIntVal;vpi_get_value(h,&v);return v.value.integer;}
static std::string snapshot(){
 if(inventories.empty())return "";char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 for(auto fn:inventories)if(fn(f))exit(2);
 if(fclose(f))exit(2);std::string s(p,n);free(p);return s;
}
static void image(const char*label,const std::string&s){if(!inventories.empty())printf("IMAGE %s%u\n%sIMAGE_END\n",label,round_id,s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 auto visible=dynamic_cast<__vpiSignal*>(vpi_handle_by_name("test.visible",0));
 auto hidden=dynamic_cast<__vpiSignal*>(vpi_handle_by_name("test.hidden",0));
 auto parameter=dynamic_cast<__vpiBinaryConst*>(vpi_handle_by_name("test.P",0));
 auto memory=dynamic_cast<__vpiArray*>(vpi_handle_by_name("test.memory",0));
 if(!visible||!hidden||!parameter||!memory||hidden->bits||hidden->is_netarray)exit(2);
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 if(!strcmp(mode,"on")&&inventories.empty()){
  auto admit=(unsigned long long(*)(vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_admit");
  if(!admit||!admit(visible))exit(2);
  for(auto name:{"robotron_vvp_scope_metadata_inventory","robotron_vvp_scope_metadata_reference_inventory","robotron_vvp_signal_handle_inventory","robotron_vvp_port_payload_inventory","robotron_vvp_array_inventory"}){
   auto fn=(int(*)(FILE*))dlsym(RTLD_DEFAULT,name);if(!fn)exit(2);inventories.push_back(fn);
  }
 }
 ++round_id;printf("ROUND %u\n",round_id);
 if(integer(hidden)!=-6||integer(parameter)!=3||strcmp(vpi_get_str(vpiName,memory),"memory"))exit(2);
 auto before=snapshot();image("before",before);
 hidden->signed_flag=0;if(integer(hidden)!=10)exit(2);printf("SIGNAL -6 10\n");
 auto changed=snapshot();if(changed!=before)exit(2);image("signal",changed);hidden->signed_flag=1;
 auto bit=parameter->bits.value(0);parameter->bits.set_bit(0,BIT4_0);
 if(integer(parameter)!=2)exit(2);printf("PARAMETER 3 2\n");
 changed=snapshot();if(changed!=before)exit(2);image("parameter",changed);parameter->bits.set_bit(0,bit);
 const char*name=memory->name;memory->name="Xemory";
 if(strcmp(vpi_get_str(vpiName,memory),"Xemory"))exit(2);printf("MEMORY memory Xemory\n");
 changed=snapshot();if(changed!=before)exit(2);image("memory",changed);memory->name=name;
 if(snapshot()!=before||integer(hidden)!=-6||integer(parameter)!=3||strcmp(vpi_get_str(vpiName,memory),"memory"))exit(2);
 image("restored",before);printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$scope_payload_gaps";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
