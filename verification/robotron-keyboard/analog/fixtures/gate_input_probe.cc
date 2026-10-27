#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vector>
#include <limits>
#include <string>
#include <vpi_user.h>
#include "logic.h"
static unsigned stage,phase;
static char* snapshot(int (*inventory)(FILE*)) {
 char *p=0;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;if(r){free(p);return 0;}return p;
}
static void observe(bool callback) {
 auto inventory=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_gate_inventory"));
 auto toggle=reinterpret_cast<int (*)(unsigned long long,int)>(dlsym(RTLD_DEFAULT,"robotron_vvp_gate_toggle"));
 const char *mode=getenv("K7658_GATE_PROBE");
 printf("GGM_API %u %d %d\n",stage,inventory!=0,callback);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("GGM_BEFORE\n%sGGM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt") && !callback) {
   std::string text(before);size_t pos=0;
   while((pos=text.find("VGL_GATE ",pos))!=std::string::npos){
    unsigned long long id;if(sscanf(text.c_str()+pos,"VGL_GATE %llu",&id)!=1)exit(2);pos++;
    for(int field=0;field<6;field++) {
     int found=toggle(id,field);if(found!=0 && found!=1)exit(2);if(!found)continue;
     char *changed=snapshot(inventory);if(toggle(id,field)!=1)exit(3);
     char *after=snapshot(inventory);
     if(!changed || !after || !strcmp(before,changed) || strcmp(before,after))exit(2);
     printf("GGM_CHANGED %llu %d\n%sGGM_RESTORED\n%sGGM_FAULT %llu %d 1 1\n",id,field,changed,after,id,field);
     free(changed);free(after);
    }
   }
  }
  free(before);
 }
 printf("GGM_DONE %u\n",stage++);
}
static vvp_net_t *nodes[8];
class Sink: public vvp_net_fun_t {
 unsigned index;
 public:
 explicit Sink(unsigned n):index(n){}
 void recv_vec4(vvp_net_ptr_t,const vvp_vector4_t& value,vvp_context_t) override {
  printf("GATE_VALUE %llu %u ",(unsigned long long)schedule_simtime(),index);
  for(unsigned i=0;i<value.size();i++)printf("%u",unsigned(value.value(i)));
  printf("\n");observe(true);
 }
};
static PLI_INT32 startup(p_cb_data) {
 for(unsigned i=0;i<8;i++){
  nodes[i]=new vvp_net_t;
  if(i<2)nodes[i]->fun=new vvp_fun_and(80,i%2);
  else if(i<4)nodes[i]->fun=new vvp_fun_or(80,i%2);
  else if(i<6)nodes[i]->fun=new vvp_fun_xor(80,i%2);
  else if(i==6)nodes[i]->fun=new vvp_fun_buf(80);
  else nodes[i]->fun=new vvp_fun_not(80);
  auto sink=new vvp_net_t;sink->fun=new Sink(i);nodes[i]->link(vvp_net_ptr_t(sink,0));
 }
 observe(false);return 0;
}
static PLI_INT32 step(PLI_BYTE8*) {
 ++phase;
 for(unsigned i=0;i<8;i++) {
  unsigned count=i<6?4:1;
  if(phase==1 || phase==2) {
   const double values[]={2.5,-1.5,0.49,-0.5};
   for(unsigned port=0;port<count;port++)nodes[i]->fun->recv_real(vvp_net_ptr_t(nodes[i],port),phase==1?values[port]:0.0,0);
  }else if(phase==3 || phase==4 || phase==6){
   if(i<6) {
    for(unsigned port=0;port<4;port++){
     unsigned width=port==1?1:80;
     vvp_bit4_t bit=i<2?BIT4_1:i<4?BIT4_0:port==1?BIT4_1:BIT4_0;
     if(phase==6 && port==0 && i<4)bit=i<2?BIT4_0:BIT4_1;
     nodes[i]->fun->recv_vec4(vvp_net_ptr_t(nodes[i],port),vvp_vector4_t(width,bit),0);
    }
   }else{
    vvp_vector4_t bits(3);bits.set_bit(0,BIT4_Z);bits.set_bit(1,BIT4_0);bits.set_bit(2,BIT4_X);
    nodes[i]->fun->recv_vec4(vvp_net_ptr_t(nodes[i],0),bits,0);
   }
  }else if(phase==7 || phase==8){
   for(unsigned port=0;port<count;port++)nodes[i]->fun->recv_real(vvp_net_ptr_t(nodes[i],port),phase==7?std::numeric_limits<double>::quiet_NaN():(port%2?-std::numeric_limits<double>::infinity():std::numeric_limits<double>::infinity()),0);
  }else if(phase==5 || phase==9){
   for(unsigned port=0;port<count;port++)nodes[i]->fun->recv_vec4(vvp_net_ptr_t(nodes[i],port),vvp_vector4_t(80,BIT4_X),0);
  }
 }
 observe(false);return 0;
}

static void setup() {
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(2);
 s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$gate_step";task.calltf=step;vpi_register_systf(&task);
}
extern "C" { void (*vlog_startup_routines[])(void)={setup,0}; }
