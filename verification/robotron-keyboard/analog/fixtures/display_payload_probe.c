#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static PLI_INT32 observe(PLI_BYTE8 *unused) {
 (void)unused;
 void *module=dlopen(getenv("K7658_DISPLAY_MODULE"),RTLD_LAZY|RTLD_NOLOAD);
 if(!module) {fprintf(stderr,"Display module is not loaded\n");exit(2);}
 int (*inventory)(FILE*)=dlsym(module,"robotron_display_inventory");
 int (*toggle)(void)=dlsym(module,"robotron_display_toggle_destination");
 printf("VD_API %d\n",inventory!=NULL);
 const char *mode=getenv("K7658_DISPLAY_PROBE");
 if(!strcmp(mode,"off")) {dlclose(module);return 0;}
 if(!inventory || !toggle || inventory(stdout) || inventory(stdout)) exit(2);
 if(!strcmp(mode,"corrupt")) {
  int changed=toggle();printf("VD_FAULT %d\n",changed);
  if(changed!=0 && changed!=1) exit(2);
  if(changed && (inventory(stdout) || toggle()!=1 || inventory(stdout))) exit(2);
 }
 dlclose(module);return 0;
}
static void setup(void) {
 s_vpi_systf_data d={0};d.type=vpiSysTask;d.tfname="$display_inventory";d.calltf=observe;vpi_register_systf(&d);
}
void (*vlog_startup_routines[])(void)={setup,0};
