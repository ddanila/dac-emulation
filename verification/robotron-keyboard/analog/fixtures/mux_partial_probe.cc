#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
#include "logic.h"
static unsigned stage;
static char *snapshot(int (*inventory)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;
 if(r){free(p);return NULL;}return p;
}
static PLI_INT32 observe(PLI_BYTE8 *unused) {
 (void)unused;
 int (*inventory)(FILE*)=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_mux_inventory"));
 int (*toggle)(int)=reinterpret_cast<int (*)(int)>(dlsym(RTLD_DEFAULT,"robotron_vvp_mux_toggle"));
 const char *mode=getenv("K7658_MUX_PROBE");
 printf("MXM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("MXM_BEFORE\n%sMXM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt"))for(int field=0;field<5;field++) {
   int found=toggle(field);if(found!=0 && found!=1)exit(2);
   if(!found)continue;
   char *changed=snapshot(inventory);
   if(toggle(field)!=1)exit(3);
   char *after=snapshot(inventory);
   int detected=changed && strcmp(before,changed)!=0;
   int restored=after && !strcmp(before,after);
   printf("MXM_CHANGED %d\n%sMXM_RESTORED\n%sMXM_FAULT %d %d %d\n",field,changed?changed:"",after?after:"",field,detected,restored);
   free(changed);free(after);if(!detected || !restored)exit(2);
  }
  free(before);
 }
 printf("MXM_DONE %u\n",stage++);return 0;
}

// Call the public native entry point explicitly: HDL slices need not use it.
static vvp_net_t *node;
static vvp_fun_muxz *mux;
static unsigned phase;
class Sink : public vvp_net_fun_t {
 public:
 void recv_vec4(vvp_net_ptr_t, const vvp_vector4_t& value, vvp_context_t) override {
  printf("PARTIAL_VALUE %llu ",(unsigned long long)schedule_simtime());
  for(unsigned i=0;i<value.size();i++)printf("%u",unsigned(value.value(i)));
  printf("\n");observe(NULL);
 }
};
static vvp_vector4_t vector(const char *bits) {
 vvp_vector4_t result(strlen(bits));
 for(unsigned i=0;i<strlen(bits);i++)result.set_bit(i,static_cast<vvp_bit4_t>(bits[i]-'0'));
 return result;
}
static void partial(unsigned port,unsigned base,const char *bits) {
 printf("PARTIAL_CALL %u %u %u %s\n",phase,port,base,bits);
 mux->recv_vec4_pv(vvp_net_ptr_t(node,port),vector(bits),base,port==2?1:80,0);
}
static PLI_INT32 step(PLI_BYTE8*) {
 ++phase;
 switch(phase) {
 case 1:
  mux->recv_vec4(vvp_net_ptr_t(node,0),vvp_vector4_t(80,BIT4_0),0);
  mux->recv_vec4(vvp_net_ptr_t(node,1),vvp_vector4_t(80,BIT4_1),0);
  partial(2,0,"0");break;
 case 2:partial(1,70,"2301");break;
 case 3:partial(2,0,"1");break;
 case 4:partial(0,0,"1010");break;
 case 5:partial(2,0,"3");break;
 case 6:partial(1,0,"1010");break;
 case 7:partial(2,0,"2");break;
 case 8:partial(0,70,"2301");break;
 case 9:partial(2,0,"0");break;
 case 10:partial(0,70,"2301");break;
 default:exit(2);
 }
 return observe(NULL);
}
static PLI_INT32 startup(p_cb_data) {
 node=new vvp_net_t; mux=new vvp_fun_muxz(80);node->fun=mux;
 vvp_net_t *sink=new vvp_net_t;sink->fun=new Sink;
 node->link(vvp_net_ptr_t(sink,0));return observe(NULL);
}
static void setup() {
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;
 if(!vpi_register_cb(&cb))exit(2);
 s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$mux_partial_step";task.calltf=step;vpi_register_systf(&task);
 task.tfname="$mux_partial_observe";task.calltf=observe;vpi_register_systf(&task);
}
extern "C" { void (*vlog_startup_routines[])(void)={setup,0}; }
