#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
// VPI modules require this duplicate export. Do not instrument the loader table.
extern "C"{__attribute__((no_sanitize("address"))) void(*vlog_startup_routines[])(void)={0};}
__attribute__((destructor)) static void post_cleanup(){
 if(!getenv("ROBOTRON_TEARDOWN_TRACE"))return;
 const char* names[]={"scope_metadata","scope_metadata_reference","parameter","memory_metadata","array","array_compact","port_payload"};
 printf("POST_CLEANUP_ENTER\n");fflush(stdout);
 for(auto name:names){
  char symbol[128];snprintf(symbol,sizeof(symbol),"robotron_vvp_%s_inventory",name);
  auto fn=(int(*)(FILE*))dlsym(RTLD_DEFAULT,symbol);if(!fn)exit(2);
  char*data=0;size_t size=0;FILE*f=open_memstream(&data,&size);if(!f)exit(2);
  int rc=fn(f);if(fclose(f))exit(2);
  printf("POST_RESULT %s %d %zu\n",symbol,rc,size);fflush(stdout);
  if(size)fwrite(data,1,size,stdout);free(data);fflush(stdout);
 }
 printf("POST_CLEANUP_RETURN\n");fflush(stdout);
}
