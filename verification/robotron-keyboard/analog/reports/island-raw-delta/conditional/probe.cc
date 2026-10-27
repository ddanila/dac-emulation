#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static unsigned stage;
static char *snapshot(int (*api)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=api(f);auto raw=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_inventory");if(api==raw){auto delta=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_delta_inventory");if(!delta || delta(f))exit(2);}if(fclose(f)||r)exit(2);return p;
}
#include "schedule.h"
#include "island_fixture.h"
struct Fixture {vvp_net_t *a,*b,*e;unsigned width;};
static Fixture fixtures[8];static unsigned phase,population;
static void observe(int callback) {
 auto raw=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_inventory");
 auto legacy=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_island_inventory");
 const char* mode=getenv("K7658_ISLAND_RAW_PROBE");
 printf("IRM_STAGE %u %d %d\n",stage,callback,raw!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!raw || !legacy)exit(2);
  static bool referenced=false;if(!referenced){auto ref=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_island_raw_reference");if(!ref || ref(stdout))exit(2);referenced=true;}
  char *before=snapshot(raw),*old=snapshot(legacy),*repeat=snapshot(raw);
  if(strcmp(before,repeat))exit(2);
  printf("IRM_BEFORE\n%s%sIRM_REPEAT\n%s",before,old,repeat);free(repeat);
  if(!strcmp(mode,"corrupt"))for(unsigned island=0;island<population;island++)for(unsigned port=0;port<3;port++)for(int field=0;field<3;field++)for(int op=0;op<3;op++){
   auto p=static_cast<vvp_island_port*>((port==2?fixtures[island].e:port?fixtures[island].b:fixtures[island].a)->fun);
   auto& v=field==0?p->invalue:field==1?p->outvalue:p->value;
   unsigned bitindex=0;unsigned char byte=0;
   if(op!=2){
    if(!v.size())continue;
    for(;bitindex<v.size();bitindex++){auto bit=v.value(bitindex);memcpy(&byte,&bit,1);if(op==0 || byte==0 || byte==136)break;}
    if(bitindex==v.size())continue;
   }
   auto saved=v;
   if(op==2)v=vvp_vector8_t(v.size()+1);
   else {byte=op==1?byte^136:byte==238?102:238;vvp_scalar_t bit;memcpy(&bit,&byte,1);v.set_bit(bitindex,bit);}
   char *changed=snapshot(raw),*changed_old=snapshot(legacy);v=saved;
   char *restored=snapshot(raw),*restored_old=snapshot(legacy);
   if(!strcmp(before,changed)||strcmp(before,restored)||strcmp(old,restored_old))exit(2);
   if(op==1 && strcmp(old,changed_old))exit(2);
   printf("IRM_CHANGED %u %u %d %d\n%s%sIRM_RESTORED\n%s",island+1,port+1,field,op,changed,changed_old,restored);
   free(changed);free(changed_old);free(restored);free(restored_old);
  }
  free(before);free(old);
 }
 printf("IRM_DONE %u\n",stage++);
}
class Sink: public vvp_net_fun_t {
 unsigned index_;
 public:explicit Sink(unsigned index):index_(index){}
 void recv_vec8(vvp_net_ptr_t,const vvp_vector8_t& bits) override {
  printf("GROW_VALUE %llu %u ",(unsigned long long)schedule_simtime(),index_);
  for(unsigned i=0;i<bits.size();i++){auto scalar=bits.value(i);unsigned char raw;memcpy(&raw,&scalar,1);printf("%02x",raw);}
  printf("\n");
 }
};
static void allocate(unsigned index,unsigned width){
 auto island=new vvp_island_tran;auto a=new vvp_net_t;auto b=new vvp_net_t;auto e=new vvp_net_t;
 a->fun=new vvp_island_port(island);b->fun=new vvp_island_port(island);e->fun=new vvp_island_port(island);
 island->add_port("a",a);island->add_port("b",b);island->add_port("e",e);
 island->add_branch(new vvp_island_branch_tran(e,index%4>=2,0,0,0,index>=4),"a","b");island->compile_cleanup();
 auto sink=new vvp_net_t;sink->fun=new Sink(index);b->link(vvp_net_ptr_t(sink,0));fixtures[index]={a,b,e,width};population=index+1;
}
static PLI_INT32 startup(p_cb_data){unsigned widths[]={1,9,1,9,1,9,1,9};for(unsigned i=0;i<8;i++)allocate(i,widths[i]);observe(0);return 0;}
static vvp_vector8_t rawvector(unsigned width,unsigned char raw){vvp_vector8_t v(width);vvp_scalar_t scalar;memcpy(&scalar,&raw,1);for(unsigned i=0;i<width;i++)v.set_bit(i,scalar);return v;}
static PLI_INT32 drive(PLI_BYTE8*){
 ++phase;printf("GROW_PHASE %u\n",phase);
 for(unsigned i=0;i<8;i++){
  auto f=fixtures[i];auto target=vvp_net_ptr_t(f.a,0);
  static const vvp_bit4_t enables[]={BIT4_0,BIT4_1,BIT4_X,BIT4_Z,BIT4_0,BIT4_1,BIT4_X,BIT4_Z,BIT4_0,BIT4_1,BIT4_1,BIT4_Z};
  f.e->fun->recv_vec4(vvp_net_ptr_t(f.e,0),vvp_vector4_t(1,enables[phase-1]),0);
  static const unsigned char inputs[][2]={{0x66,0xee},{0x33,0xee},{0xee,0x55},{0x81,0xd3},{0x88,0x00},{0x00,0x88},{0xff,0x66},{0x77,0xee},{0xb5,0xd3},{0xee,0xee},{0xee,0xee},{0x00,0x00}};
  f.a->fun->recv_vec8(target,rawvector(f.width,inputs[phase-1][0]));
  f.b->fun->recv_vec8(vvp_net_ptr_t(f.b,0),rawvector(f.width,inputs[phase-1][1]));
 }
 return 0;
}
static PLI_INT32 settle(PLI_BYTE8*){observe(0);return 0;}
static void setup(){
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;vpi_register_cb(&cb);
 s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$growth_drive";t.calltf=drive;vpi_register_systf(&t);
 t.tfname="$growth_settle";t.calltf=settle;vpi_register_systf(&t);
}
extern "C" {void(*vlog_startup_routines[])(void)={setup,0};}
