#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static char users[]="ABCD";
static vpiHandle callbacks[4],object;
static const char*mode;
static unsigned stage;
static int added;
static int observing(void){return strcmp(mode,"off")!=0;}
static char* snapshot(int*r,size_t*n){
 int(*api)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_inventory");if(!api)exit(2);
 char*p=NULL;*n=0;FILE*f=open_memstream(&p,n);if(!f)exit(2);*r=api(f);if(fclose(f))exit(2);return p;
}
static void refusal(const char*label){if(observing()){int r;size_t n;char*p=snapshot(&r,&n);if(r!=-1||n)exit(2);free(p);puts(label);}}
static void add(int index);
static PLI_INT32 changed(p_cb_data cb){
 refusal("REG_ACTIVE_REFUSED");
 s_vpi_time t={.type=vpiSimTime};vpi_get_time(NULL,&t);
 printf("CALLBACK %u %c %d %d\n",t.low,*cb->user_data,cb->value->value.vector[0].aval,cb->value->value.vector[0].bval);
 if(*cb->user_data=='A'&&!added){added=1;add(1);refusal("REG_ACTIVE_AFTER_ADD_REFUSED");}
 return 0;
}
static void add(int index){
 s_vpi_time t={.type=vpiSuppressTime};s_vpi_value v={.format=vpiVectorVal};s_cb_data cb={0};
 cb.reason=cbValueChange;cb.cb_rtn=changed;cb.obj=object;cb.time=&t;cb.value=&v;cb.user_data=users+index;
 callbacks[index]=vpi_register_cb(&cb);if(!callbacks[index])exit(2);
 refusal("REG_NEW_REFUSED");
}
static void admit(int index){if(observing()){
 unsigned long long(*api)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle)=dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_admit");if(!api)exit(2);
 unsigned long long id=api(callbacks[index],changed,users+index,object);if(!id)exit(2);printf("REG_ADMIT %c %llu\n",users[index],id);
}}
static void observe(void){
 printf("REG_STAGE %u\n",stage);
 if(observing()){
  if(stage==2)refusal("REG_UNADMITTED_REFUSED");
  else{int r;size_t n;char*p=snapshot(&r,&n);if(r)exit(2);char*q=snapshot(&r,&n);if(r||strcmp(p,q))exit(2);printf("REG_BEFORE\n%sREG_REPEAT\n%s",p,q);free(p);free(q);}
 }
 printf("REG_DONE %u\n",stage++);
}
static PLI_INT32 start(PLI_BYTE8*u){(void)u;mode=getenv("K7658_CALLBACK_LISTS");if(!mode)exit(2);object=vpi_handle_by_name("probe.a",NULL);if(!object)exit(2);observe();add(0);admit(0);observe();return 0;}
static PLI_INT32 inspect(PLI_BYTE8*u){(void)u;observe();return 0;}
static PLI_INT32 admit_b(PLI_BYTE8*u){(void)u;admit(1);observe();return 0;}
static PLI_INT32 replace(PLI_BYTE8*u){(void)u;if(!vpi_remove_cb(callbacks[0]))exit(2);add(2);admit(2);observe();return 0;}
static PLI_INT32 cancel(PLI_BYTE8*u){(void)u;for(int i=1;i<=2;i++)if(!vpi_remove_cb(callbacks[i]))exit(2);observe();return 0;}
static PLI_INT32 restart(PLI_BYTE8*u){(void)u;add(3);admit(3);observe();return 0;}
static void setup(void){
 const char*names[]={"$reg_start","$reg_inspect","$reg_admit","$reg_replace","$reg_cancel","$reg_restart"};
 PLI_INT32(*calls[])(PLI_BYTE8*)={start,inspect,admit_b,replace,cancel,restart};
 for(int i=0;i<6;i++){s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname=(char*)names[i];t.calltf=calls[i];vpi_register_systf(&t);}
}
void(*vlog_startup_routines[])(void)={setup,0};
