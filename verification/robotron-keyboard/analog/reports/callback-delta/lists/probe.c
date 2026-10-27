#include "compact.h"
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static char users[]="ABC";static vpiHandle callbacks[3],object;static unsigned stage;
static const char*mode;
static char* snapshot(int *result,size_t*size){
 int(*api)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_inventory");if(!api)exit(2);
 char*p=NULL;*size=0;FILE*f=open_memstream(&p,size);if(!f)exit(2);*result=api(f);if(fclose(f))exit(2);compact_check(*result);return p;
}
static PLI_INT32 changed(p_cb_data data){
 if(strcmp(mode,"off")) {int r;size_t n;char*p=snapshot(&r,&n);if(r!=-1||n)exit(2);free(p);puts("LST_ACTIVE_REFUSED");}
 s_vpi_time time={.type=vpiSimTime};vpi_get_time(NULL,&time);
 printf("CALLBACK %u %c %d %d\n",time.low,*data->user_data,data->value->value.vector[0].aval,data->value->value.vector[0].bval);return 0;
}
static void observe(void){
 printf("LST_STAGE %u\n",stage);
 if(strcmp(mode,"off")) {
  int r;size_t n;char*before=snapshot(&r,&n);if(r)exit(2);char*repeat=snapshot(&r,&n);if(r||strcmp(before,repeat))exit(2);
  printf("LST_BEFORE\n%sLST_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt")) {
   unsigned long long(*identity)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle)=dlsym(RTLD_DEFAULT,"robotron_vvp_value_identity");
   int(*toggle)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle,int)=dlsym(RTLD_DEFAULT,"robotron_vvp_value_toggle");if(!identity||!toggle)exit(2);
   for(int i=0;i<3;i++)if(identity(callbacks[i],changed,users+i,object))for(int field=0;field<4;field++){
    if(toggle(callbacks[i],changed,users+i,object,field)!=1)exit(2);
    char*bad=snapshot(&r,&n);if(field==3?(r!=-1||n):(r||!strcmp(before,bad)))exit(2);
    printf("LST_FAULT %d %d %d\n%s",i,field,r,bad);free(bad);
    if(toggle(callbacks[i],changed,users+i,object,field)!=1)exit(2);
    char*restored=snapshot(&r,&n);if(r||strcmp(before,restored))exit(2);printf("LST_RESTORED\n%s",restored);free(restored);
   }
  }
  free(before);
 }
 printf("LST_DONE %u\n",stage++);
}
static PLI_INT32 watch(PLI_BYTE8*unused){
 (void)unused;mode=getenv("K7658_CALLBACK_LISTS");if(!mode)exit(2);
 object=vpi_handle_by_name("probe.a",NULL);if(!object)exit(2);
 for(int i=0;i<3;i++) {
  s_vpi_time time={.type=vpiSuppressTime};s_vpi_value value={.format=vpiVectorVal};s_cb_data cb={0};
  cb.reason=cbValueChange;cb.cb_rtn=changed;cb.obj=object;cb.time=&time;cb.value=&value;cb.user_data=users+i;
  callbacks[i]=vpi_register_cb(&cb);if(!callbacks[i])exit(2);
 }
 if(strcmp(mode,"off")) {
  int r;size_t n;char*p=snapshot(&r,&n);if(r!=-1||n)exit(2);free(p);puts("LST_UNADMITTED_REFUSED");
  unsigned long long(*admit)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle)=dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_admit");if(!admit)exit(2);
  for(int i=0;i<3;i++)if(!admit(callbacks[i],changed,users+i,object))exit(2);
 }
 observe();return 0;
}
static PLI_INT32 cancel_middle(PLI_BYTE8*u){(void)u;observe();if(!vpi_remove_cb(callbacks[1]))exit(2);observe();return 0;}
static PLI_INT32 cancel_head(PLI_BYTE8*u){(void)u;if(!vpi_remove_cb(callbacks[2]))exit(2);observe();return 0;}
static PLI_INT32 cancel_tail(PLI_BYTE8*u){(void)u;if(!vpi_remove_cb(callbacks[0]))exit(2);observe();return 0;}
static PLI_INT32 inspect(PLI_BYTE8*u){(void)u;observe();return 0;}
static void setup(void){
 const char*names[]={"$list_watch","$list_cancel_middle","$list_cancel_head","$list_cancel_tail","$list_inspect"};
 PLI_INT32(*functions[])(PLI_BYTE8*)={watch,cancel_middle,cancel_head,cancel_tail,inspect};
 for(int i=0;i<5;i++){s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname=(char*)names[i];t.calltf=functions[i];vpi_register_systf(&t);}
}
void(*vlog_startup_routines[])(void)={setup,0};
