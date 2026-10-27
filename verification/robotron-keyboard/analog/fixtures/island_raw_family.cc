#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <typeinfo>
#include <dlfcn.h>
#include <vpi_user.h>
#include "schedule.h"
#include "island_fixture.h"
class ExtraIsland:public vvp_island_tran {
 unsigned runs_=0;
 public:void run_island() override {printf("PRIVATE_RUN %u\n",++runs_);vvp_island_tran::run_island();}
};
class ExtraBranch:public vvp_island_branch_tran {
 bool invert_=true;
 public:ExtraBranch():vvp_island_branch_tran(0,true,0,0,0,false){}
 void drive(vvp_net_t* n,vvp_bit4_t bit){n->fun->recv_vec4(vvp_net_ptr_t(n,0),vvp_vector4_t(1,invert_?~bit:bit),0);}
};
class ExtraPort:public vvp_island_port {
 bool invert_=true;
 public:explicit ExtraPort(vvp_island* i):vvp_island_port(i){}
 void recv_vec4(vvp_net_ptr_t p,const vvp_vector4_t& bits,vvp_context_t c) override {
  auto v=bits;if(invert_)v.set_bit(0,~v.value(0));vvp_island_port::recv_vec4(p,v,c);
 }
};
class Sink:public vvp_net_fun_t {
 const char* label_;
 public:explicit Sink(const char* label):label_(label){}
 void recv_vec8(vvp_net_ptr_t,const vvp_vector8_t& bits) override {printf("VALUE %llu %s %u\n",(unsigned long long)schedule_simtime(),label_,unsigned(bits.value(0).value()));}
};
struct Fixture{vvp_island* island;vvp_island_branch_tran* branch;vvp_net_t* input;vvp_net_t* output;};
static Fixture make(const char* family,const char* label){
 auto island=!strcmp(family,"island")?static_cast<vvp_island*>(new ExtraIsland):new vvp_island_tran;
 auto a=new vvp_net_t;auto b=new vvp_net_t;
 a->fun=!strcmp(family,"port")?static_cast<vvp_net_fun_t*>(new ExtraPort(island)):new vvp_island_port(island);
 b->fun=new vvp_island_port(island);
 island->add_port("a",a);island->add_port("b",b);
 auto branch=!strcmp(family,"branch")?static_cast<vvp_island_branch_tran*>(new ExtraBranch):new vvp_island_branch_tran(0,true,0,0,0,false);
 island->add_branch(branch,"a","b");island->compile_cleanup();
 auto sink=new vvp_net_t;sink->fun=new Sink(label);b->link(vvp_net_ptr_t(sink,0));
 return {island,branch,a,b};
}
static Fixture admitted,foreign;static const char *family,*phase;static bool enabled,allocated;static unsigned step;
static void observe(unsigned stage){
 if(!enabled)return;
 auto api=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_inventory"));if(!api)exit(3);
 char* text=0;size_t size=0;FILE* f=open_memstream(&text,&size);if(!f)exit(3);int result=api(f);if(fclose(f))exit(3);
 if(allocated){if(result!=-1 || size){if(size)fwrite(text,1,size,stdout);exit(3);}printf("RAW_REFUSED %u\n",stage);}
 else {if(result || !size)exit(3);printf("RAW_ADMITTED %u\n%s",stage,text);}
 free(text);
 if(allocated)printf("RAW_TYPES %u %s %s %s\n",stage,typeid(*foreign.island).name(),typeid(*foreign.branch).name(),typeid(*foreign.input->fun).name());
}
static void allocate(){foreign=make(family,"foreign");allocated=true;}
static PLI_INT32 startup(p_cb_data){
 family=getenv("K7658_ISLAND_FAMILY");phase=getenv("K7658_ISLAND_PHASE");const char* mode=getenv("K7658_ISLAND_MODE");if(!family || !phase || !mode)exit(3);
 enabled=!strcmp(mode,"observe");admitted=make("exact","admitted");if(!strcmp(phase,"early"))allocate();
 printf("RAW_FAMILY %s %s\n",family,phase);observe(0);return 0;
}
static PLI_INT32 drive(PLI_BYTE8*){
 ++step;if(!allocated)allocate();observe(step);auto bit=step==1?BIT4_0:BIT4_1;
 admitted.output->fun->recv_vec4(vvp_net_ptr_t(admitted.output,0),vvp_vector4_t(1,BIT4_Z),0);
 foreign.output->fun->recv_vec4(vvp_net_ptr_t(foreign.output,0),vvp_vector4_t(1,BIT4_Z),0);
 admitted.input->fun->recv_vec4(vvp_net_ptr_t(admitted.input,0),vvp_vector4_t(1,bit),0);
 if(!strcmp(family,"branch"))static_cast<ExtraBranch*>(foreign.branch)->drive(foreign.input,bit);
 else foreign.input->fun->recv_vec4(vvp_net_ptr_t(foreign.input,0),vvp_vector4_t(1,bit),0);
 return 0;
}
static PLI_INT32 settle(PLI_BYTE8*){observe(step+2);return 0;}
static void setup(){
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(3);
 s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$family_drive";t.calltf=drive;vpi_register_systf(&t);t.tfname="$family_settle";t.calltf=settle;vpi_register_systf(&t);
}
extern "C" {void(*vlog_startup_routines[])(void)={setup,0};}
