#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static char users[]="ABC";
static vpiHandle callbacks[3],object;
static PLI_INT32 changed(p_cb_data data){
 s_vpi_time time={.type=vpiSimTime};vpi_get_time(NULL,&time);
 printf("CALLBACK %u %c %d %d\n",time.low,*data->user_data,data->value->value.vector[0].aval,data->value->value.vector[0].bval);return 0;
}
static char* image(int(*api)(FILE*)){
 char* p=NULL;size_t n=0;FILE* f=open_memstream(&p,&n);if(!f)exit(2);
 int r=api(f);if(fclose(f)||r)exit(2);return p;
}
static PLI_INT32 watch(PLI_BYTE8*unused){
 (void)unused;object=vpi_handle_by_name("probe.a",NULL);if(!object)exit(2);
 for(int i=0;i<3;i++){
  s_vpi_time time={.type=vpiSuppressTime};s_vpi_value value={.format=vpiVectorVal};s_cb_data cb={0};
  cb.reason=cbValueChange;cb.cb_rtn=changed;cb.obj=object;cb.time=&time;cb.value=&value;cb.user_data=users+i;
  callbacks[i]=vpi_register_cb(&cb);if(!callbacks[i])exit(2);
 }
 return 0;
}
static PLI_INT32 cancel(PLI_BYTE8*unused){
 (void)unused;const char*mode=getenv("K7658_CALLBACK_OWNERSHIP");if(!mode)exit(2);
 if(!strcmp(mode,"no-cancel"))return 0;
 int(*api)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_wire_inventory");
 unsigned long long(*identity)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle)=dlsym(RTLD_DEFAULT,"robotron_vvp_value_identity");
 char*before=NULL;unsigned long long id=0;
 if(!strcmp(mode,"observe")){
  if(!api||!identity)exit(2);before=image(api);id=identity(callbacks[1],changed,users+1,object);if(!id)exit(2);
 }
 if(!vpi_remove_cb(callbacks[1]))exit(2);
 if(before){
  char*after=image(api);if(strcmp(before,after)||identity(callbacks[1],changed,users+1,object)!=0)exit(2);
  printf("OWN_BEFORE\n%sOWN_AFTER\n%sOWN_CANCELLED %llu\n",before,after,id);free(before);free(after);
 }
 return 0;
}
static void setup(void){
 s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname="$ownership_watch";t.calltf=watch;vpi_register_systf(&t);
 t.tfname="$ownership_cancel";t.calltf=cancel;vpi_register_systf(&t);
}
void(*vlog_startup_routines[])(void)={setup,0};
