#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <initializer_list>
#include "vpi_user.h"
static const char* names[]={"robotron_vvp_signal_handle_inventory","robotron_vvp_scope_signal_inventory"};
static const char* signals[]={"test.clk","test.a","test.b","test.left.clk","test.left.q","test.left.index","test.right.clk","test.right.q","test.right.index"};
static PLI_INT32 observe(p_cb_data cb){
 if(!getenv("TEARDOWN_OBSERVE")||strcmp(getenv("TEARDOWN_OBSERVE"),"on"))return 0;
 if(cb->reason==cbStartOfSimulation){
  auto admit=(unsigned long long(*)(vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_admit");if(!admit)exit(2);
  for(auto name:signals){
   auto h=vpi_handle_by_name(name,0);if(!h)exit(2);
   auto id=admit(h);if(!id)exit(2);
   s_vpi_value value={};value.format=vpiIntVal;vpi_get_value(vpi_handle(vpiLeftRange,h),&value);int left=value.value.integer;
   vpi_get_value(vpi_handle(vpiRightRange,h),&value);int right=value.value.integer;
   auto a=vpi_handle_by_index(h,left),b=vpi_handle_by_index(h,right);if(!a||!b)exit(2);
   printf("SIGNAL_BIND %s %llu %p %p %p\n",name,id,(void*)h,(void*)a,(void*)b);
  }
 }
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
