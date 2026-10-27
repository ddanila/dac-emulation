#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <string>
#include <vector>
#include <vpi_user.h>
#include "schedule.h"
#include "resolv.h"
static unsigned phase,stage;
static char* snapshot(int(*api)(FILE*)){char* p=0;size_t size=0;FILE* f=open_memstream(&p,&size);if(!f)exit(2);int r=api(f);if(fclose(f)||r)exit(2);return p;}
static void observe(bool callback){
 auto api=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_resolver_inventory"));
 auto fault=reinterpret_cast<int(*)(unsigned long long,int,unsigned)>(dlsym(RTLD_DEFAULT,"robotron_vvp_resolver_toggle"));
 const char* mode=getenv("K7658_RESOLVER_PROBE");printf("RSM_API %u %d %d\n",stage,api!=0,callback);
 if(mode && strcmp(mode,"off")){
  if(!api || !fault)exit(2);char* before=snapshot(api);char* repeat=snapshot(api);
  if(strcmp(before,repeat))exit(2);printf("RSM_BEFORE\n%sRSM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt") && !callback){
   std::string text(before);size_t pos=0;
   while((pos=text.find("VRS_NODE ",pos))!=std::string::npos){
    unsigned long long id;unsigned kind,slots=0;
    if(sscanf(text.c_str()+pos,"VRS_NODE %llu %*s %*s %u",&id,&kind)!=2)exit(2);
    if(kind==1 && sscanf(text.c_str()+pos,"VRS_NODE %*llu %*s %*s %*u %*u %*s %*s %*s %u",&slots)!=1)exit(2);pos++;
    for(int field=0;field<(kind==1?7:2);field++)for(unsigned index=0;index<((kind==1 && (field==0 || field==1 || field==6))?slots:1);index++){
     int result=fault(id,field,index);if(result!=0 && result!=1)exit(2);if(!result)continue;
     char* changed=snapshot(api);if(fault(id,field,index)!=1)exit(3);char* after=snapshot(api);
     if(!strcmp(before,changed)||strcmp(before,after))exit(2);
     printf("RSM_CHANGED %llu %d %u\n%sRSM_RESTORED\n%sRSM_FAULT %llu %d %u 1 1\n",id,field,index,changed,after,id,field,index);
     free(changed);free(after);
    }
   }
  }
  free(before);
 }
 printf("RSM_DONE %u\n",stage++);
}
static const unsigned ports[]={1,1,1,2,5,17};static vvp_net_t* cores[6];static std::vector<vvp_net_t*> routes[6];
class Sink:public vvp_net_fun_t {
 unsigned index;
 public:explicit Sink(unsigned i):index(i){}
 void recv_vec8(vvp_net_ptr_t,const vvp_vector8_t& bits) override {
  printf("RES_VALUE %u %u ",phase,index);
  for(unsigned i=0;i<bits.size();i++){auto b=bits.value(i);unsigned char raw;memcpy(&raw,&b,1);printf("%02x",raw);}puts("");observe(true);
 }
};
static PLI_INT32 startup(p_cb_data){
 for(unsigned i=0;i<6;i++){
  auto n=new vvp_net_t;cores[i]=n;auto core=new resolv_tri(ports[i],n,i%3==0?vvp_scalar_t():vvp_scalar_t(i%3==1?BIT4_0:BIT4_1,5,5));n->fun=core;routes[i].push_back(n);
  auto sink=new vvp_net_t;sink->fun=new Sink(i);n->link(vvp_net_ptr_t(sink,0));
  for(unsigned base=4;base<ports[i];base+=4){auto ext=new vvp_net_t;ext->fun=new resolv_extend(core,base);routes[i].push_back(ext);}
 }
 observe(false);return 0;
}
static PLI_INT32 drive(PLI_BYTE8*){
 ++phase;
 for(unsigned core=0;core<6;core++)for(unsigned port=0;port<ports[core];port++){
  printf("RES_DRIVE %u %u %u\n",phase,core,port);auto n=routes[core][port/4];auto p=vvp_net_ptr_t(n,port%4);
  static const unsigned char raw[]={0x33,0xbb,0x55,0xdd,0x66,0xee,0x77,0xff,0x88,0x00,0x88,0x88};
  if(phase==1)n->fun->recv_vec4_pv(p,vvp_vector4_t(3,BIT4_0),PROBE_WIDTH-1,PROBE_WIDTH,0);
  else {
   vvp_vector8_t value(PROBE_WIDTH);vvp_scalar_t bit;memcpy(&bit,&raw[phase-2],1);
   for(unsigned i=0;i<PROBE_WIDTH;i++)value.set_bit(i,bit);
   n->fun->recv_vec8(p,value);
  }
 }
 observe(false);return 0;
}
static void setup(){s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(2);s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$resolver_drive";task.calltf=drive;vpi_register_systf(&task);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
