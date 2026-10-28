#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include "vpi_user.h"
// VPI modules require this duplicate export. Do not instrument the loader table.
extern "C"{__attribute__((no_sanitize("address"))) void(*vlog_startup_routines[])(void)={0};}
__attribute__((destructor)) static void post_cleanup(){
 if(!getenv("ROBOTRON_TEARDOWN_TRACE"))return;
 const char* names[]={"robotron_vvp_arithmetic_delta_inventory","robotron_vvp_arithmetic_inventory","robotron_vvp_array_compact_inventory","robotron_vvp_array_inventory","robotron_vvp_assignment_inventory","robotron_vvp_assignment_raw_inventory","robotron_vvp_callback_list_delta_inventory","robotron_vvp_callback_list_inventory","robotron_vvp_callback_signal_inventory","robotron_vvp_callback_signal_reference_inventory","robotron_vvp_code_operand_inventory","robotron_vvp_concat_delta_inventory","robotron_vvp_concat_inventory","robotron_vvp_executing_inventory","robotron_vvp_gate_delta_inventory","robotron_vvp_gate_inventory","robotron_vvp_island_filter_inventory","robotron_vvp_island_inventory","robotron_vvp_island_queue_inventory","robotron_vvp_island_raw_delta_inventory","robotron_vvp_island_raw_inventory","robotron_vvp_memory_metadata_inventory","robotron_vvp_mux_delta_inventory","robotron_vvp_mux_inventory","robotron_vvp_net_delta_inventory","robotron_vvp_net_inventory","robotron_vvp_parameter_inventory","robotron_vvp_port_payload_inventory","robotron_vvp_primitive_inventory","robotron_vvp_queue_inventory","robotron_vvp_reduction_delta_inventory","robotron_vvp_reduction_inventory","robotron_vvp_resolver_delta_inventory","robotron_vvp_resolver_inventory","robotron_vvp_scope_inventory","robotron_vvp_scope_metadata_compact_inventory","robotron_vvp_scope_metadata_inventory","robotron_vvp_scope_metadata_reference_compact_inventory","robotron_vvp_scope_metadata_reference_inventory","robotron_vvp_scope_signal_inventory","robotron_vvp_signal_delta_inventory","robotron_vvp_signal_handle_inventory","robotron_vvp_signal_handle_reference_inventory","robotron_vvp_signal_inventory","robotron_vvp_sync_family_inventory","robotron_vvp_sync_inventory","robotron_vvp_thread_code_inventory","robotron_vvp_thread_compact_inventory","robotron_vvp_thread_inventory","robotron_vvp_thread_queue_inventory","robotron_vvp_wait_inventory","robotron_vvp_wire_delta_inventory","robotron_vvp_wire_inventory","robotron_vvp_wire_raw_delta_inventory","robotron_vvp_wire_raw_inventory"};
 printf("POST_CLEANUP_ENTER\n");fflush(stdout);
 for(auto name:names){
  char symbol[128];snprintf(symbol,sizeof(symbol),"%s",name);
  auto fn=(int(*)(FILE*))dlsym(RTLD_DEFAULT,symbol);if(!fn)exit(2);
  char*data=0;size_t size=0;FILE*f=open_memstream(&data,&size);if(!f)exit(2);
  int rc;
  if(!strcmp(name,"robotron_vvp_code_operand_inventory"))rc=((int(*)(FILE*,int))fn)(f,0);
  else if(!strcmp(name,"robotron_vvp_sync_inventory")||!strcmp(name,"robotron_vvp_sync_family_inventory"))rc=((int(*)(FILE*,PLI_BYTE8*,PLI_INT32(*)(p_cb_data)))fn)(f,0,0);
  else rc=fn(f);
  if(fclose(f))exit(2);
  printf("POST_RESULT %s %d %zu\n",symbol,rc,size);fflush(stdout);
  if(size)fwrite(data,1,size,stdout);free(data);fflush(stdout);
 }
 printf("POST_CLEANUP_RETURN\n");fflush(stdout);
}
