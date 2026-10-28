#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <initializer_list>
#include "vpi_user.h"
static const char* names[]={
 "robotron_vvp_scope_metadata_inventory",
 "robotron_vvp_scope_metadata_reference_inventory",
 "robotron_vvp_parameter_inventory",
 "robotron_vvp_memory_metadata_inventory",
 "robotron_vvp_array_inventory",
 "robotron_vvp_array_compact_inventory",
 "robotron_vvp_port_payload_inventory"};
static PLI_INT32 observe(p_cb_data cb){
 if(!getenv("TEARDOWN_OBSERVE")||strcmp(getenv("TEARDOWN_OBSERVE"),"on"))return 0;
 for(unsigned i=0;i<sizeof(names)/sizeof(*names);++i){
  auto fn=(int(*)(FILE*))dlsym(RTLD_DEFAULT,names[i]);if(!fn)exit(2);
  char*data=0;size_t size=0;FILE*f=open_memstream(&data,&size);if(!f)exit(2);
  int rc=fn(f);if(fclose(f)||rc||!size)exit(2);
  printf("OBSERVER_BEGIN %d %s\n",cb->reason,names[i]);
  fwrite(data,1,size,stdout);printf("OBSERVER_END\n");free(data);
 }
 return 0;
}
static void setup(){
 for(int reason:{cbStartOfSimulation,cbEndOfSimulation}){
  s_cb_data cb={};cb.reason=reason;cb.cb_rtn=observe;
  if(!vpi_register_cb(&cb))exit(2);
 }
}
// Every VPI module exports this loader table under the same required symbol.
// Exclude only this immutable loader table from ASAN global ODR instrumentation;
// callback code and all runtime allocations remain instrumented.
extern "C"{__attribute__((no_sanitize("address"))) void(*vlog_startup_routines[])(void)={setup,0};}

// VPI unload occurs after root/pool cleanup in this candidate's final_cleanup.
// Reading registries here tests post-cleanup refusal, not user callback ordering.
__attribute__((destructor)) static void after_cleanup(){
 if(!getenv("TEARDOWN_OBSERVE")||strcmp(getenv("TEARDOWN_OBSERVE"),"on"))return;
 fprintf(stdout,"POST_CLEANUP_ENTER\n");fflush(stdout);
 for(unsigned i=0;i<sizeof(names)/sizeof(*names);++i){
  auto fn=(int(*)(FILE*))dlsym(RTLD_DEFAULT,names[i]);if(!fn)exit(2);
  char*data=0;size_t size=0;FILE*f=open_memstream(&data,&size);if(!f)exit(2);
  int rc=fn(f);if(fclose(f))exit(2);
  printf("POST_RESULT %s %d %zu\n",names[i],rc,size);fflush(stdout);
  if(size)fwrite(data,1,size,stdout);free(data);fflush(stdout);
 }
 fprintf(stdout,"POST_CLEANUP_RETURN\n");fflush(stdout);
}
