#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vector>
#include <string>
#include <vpi_user.h>
#include "schedule.h"
#include "concat.h"
static unsigned stage,phase;
static char* snapshot(int (*inventory)(FILE*)) {
 char *p=0;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;if(r){free(p);return 0;}return p;
}
static void observe(bool callback) {
 auto inventory=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_concat_inventory"));
 auto toggle=reinterpret_cast<int (*)(unsigned long long,int)>(dlsym(RTLD_DEFAULT,"robotron_vvp_concat_toggle"));
 const char *mode=getenv("K7658_CONCAT_PROBE");
 printf("CNM_API %u %d %d\n",stage,inventory!=0,callback);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("CNM_BEFORE\n%sCNM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt") && !callback) {
   std::string text(before);size_t pos=0;
   while((pos=text.find("VCN_NODE ",pos))!=std::string::npos){
    unsigned long long id;if(sscanf(text.c_str()+pos,"VCN_NODE %llu",&id)!=1)exit(2);pos++;
    for(int field=0;field<7;field++) {
     int found=toggle(id,field);if(found!=0 && found!=1)exit(2);if(!found)continue;
     char *changed=snapshot(inventory);if(toggle(id,field)!=1)exit(3);
     char *after=snapshot(inventory);
     if(!changed || !after || !strcmp(before,changed) || strcmp(before,after))exit(2);
     printf("CNM_CHANGED %llu %d\n%sCNM_RESTORED\n%sCNM_FAULT %llu %d 1 1\n",id,field,changed,after,id,field);
     free(changed);free(after);
    }
   }
  }
  free(before);
 }
 printf("CNM_DONE %u\n",stage++);
}

static vvp_net_t* nodes[2];
class Sink: public vvp_net_fun_t {
 unsigned index;
 public:
 explicit Sink(unsigned i):index(i){}
 void recv_vec4(vvp_net_ptr_t,const vvp_vector4_t& bits,vvp_context_t) override {
  printf("CONCAT_VALUE %llu %u ",(unsigned long long)schedule_simtime(),index);
  for(unsigned i=0;i<bits.size();i++)printf("%u",unsigned(bits.value(i)));puts("");observe(true);
 }
 void recv_vec8(vvp_net_ptr_t,const vvp_vector8_t& bits) override {
  printf("CONCAT_VALUE %llu %u ",(unsigned long long)schedule_simtime(),index);
  for(unsigned i=0;i<bits.size();i++){auto bit=bits.value(i);unsigned char byte;memcpy(&byte,&bit,1);printf("%02x",byte);}puts("");observe(true);
 }
};
static PLI_INT32 startup(p_cb_data) {
 for(unsigned i=0;i<2;i++){
  nodes[i]=new vvp_net_t;
  if(i==0)nodes[i]->fun=new vvp_fun_concat(1,8,9,80);
  else nodes[i]->fun=new vvp_fun_concat8(1,8,9,80);
  auto sink=new vvp_net_t;sink->fun=new Sink(i);nodes[i]->link(vvp_net_ptr_t(sink,0));
 }
 observe(false);return 0;
}
static PLI_INT32 step(PLI_BYTE8*) {
 ++phase;
 for(unsigned i=0;i<2;i++){
  auto fun=nodes[i]->fun;
  unsigned port=phase<=4?phase-1:3;
  auto p=vvp_net_ptr_t(nodes[i],port);
  unsigned widths[]={1,8,9,80};
  if(phase<=4){vvp_bit4_t values[]={BIT4_1,BIT4_0,BIT4_X,BIT4_Z};fun->recv_vec4(p,vvp_vector4_t(widths[port],values[port]),0);}
  if(phase==5 || phase==6)fun->recv_vec4_pv(p,vvp_vector4_t(1,BIT4_1),79,80,0);
  if(phase==7 && i==1){vvp_vector8_t bits(1);bits.set_bit(0,vvp_scalar_t(BIT4_1,1,0));fun->recv_vec8_pv(p,bits,0,80);}
  if(phase==8 && i==1){vvp_vector8_t bits(1);fun->recv_vec8_pv(p,bits,0,80);}
 }
 observe(false);return 0;
}
static void setup() {
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(2);
 s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$concat_step";task.calltf=step;vpi_register_systf(&task);
}
extern "C" { void (*vlog_startup_routines[])(void)={setup,0}; }
