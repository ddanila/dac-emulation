#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static unsigned stage;
static char *snapshot(int (*api)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=api(f);if(fclose(f)||r)exit(2);return p;
}
static void observe(int callback) {
 int (*raw)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_inventory");
 int (*legacy)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_island_inventory");
 int (*toggle)(int,int)=dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_toggle");
 const char* mode=getenv("K7658_ISLAND_RAW_PROBE");
 printf("IRM_STAGE %u %d %d\n",stage,callback,raw!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!raw || !legacy || !toggle)exit(2);
  char *before=snapshot(raw),*old=snapshot(legacy),*repeat=snapshot(raw);
  if(strcmp(before,repeat))exit(2);
  printf("IRM_BEFORE\n%s%sIRM_REPEAT\n%s",before,old,repeat);free(repeat);
  if(!strcmp(mode,"corrupt"))for(int field=0;field<3;field++)for(int op=0;op<3;op++){
   int result=toggle(field,op);if(result!=0 && result!=1)exit(2);if(!result)continue;
   char *changed=snapshot(raw),*changed_old=snapshot(legacy);
   if(toggle(field,op)!=1)exit(3);
   char *restored=snapshot(raw),*restored_old=snapshot(legacy);
   if(!strcmp(before,changed)||strcmp(before,restored)||strcmp(old,restored_old))exit(2);
   if(op==1 && strcmp(old,changed_old))exit(2);
   printf("IRM_CHANGED %d %d\n%s%sIRM_RESTORED\n%sIRM_FAULT %d %d 1 1\n",field,op,changed,changed_old,restored,field,op);
   free(changed);free(changed_old);free(restored);free(restored_old);
  }
  free(before);free(old);
 }
 printf("IRM_DONE %u\n",stage++);
}
static PLI_INT32 task(PLI_BYTE8 *unused){(void)unused;observe(0);return 0;}
static PLI_INT32 changed(p_cb_data unused){(void)unused;observe(1);return 0;}
static PLI_INT32 start(p_cb_data unused){
 (void)unused;
 const char* names[]={"probe.a","probe.b"};
 for(unsigned i=0;i<2;i++){
  vpiHandle net=vpi_handle_by_name((PLI_BYTE8*)names[i],NULL);if(!net)exit(2);
  s_vpi_time time={0};time.type=vpiSuppressTime;
  s_vpi_value value={0};value.format=vpiSuppressVal;
  s_cb_data cb={0};cb.reason=cbValueChange;cb.cb_rtn=changed;cb.obj=net;cb.time=&time;cb.value=&value;
  if(!vpi_register_cb(&cb))exit(2);
 }
 return 0;
}
static void setup(void){
 s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname="$island_observe";t.calltf=task;vpi_register_systf(&t);
 s_cb_data cb={0};cb.reason=cbStartOfSimulation;cb.cb_rtn=start;if(!vpi_register_cb(&cb))exit(2);
}
void (*vlog_startup_routines[])(void)={setup,0};
