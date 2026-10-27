#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vector>
#include <string>
#include <vpi_user.h>
#include "reduction_fixture.h"
#include "schedule.h"
static unsigned stage,phase;
static char* snapshot(int (*inventory)(FILE*)) {
 char *p=0;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;if(r){free(p);return 0;}
 static int ready;
 int (*reference)(FILE*)=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_reduction_reference"));
 int (*delta)(FILE*)=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_reduction_delta_inventory"));
 if(!reference || !delta)exit(2);
 if(!ready) {
  FILE* rejected=tmpfile();if(!rejected)exit(2);
  if(delta(rejected)!=-1 || ftell(rejected)!=0)exit(2);
  if(reference(stdout))exit(2);
  if(reference(rejected)!=-1 || ftell(rejected)!=0 || fclose(rejected))exit(2);
  ready=1;
 }
 if(delta(stdout))exit(2);
 return p;
}
static void observe(bool callback) {
 auto inventory=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_reduction_inventory"));
 auto toggle=reinterpret_cast<int (*)(unsigned long long,int)>(dlsym(RTLD_DEFAULT,"robotron_vvp_reduction_toggle"));
 const char *mode=getenv("K7658_REDUCTION_PROBE");
 printf("RDM_API %u %d %d\n",stage,inventory!=0,callback);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("RDM_BEFORE\n%sRDM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt") && !callback) {
   std::string text(before);size_t pos=0;
   while((pos=text.find("VRD_NODE ",pos))!=std::string::npos){
    unsigned long long id;if(sscanf(text.c_str()+pos,"VRD_NODE %llu",&id)!=1)exit(2);pos++;
    for(int field=0;field<2;field++) {
     int found=toggle(id,field);if(found!=0 && found!=1)exit(2);if(!found)continue;
     char *changed=snapshot(inventory);if(toggle(id,field)!=1)exit(3);
     char *after=snapshot(inventory);
     if(!changed || !after || !strcmp(before,changed) || strcmp(before,after))exit(2);
     printf("RDM_CHANGED %llu %d\n%sRDM_RESTORED\n%sRDM_FAULT %llu %d 1 1\n",id,field,changed,after,id,field);
     free(changed);free(after);
    }
   }
  }
  free(before);
 }
 printf("RDM_DONE %u\n",stage++);
}
static vvp_net_t* nodes[6];
class Sink: public vvp_net_fun_t {
 unsigned index;
 public:
 explicit Sink(unsigned i):index(i){}
 void recv_vec4(vvp_net_ptr_t,const vvp_vector4_t& bits,vvp_context_t) override {
  printf("REDUCTION_VALUE %llu %u %u\n",(unsigned long long)schedule_simtime(),index,unsigned(bits.value(0)));
 }
};
static PLI_INT32 startup(p_cb_data) {
 for(unsigned i=0;i<6;i++){
  nodes[i]=new vvp_net_t;
  if(i==0)nodes[i]->fun=new vvp_reduce_and;
  if(i==1)nodes[i]->fun=new vvp_reduce_or;
  if(i==2)nodes[i]->fun=new vvp_reduce_xor;
  if(i==3)nodes[i]->fun=new vvp_reduce_nand;
  if(i==4)nodes[i]->fun=new vvp_reduce_nor;
  if(i==5)nodes[i]->fun=new vvp_reduce_xnor;
  auto sink=new vvp_net_t;sink->fun=new Sink(i);nodes[i]->link(vvp_net_ptr_t(sink,0));
 }
 observe(false);return 0;
}
static PLI_INT32 step(PLI_BYTE8*) {
 ++phase;
 for(unsigned i=0;i<6;i++){
  auto p=vvp_net_ptr_t(nodes[i],0);auto fun=nodes[i]->fun;
  if(phase==1)fun->recv_vec4_pv(p,vvp_vector4_t(2,BIT4_0),70,80,0);
  if(phase==2)fun->recv_vec4(p,vvp_vector4_t(80,BIT4_0),0);
  if(phase==3)fun->recv_vec4_pv(p,vvp_vector4_t(1,BIT4_1),71,80,0);
  if(phase==4 || phase==5)fun->recv_vec4_pv(p,vvp_vector4_t(1,BIT4_Z),71,80,0);
  if(phase==6)fun->recv_vec4(p,vvp_vector4_t(80,BIT4_1),0);
  if(phase==7){vvp_vector4_t bits(2,BIT4_0);bits.set_bit(0,BIT4_X);fun->recv_vec4_pv(p,bits,0,80,0);}
  if(phase==8)fun->recv_vec4(p,vvp_vector4_t(3,BIT4_1),0);
  if(phase==9)fun->recv_vec4_pv(p,vvp_vector4_t(1,BIT4_0),2,3,0);
  if(phase==10)fun->recv_vec4(p,vvp_vector4_t(0),0);
  if(phase==11)fun->recv_vec4_pv(p,vvp_vector4_t(1,BIT4_1),79,80,0);
 }
 observe(false);return 0;
}
static void setup() {
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(2);
 s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$reduction_step";task.calltf=step;vpi_register_systf(&task);
}
extern "C" { void (*vlog_startup_routines[])(void)={setup,0}; }
