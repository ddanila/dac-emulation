#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <algorithm>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*metadata)(FILE*),(*reference)(FILE*),(*membership)(FILE*),(*signals)(FILE*);
static unsigned long long(*admit)(vpiHandle);static unsigned round_id;
static std::string snapshot(int(*fn)(FILE*),bool refuse=false){
 if(!fn)return "";char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=fn(f);if(fclose(f))exit(2);std::string s(p,n);free(p);
 if(refuse?(rc>=0||n):rc!=0)exit(2);return s;
}
static std::string bundle(){return snapshot(metadata)+snapshot(reference)+snapshot(membership)+snapshot(signals);}
static void print(const char*name,const std::string&s){if(metadata)printf("IMAGE %s%u\n%sBUNDLE_END\n",name,round_id,s.c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 auto scope=dynamic_cast<__vpiScope*>(vpi_handle_by_name("test",0));
 auto value=vpi_handle_by_name("test.value",0);auto child=vpi_handle_by_name("test.child.value",0);
 if(!scope||!value||!child)exit(2);
 const char*mode=getenv("K7658_SCOPE_METADATA_BINDINGS");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  metadata=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_metadata_inventory");
  reference=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_metadata_reference_inventory");
  membership=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_inventory");
  signals=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_inventory");
  admit=(unsigned long long(*)(vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_admit");
  if(!metadata||!reference||!membership||!signals||!admit||!admit(value)||!admit(child))exit(2);
 }
 ++round_id;printf("ROUND %u\n",round_id);auto before=bundle();print("before",before);
 auto intern=scope->intern;auto found=std::find(scope->intern.begin(),scope->intern.end(),value);
 if(found==scope->intern.end())exit(2);scope->intern.erase(found);auto missing=bundle();
 if(metadata&&missing==before)exit(2);print("missing",missing);printf("OMITTED signal\n");scope->intern=intern;
 auto item=scope->intern.front();scope->intern.front()=reinterpret_cast<vpiHandle>(1);
 snapshot(reference,true);printf("REFUSED intern\n");scope->intern.front()=item;
 auto after=bundle();if(after!=before)exit(2);print("restored",after);printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$scope_metadata_bindings";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
