#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <vpi_user.h>
#include "scope_compare.h"
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_REFERENTS");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  auto inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_inventory");
  auto admit=(unsigned long long(*)(vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_admit");
  if(!inventory||!admit)exit(2);
  char*p=0;size_t size=0;FILE*f=open_memstream(&p,&size);if(!f)exit(2);
  if(inventory(f)||fclose(f)||strcmp(p,"VSH_BEGIN 1 1000\nVSH_END 0\n"))exit(2);free(p);
  auto h=vpi_handle_by_name("test.x",0);if(!h||!admit(h))exit(2);
  p=0;size=0;f=open_memstream(&p,&size);if(!f)exit(2);
  int r=inventory(f);if(fclose(f)||r!=-1||size)exit(2);free(p);
 }
 printf("SCOPE_ADMISSION_DONE\n");return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$scope_admission";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
