#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*metadata)(FILE*);static unsigned round_id;
static std::string snapshot(bool refuse=false){
 if(!metadata)return "";char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=metadata(f);if(fclose(f))exit(2);std::string s(p,n);free(p);if(refuse?(rc>=0||n):rc!=0)exit(2);return s;
}
static std::vector<int> bits(vpiHandle port){
 std::vector<int> result;auto iter=vpi_iterate(vpiBit,port);if(!iter)exit(2);
 while(auto bit=vpi_scan(iter))result.push_back(vpi_get(vpiBit,bit));return result;
}
static void image(const char*label,const std::string&s){if(metadata)printf("IMAGE %s%u\n%sIMAGE_END\n",label,round_id,s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  metadata=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_port_payload_inventory");
  if(!metadata)exit(2);
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
 auto swapped=snapshot();if(metadata&&swapped==before)exit(2);image("swapped",swapped);
 std::swap(port->port_bits_[0],port->port_bits_[1]);
 auto saved=port->port_bits_[0];port->port_bits_[0]=reinterpret_cast<vpiPortBitInfo*>(1);
 snapshot(true);printf("REFUSED foreign\n");
 // Never iterate/dereference the intentionally foreign bit pointer.
 port->port_bits_[0]=saved;
 auto vector=port->port_bits_;
 port->port_bits_[1]=port->port_bits_[0];snapshot(true);printf("REFUSED duplicate\n");port->port_bits_=vector;
 port->port_bits_.pop_back();snapshot(true);printf("REFUSED missing\n");port->port_bits_=vector;
 port->port_bits_.push_back(port->port_bits_[0]);snapshot(true);printf("REFUSED overflow\n");port->port_bits_=vector;
 char*name=const_cast<char*>(port->robotron_name());char first=name[0];name[0]='X';
 auto renamed=snapshot();if(metadata&&renamed==before)exit(2);image("renamed",renamed);name[0]=first;

 if(bits(port)!=std::vector<int>({0,1,2,3})||snapshot()!=before)exit(2);
 image("restored",before);printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$port_payload";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
