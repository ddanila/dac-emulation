#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static unsigned stage;
static char *snapshot(int (*inventory)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;if(r){free(p);return NULL;}return p;
}
static void observe(void) {
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_primitive_inventory");
 int (*toggle)(int,int)=dlsym(RTLD_DEFAULT,"robotron_vvp_primitive_toggle");
 const char *mode=getenv("K7658_PRIMITIVE_PROBE");
 printf("VPM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("VPM_BEFORE\n%sVPM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt")) for(int kind=1;kind<=2;kind++) for(int field=0;field<(kind==1?2:3);field++) {
   int present=toggle(kind,field);if(present!=0 && present!=1)exit(2);
   if(present) {
    char *changed=snapshot(inventory);
    if(toggle(kind,field)!=1)exit(3);
    char *after=snapshot(inventory);
    int detected=changed && strcmp(before,changed)!=0;
    int restored=after && !strcmp(before,after);
    printf("VPM_CHANGED %d %d\n%sVPM_RESTORED\n%s",kind,field,changed?changed:"",after?after:"");
    printf("VPM_FAULT %d %d %d %d\n",kind,field,detected,restored);
    free(changed);free(after);if(!detected || !restored)exit(2);
   }
  }
  free(before);
 }
 printf("VPM_DONE %u\n",stage++);
}
static PLI_INT32 task(PLI_BYTE8 *unused) {(void)unused;observe();return 0;}
static PLI_INT32 drive(PLI_BYTE8 *unused) {
 (void)unused;static int which;
 s_vpi_vecval first[3]={{0x3210fedc,0},{0xba987654,0},{0xfedc,0}};
 s_vpi_vecval second[3]={{0xcdef0123,0},{0x456789ab,0},{0x123,0}};
 vpiHandle target=vpi_handle_by_name("probe.wide",NULL);if(!target)exit(2);
 s_vpi_value value={.format=vpiVectorVal};value.value.vector=which++ ? second:first;
 vpi_put_value(target,&value,NULL,vpiNoDelay);observe();return 0;
}
static void setup(void){
 s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname="$primitive_observe";t.calltf=task;vpi_register_systf(&t);
 t.tfname="$primitive_drive";t.calltf=drive;vpi_register_systf(&t);
}
void (*vlog_startup_routines[])(void)={setup,0};
