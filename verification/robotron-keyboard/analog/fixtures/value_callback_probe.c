#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static char users[3]={'A','B','C'};
static vpiHandle handles[3],objects[3];
static unsigned long long identities[3];
static PLI_INT32 callback(p_cb_data cb) {
 s_vpi_time now={.type=vpiSimTime};vpi_get_time(NULL,&now);
 printf("CALLBACK %u %u %c %d %d\n",now.high,now.low,*cb->user_data,
        cb->value->value.vector[0].aval,cb->value->value.vector[0].bval);
 return 0;
}
static void observe(int stage) {
 unsigned long long (*lookup)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle)=dlsym(RTLD_DEFAULT,"robotron_vvp_value_identity");
 int (*toggle)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle,int)=dlsym(RTLD_DEFAULT,"robotron_vvp_value_toggle");
 printf("VQ_API %d %d\n",stage,lookup!=NULL);
 const char *mode=getenv("K7658_VALUE_PROBE");
 if(!mode || !strcmp(mode,"off")) return;
 if(!lookup || !toggle || lookup((void*)1,callback,users,objects[0])!=0) exit(2);
 for(int i=0;i<3;i++) {
  unsigned long long first=lookup(handles[i],callback,users+i,objects[i]);
  unsigned long long second=lookup(handles[i],callback,users+i,objects[i]);
  int active=(i==1 || (i==0 && stage<2) || (i==2 && stage<4));
  if(first!=second || (!!first)!=active) exit(2);
  if(stage==0) identities[i]=first;
  else if(active && first!=identities[i]) exit(2);
  if(lookup(handles[i],callback,users+((i+1)%3),objects[i]) || lookup(handles[i],callback,users+i,objects[i==1?0:1])) exit(2);
  printf("VQ_LINK %d %d %llu\n",stage,i,first);
  if(!strcmp(mode,"corrupt") && active) for(int field=0;field<4;field++) {
   if(toggle(handles[i],callback,users+i,objects[i],field)!=1) exit(2);
   int rejected=lookup(handles[i],callback,users+i,objects[i])==0;
   if(toggle(handles[i],callback,users+i,objects[i],field)!=1) exit(2);
   int restored=lookup(handles[i],callback,users+i,objects[i])==first;
   printf("VQ_FAULT %d %d %d %d %d\n",stage,i,field,rejected,restored);
   if(!rejected || !restored) exit(2);
  }
 }
}
static PLI_INT32 watch(PLI_BYTE8 *unused) {
 (void)unused;
 for(int i=0;i<3;i++) {
  objects[i]=vpi_handle_by_name(i==1?"probe.b":"probe.a",NULL);
  s_vpi_time time={.type=vpiSuppressTime};s_vpi_value value={.format=vpiVectorVal};
  s_cb_data cb={0};cb.reason=cbValueChange;cb.cb_rtn=callback;cb.obj=objects[i];
  cb.time=&time;cb.value=&value;cb.user_data=users+i;
  if(!objects[i] || !(handles[i]=vpi_register_cb(&cb))) exit(2);
 }
 observe(0);return 0;
}
static PLI_INT32 inspect(PLI_BYTE8 *unused) {(void)unused;observe(1);return 0;}
static PLI_INT32 cancel(PLI_BYTE8 *unused) {(void)unused;if(!vpi_remove_cb(handles[0])) exit(2);observe(2);return 0;}
static PLI_INT32 retired(PLI_BYTE8 *unused) {(void)unused;observe(3);return 0;}
static PLI_INT32 cancel_head(PLI_BYTE8 *unused) {(void)unused;if(!vpi_remove_cb(handles[2])) exit(2);observe(4);return 0;}
static PLI_INT32 retired_head(PLI_BYTE8 *unused) {(void)unused;observe(5);return 0;}
static void setup(void) {
 const char *names[]={"$value_watch","$value_observe","$value_cancel","$value_retired","$value_cancel_head","$value_retired_head"};
 PLI_INT32 (*functions[])(PLI_BYTE8*)={watch,inspect,cancel,retired,cancel_head,retired_head};
 for(int i=0;i<6;i++) {s_vpi_systf_data d={0};d.type=vpiSysTask;d.tfname=(PLI_BYTE8*)names[i];d.calltf=functions[i];vpi_register_systf(&d);}
}
void (*vlog_startup_routines[])(void)={setup,0};
