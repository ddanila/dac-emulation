#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vector>
#include <string>
#include <vpi_user.h>
#include "arith.h"
#include "schedule.h"
static unsigned stage,phase;
static const unsigned width=ARITHMETIC_WIDTH;
static char* snapshot(int (*inventory)(FILE*)) {
 char *p=0;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;if(r){free(p);return 0;}
 static int ready;
 int (*reference)(FILE*)=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_arithmetic_reference"));
 int (*delta)(FILE*)=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_arithmetic_delta_inventory"));
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
 auto inventory=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_arithmetic_inventory"));
 auto toggle=reinterpret_cast<int (*)(unsigned long long,int)>(dlsym(RTLD_DEFAULT,"robotron_vvp_arithmetic_toggle"));
 const char *mode=getenv("K7658_ARITHMETIC_PROBE");
 printf("ARM_API %u %d %d\n",stage,inventory!=0,callback);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("ARM_BEFORE\n%sARM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt") && !callback) {
   std::string text(before);size_t pos=0;
   while((pos=text.find("VAR_NODE ",pos))!=std::string::npos){
    unsigned long long id;if(sscanf(text.c_str()+pos,"VAR_NODE %llu",&id)!=1)exit(2);pos++;
    for(int field=0;field<4;field++) {
     int found=toggle(id,field);if(found!=0 && found!=1)exit(2);if(!found)continue;
     char *changed=snapshot(inventory);if(toggle(id,field)!=1)exit(3);
     char *after=snapshot(inventory);
     if(!changed || !after || !strcmp(before,changed) || strcmp(before,after))exit(2);
     printf("ARM_CHANGED %llu %d\n%sARM_RESTORED\n%sARM_FAULT %llu %d 1 1\n",id,field,changed,after,id,field);
     free(changed);free(after);
    }
   }
  }
  free(before);
 }
 printf("ARM_DONE %u\n",stage++);
}
static vvp_net_t *nodes[5];
class Sink: public vvp_net_fun_t {
 unsigned index;
 public:
 explicit Sink(unsigned n):index(n){}
 void recv_vec4(vvp_net_ptr_t,const vvp_vector4_t& value,vvp_context_t) override {
  printf("ARITHMETIC_VALUE %llu %u ",(unsigned long long)schedule_simtime(),index);
  for(unsigned i=0;i<value.size();i++)printf("%u",unsigned(value.value(i)));
  printf("\n");
 }
};
static PLI_INT32 startup(p_cb_data) {
 for(unsigned i=0;i<5;i++){
  nodes[i]=new vvp_net_t;
  if(i==0)nodes[i]->fun=new vvp_arith_sum(width);
  else if(i==1)nodes[i]->fun=new vvp_arith_sub(width);
  else if(i==2)nodes[i]->fun=new vvp_cmp_eq(width);
  else if(i==3)nodes[i]->fun=new vvp_cmp_eeq(width);
  else nodes[i]->fun=new vvp_cmp_nee(width);
  auto sink=new vvp_net_t;sink->fun=new Sink(i);nodes[i]->link(vvp_net_ptr_t(sink,0));
 }
 observe(false);return 0;
}
static PLI_INT32 step(PLI_BYTE8*) {
 ++phase;
 unsigned port=(phase==2 || phase==5 || phase==7 || phase==9 || phase==10)?1:0;
 vvp_vector4_t bits(width,phase==3?BIT4_1:BIT4_0);
 if(phase==2 || phase==8)bits.set_bit(0,BIT4_1);
 if(phase==7 || phase==9)bits.set_bit(width-1,BIT4_X);
 for(unsigned i=0;i<5;i++) {
  if(phase==4 || phase==5){
   vvp_vector4_t part(width>1?2:1);part.set_bit(0,width>1?BIT4_Z:BIT4_X);if(width>1)part.set_bit(1,BIT4_X);
   nodes[i]->fun->recv_vec4_pv(vvp_net_ptr_t(nodes[i],port),part,width>1?width-2:0,width,0);
  }else nodes[i]->fun->recv_vec4(vvp_net_ptr_t(nodes[i],port),bits,0);
 }
 observe(false);return 0;
}
static void setup() {
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(2);
 s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$arithmetic_step";task.calltf=step;vpi_register_systf(&task);
}
extern "C" { void (*vlog_startup_routines[])(void)={setup,0}; }
