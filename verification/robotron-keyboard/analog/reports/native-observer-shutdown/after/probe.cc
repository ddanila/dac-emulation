#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <initializer_list>
#include "vpi_user.h"
static int(*inventory)(FILE*);
static void inspect(const char*phase){
 printf("SWEEP_ENTER %s\n",phase);fflush(stdout);
 char*data=0;size_t bytes=0;FILE*f=open_memstream(&data,&bytes);if(!f)exit(2);
 const char*name=getenv("TEARDOWN_INVENTORY");int rc;
 if(!strcmp(name,"robotron_vvp_code_operand_inventory"))rc=((int(*)(FILE*,int))inventory)(f,0);
 else if(!strcmp(name,"robotron_vvp_sync_inventory")||!strcmp(name,"robotron_vvp_sync_family_inventory"))rc=((int(*)(FILE*,PLI_BYTE8*,PLI_INT32(*)(p_cb_data)))inventory)(f,0,0);
 else rc=inventory(f);
 if(fclose(f))exit(2);
 printf("SWEEP_RESULT %s %d %zu\n",phase,rc,bytes);
 if(bytes)fwrite(data,1,bytes,stdout);free(data);printf("SWEEP_END %s\n",phase);fflush(stdout);
}
static PLI_INT32 observe(p_cb_data cb){
 const char*name=getenv("TEARDOWN_INVENTORY");if(!name||!strcmp(name,"off"))return 0;
 if(cb->reason==cbStartOfSimulation){
  inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,name);if(!inventory)exit(2);
  auto admit=(unsigned long long(*)(vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_admit");if(!admit)exit(2);
  for(auto name:{"test.clk","test.left.index","test.right.index"}){
   auto h=vpi_handle_by_name(name,0);if(!h||!admit(h))exit(2);
  }
  printf("SWEEP_ADMITTED 3\n");
 }
 inspect(cb->reason==cbStartOfSimulation?"start":"end");return 0;
}
static void setup(){for(int reason:{cbStartOfSimulation,cbEndOfSimulation}){s_cb_data cb={};cb.reason=reason;cb.cb_rtn=observe;if(!vpi_register_cb(&cb))exit(2);}}
extern "C"{__attribute__((no_sanitize("address"))) void(*vlog_startup_routines[])(void)={setup,0};}
__attribute__((destructor)) static void unload(){if(inventory)inspect("post");}
