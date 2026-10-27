#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <algorithm>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*inventory)(FILE*);
static std::string snapshot(){
 if(!inventory)return "";
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=inventory(f);if(fclose(f)||rc)exit(2);std::string s(p,n);free(p);return s;
}
static void unchanged(const char*field,const std::string&before){
 if(inventory){auto after=snapshot();if(after!=before)exit(2);printf("IMAGE %s\n%s",field,after.c_str());}
}
static double realtime(vpiHandle h){s_vpi_time t={};t.type=vpiScaledRealTime;vpi_get_time(h,&t);return t.real;}
static PLI_INT32 run(PLI_BYTE8*){
 auto scope=dynamic_cast<__vpiScope*>(vpi_handle_by_name("test",0));
 auto signal=vpi_handle_by_name("test.value",0);if(!scope||!signal||scope->is_automatic())exit(2);
 const char*mode=getenv("K7658_SCOPE_REFERENTS");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_inventory");if(!inventory)exit(2);
 }
 auto before=snapshot();if(inventory)printf("IMAGE before\n%s",before.c_str());
 int units=scope->time_units;unsigned line=scope->lineno;
 if(units!=-9||realtime(scope)!=1.)exit(2);
 printf("BASE %.3f\n",realtime(scope));
 scope->time_units=-6;if(vpi_get(vpiTimeUnit,scope)!=-6)exit(2);
 printf("UNITS %.3f\n",realtime(scope));unchanged("units",before);scope->time_units=units;
 scope->lineno=line+17;if(vpi_get(vpiLineNo,scope)!=(int)line+17)exit(2);
 printf("LINE_CHANGED 17\n");unchanged("line",before);scope->lineno=line;
 auto intern=scope->intern;auto found=std::find(scope->intern.begin(),scope->intern.end(),signal);
 if(found==scope->intern.end())exit(2);scope->intern.erase(found);
 if(vpi_handle_by_name("test.value",0))exit(2);
 printf("LOOKUP_MISSING 1\n");unchanged("intern",before);scope->intern=intern;
 if(snapshot()!=before||realtime(scope)!=1.||vpi_get(vpiLineNo,scope)!=(int)line||vpi_handle_by_name("test.value",0)!=signal)exit(2);
 printf("RESTORED 1\n");return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$scope_referents";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
