#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static PLI_INT32 observe(PLI_BYTE8 *unused) {
 (void)unused;const char *mode=getenv("K7658_SIGNAL_MODE");
 if(!mode)exit(2);if(!strcmp(mode,"off"))return 0;
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_signal_inventory");
 int (*types)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_net_types");
 if(!inventory || !types)exit(2);
 const char *family=getenv("K7658_SIGNAL_FAMILY");if(!family)exit(2);
 char name[128];if(snprintf(name,sizeof(name),"%s.types",family)>=(int)sizeof(name))exit(2);
 FILE *f=fopen(name,"w");if(!f || types(f) || fclose(f))exit(2);
 char *text=NULL;size_t size=0;f=open_memstream(&text,&size);if(!f)exit(2);
 int result=inventory(f);if(fclose(f))exit(2);
 if(result!=-1 || size){free(text);exit(3);}
 free(text);printf("SIGNAL_REFUSED\n");exit(2);
}
static void setup(void) {
 s_vpi_systf_data task={0};task.type=vpiSysTask;task.tfname="$family_observe";task.calltf=observe;vpi_register_systf(&task);
}
void (*vlog_startup_routines[])(void)={setup,0};
