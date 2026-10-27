#include "compact.h"
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static char users[]="AB";static vpiHandle objects[2],callbacks[2];
static const char*mode;static unsigned stage,depth;
static char* snapshot(int*r,size_t*n){
 int(*api)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_inventory");if(!api)exit(2);
 char*p=NULL;*n=0;FILE*f=open_memstream(&p,n);if(!f)exit(2);*r=api(f);if(fclose(f))exit(2);compact_check(*r);return p;
}
static void refusal(const char*where){if(strcmp(mode,"off")){int r;size_t n;char*p=snapshot(&r,&n);if(r!=-1||n)exit(2);free(p);printf("NEST_REFUSED %s %u\n",where,depth);}}
static void put(unsigned i,int value){s_vpi_value v={.format=vpiIntVal};v.value.integer=value;vpi_put_value(objects[i],&v,NULL,vpiNoDelay);}
static PLI_INT32 changed(p_cb_data cb){
 ++depth;s_vpi_time t={.type=vpiSimTime};vpi_get_time(NULL,&t);
 int entered=cb->value->value.vector[0].aval;
 printf("ENTER %u %c %u %d %d\n",t.low,*cb->user_data,depth,entered,cb->value->value.vector[0].bval);refusal("enter");
 if(*cb->user_data=='A' && entered==1 && depth==1)put(1,2);
 if(*cb->user_data=='B' && entered==2 && depth==2)put(0,3);
 refusal("exit");printf("EXIT %u %c %u %d %d\n",t.low,*cb->user_data,depth,cb->value->value.vector[0].aval,cb->value->value.vector[0].bval);
 --depth;return 0;
}
static void observe(void){
 if(depth)exit(2);printf("NEST_STAGE %u\n",stage);
 if(strcmp(mode,"off")){int r;size_t n;char*p=snapshot(&r,&n);if(r)exit(2);char*q=snapshot(&r,&n);if(r||strcmp(p,q))exit(2);printf("NEST_BEFORE\n%sNEST_REPEAT\n%s",p,q);free(p);free(q);}
 printf("NEST_DONE %u\n",stage++);
}
static PLI_INT32 start(PLI_BYTE8*u){
 (void)u;mode=getenv("K7658_CALLBACK_LISTS");if(!mode)exit(2);
 for(int i=0;i<2;i++){
  objects[i]=vpi_handle_by_name(i?"probe.b":"probe.a",NULL);if(!objects[i])exit(2);
  s_vpi_time t={.type=vpiSuppressTime};s_vpi_value v={.format=vpiVectorVal};s_cb_data cb={0};cb.reason=cbValueChange;cb.cb_rtn=changed;cb.obj=objects[i];cb.time=&t;cb.value=&v;cb.user_data=users+i;
  callbacks[i]=vpi_register_cb(&cb);if(!callbacks[i])exit(2);
  if(strcmp(mode,"off")){
   unsigned long long(*api)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle)=dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_admit");
   if(!api||!api(callbacks[i],changed,users+i,objects[i]))exit(2);
  }
 }
 observe();return 0;
}
static PLI_INT32 inspect(PLI_BYTE8*u){(void)u;observe();return 0;}
static void setup(void){const char*names[]={"$nest_start","$nest_inspect"};PLI_INT32(*calls[])(PLI_BYTE8*)={start,inspect};for(int i=0;i<2;i++){s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname=(char*)names[i];t.calltf=calls[i];vpi_register_systf(&t);}}
void(*vlog_startup_routines[])(void)={setup,0};
