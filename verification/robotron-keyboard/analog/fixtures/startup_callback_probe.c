#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static char users[3];
static vpiHandle handles[3];
static int stage;
static PLI_INT32 callback(p_cb_data cb);
static void observe(void) {
 unsigned long long (*identity)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*)=dlsym(RTLD_DEFAULT,"robotron_vvp_start_identity");
 int (*toggle)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,int)=dlsym(RTLD_DEFAULT,"robotron_vvp_start_toggle");
 const char *mode=getenv("K7658_START_PROBE");
 printf("VS_API %d %d\n",stage,identity!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!identity || !toggle || identity((void*)1,callback,users)) exit(2);
  for(int i=0;i<3;i++) {
   unsigned long long id=identity(handles[i],callback,users+i);
   printf("VS_LINK %d %d %llu\n",stage,i,id);
   if(identity(handles[i],callback,users+(i+1)%3) || identity(handles[i],NULL,users+i)) exit(2);
   if(id && !strcmp(mode,"corrupt")) for(int field=0;field<4;field++) {
    if(toggle(handles[i],callback,users+i,field)!=1) exit(2);
    int rejected=identity(handles[i],callback,users+i)==0;
    if(toggle(handles[i],callback,users+i,field)!=1) exit(2);
    int restored=identity(handles[i],callback,users+i)==id;
    printf("VS_FAULT %d %d %d %d %d\n",stage,i,field,rejected,restored);
    if(!rejected || !restored) exit(2);
   }
  }
 }
 stage++;
}
static PLI_INT32 callback(p_cb_data cb) {
 s_vpi_time now={.type=vpiSimTime};vpi_get_time(NULL,&now);
 printf("CALLBACK %u %u %c\n",now.high,now.low,(char)('A'+(cb->user_data-users)));
 observe();return 0;
}
static PLI_INT32 done(PLI_BYTE8 *unused) {(void)unused;observe();return 0;}
static void setup(void) {
 s_vpi_systf_data task={0};task.type=vpiSysTask;task.tfname="$startup_done";task.calltf=done;vpi_register_systf(&task);
 for(int i=0;i<3;i++) {
  s_vpi_time ignored={.type=vpiSimTime};
  s_cb_data cb={0};cb.reason=cbStartOfSimulation;cb.cb_rtn=callback;cb.time=&ignored;cb.user_data=users+i;
  handles[i]=vpi_register_cb(&cb);if(!handles[i]) exit(2);
 }
 observe();
 if(!vpi_remove_cb(handles[1])) exit(2);
 observe();
}
void (*vlog_startup_routines[])(void)={setup,0};
