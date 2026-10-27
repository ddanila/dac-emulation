#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static unsigned stage;
static int (*delta)(FILE*);
static int (*reference)(FILE*);
static int reference_ready;
static char *snapshot(int (*inventory)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;
 if(r){free(p);return NULL;}
 if(!reference_ready) {
  FILE* rejected=tmpfile();if(!rejected)exit(2);
  if(delta(rejected)!=-1 || ftell(rejected)!=0)exit(2);
  if(reference(stdout))exit(2);
  if(reference(rejected)!=-1 || ftell(rejected)!=0 || fclose(rejected))exit(2);
  reference_ready=1;
 }
 if(delta(stdout))exit(2);
 return p;
}
static PLI_INT32 observe(PLI_BYTE8 *unused) {
 (void)unused;
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_wire_inventory");
 int (*toggle)(int,int)=dlsym(RTLD_DEFAULT,"robotron_vvp_wire_toggle");
 const char *mode=getenv("K7658_WIRE_PROBE");
 printf("WFM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  reference=dlsym(RTLD_DEFAULT,"robotron_vvp_wire_reference");
  delta=dlsym(RTLD_DEFAULT,"robotron_vvp_wire_delta_inventory");
  if(!inventory || !toggle || !reference || !delta)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("WFM_BEFORE\n%sWFM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt"))for(int kind=4;kind<=8;kind+=4)for(int field=0;field<(kind==4?6:7);field++) {
   int found=toggle(kind,field);if(found!=0 && found!=1)exit(2);
   if(!found)continue;
   char *changed=snapshot(inventory);
   if(toggle(kind,field)!=1)exit(3);
   char *after=snapshot(inventory);
   int detected=changed && strcmp(before,changed)!=0;
   int restored=after && !strcmp(before,after);
   printf("WFM_CHANGED %d %d\n%sWFM_RESTORED\n%sWFM_FAULT %d %d %d %d\n",kind,field,changed?changed:"",after?after:"",kind,field,detected,restored);
   free(changed);free(after);if(!detected || !restored)exit(2);
  }
  free(before);
 }
 printf("WFM_DONE %u\n",stage++);return 0;
}
static void setup(void) {
 s_vpi_systf_data task={0};task.type=vpiSysTask;task.tfname="$wire_observe";task.calltf=observe;vpi_register_systf(&task);
}
void (*vlog_startup_routines[])(void)={setup,0};
