#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*metadata)(FILE*),(*reference)(FILE*);static unsigned round_id;
static std::string snapshot(){
 if(!metadata)return "";char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=metadata(f);if(!rc)rc=reference(f);if(fclose(f)||rc)exit(2);std::string s(p,n);free(p);return s;
}
static std::vector<int> bits(vpiHandle port){
 std::vector<int> result;auto iter=vpi_iterate(vpiBit,port);if(!iter)exit(2);
 while(auto bit=vpi_scan(iter))result.push_back(vpi_get(vpiBit,bit));return result;
}
static void image(const char*label,const std::string&s){if(metadata)printf("IMAGE %s%u\n%sIMAGE_END\n",label,round_id,s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_REFERENTS");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  metadata=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_metadata_inventory");
  reference=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_metadata_reference_inventory");
  if(!metadata||!reference)exit(2);
 }
 auto scope=vpi_handle_by_name("test.child",0);if(!scope)exit(2);
 auto iter=vpi_iterate(vpiPort,scope);if(!iter)exit(2);vpiPortInfo*port=0;
 while(auto item=vpi_scan(iter)){if(!port)port=dynamic_cast<vpiPortInfo*>(item);}
 if(!port||port->port_bits_.size()!=4)exit(2);
 ++round_id;printf("ROUND %u\n",round_id);
 if(bits(port)!=std::vector<int>({0,1,2,3}))exit(2);printf("ORDER before 0 1 2 3\n");
 auto before=snapshot();image("before",before);
 std::swap(port->port_bits_[0],port->port_bits_[1]);
 if(bits(port)!=std::vector<int>({1,0,2,3}))exit(2);printf("ORDER swapped 1 0 2 3\n");
 auto swapped=snapshot();if(swapped!=before)exit(2);image("swapped",swapped);
 std::swap(port->port_bits_[0],port->port_bits_[1]);
 auto saved=port->port_bits_[0];port->port_bits_[0]=reinterpret_cast<vpiPortBitInfo*>(1);
 auto foreign=snapshot();if(foreign!=before)exit(2);image("foreign",foreign);
 // Never iterate/dereference the intentionally foreign bit pointer.
 port->port_bits_[0]=saved;
 if(bits(port)!=std::vector<int>({0,1,2,3})||snapshot()!=before)exit(2);
 image("restored",before);printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$port_referents";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
