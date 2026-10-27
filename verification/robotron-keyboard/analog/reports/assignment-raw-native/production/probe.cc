#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <vector>
#include <vpi_user.h>
#include "schedule.h"
static unsigned phase,stage;
static char* snapshot(int(*api)(FILE*)) {
 char* p=0;size_t n=0;FILE* f=open_memstream(&p,&n);if(!f)exit(2);
 int r=api(f);if(fclose(f)||r)exit(2);return p;
}
static void observe(int callback) {
 auto raw=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_raw_inventory");
 auto legacy=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_inventory");
 auto toggle=(int(*)(unsigned long long,int))dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_raw_toggle");
 auto mode=getenv("K7658_ASSIGNMENT_RAW");
 printf("ARM_STAGE %u %u %d %d\n",stage,phase,callback,raw!=0);
 if(mode && strcmp(mode,"off")) {
  if(!raw || !legacy || !toggle)exit(2);
  auto before=snapshot(raw),old=snapshot(legacy),repeat=snapshot(raw);
  if(strcmp(before,repeat))exit(2);
  printf("ARM_BEFORE\n%s%sARM_REPEAT\n%s",before,old,repeat);free(repeat);
  if(!strcmp(mode,"corrupt")) {
   std::vector<unsigned long long> ids;char* copy=strdup(before);char* save=0;
   for(char* line=strtok_r(copy,"\n",&save);line;line=strtok_r(0,"\n",&save)) {
    long long slot;char region[32];unsigned long long ordinal,id;
    if(sscanf(line,"VAR_EVENT %lld %31s %llu %llu",&slot,region,&ordinal,&id)==4)ids.push_back(id);
   }
   free(copy);
   for(auto id:ids)for(int op=0;op<4;op++) {
    int r=toggle(id,op);if(r!=0 && r!=1)exit(2);
    if(!r)continue;
    auto changed=snapshot(raw),changed_old=snapshot(legacy);
    if(toggle(id,op)!=1)exit(2);
    auto restored=snapshot(raw),restored_old=snapshot(legacy);
    if(!strcmp(before,changed)||strcmp(before,restored)||strcmp(old,restored_old))exit(2);
    if(op==1 && strcmp(old,changed_old))exit(2);
    printf("ARM_CHANGED %llu %d\n%s%sARM_RESTORED\n%s",id,op,changed,changed_old,restored);
    free(changed);free(changed_old);free(restored);free(restored_old);
   }
  }
  free(before);free(old);
 }
 printf("ARM_DONE %u\n",stage++);
}
static const unsigned widths[]={0,1,8,9,80};
static const unsigned char values[]={0x00,0x88,0x81,0x90,0xb5,0xd3,0xe7,0xf6,0x12,0x67,0xa9,0xfe,0xff,0x77,0xee,0x66};
static vvp_net_t* targets[5];
class Sink:public vvp_net_fun_t {
 unsigned index;
 public:explicit Sink(unsigned i):index(i){}
 void recv_vec8(vvp_net_ptr_t ptr,const vvp_vector8_t& bits) override {
  observe(index+1);
  printf("ARM_VALUE %llu %u %u %u ",(unsigned long long)schedule_simtime(),phase,index,ptr.port());
  if(!bits.size())printf("-");
  for(unsigned i=0;i<bits.size();i++){auto scalar=bits.value(i);unsigned char raw;memcpy(&raw,&scalar,1);printf("%02x",raw);}
  printf("\n");
 }
};
static void enqueue(bool initial){
 for(unsigned j=0;j<5;j++) {
  vvp_vector8_t val(widths[j]);
  for(unsigned k=0;k<widths[j];k++){vvp_scalar_t scalar;unsigned char raw=values[(phase+k)%16];memcpy(&scalar,&raw,1);val.set_bit(k,scalar);}
  vvp_net_ptr_t ptr(targets[j],j%4);
  if(initial)schedule_init_vector(ptr,val);else schedule_set_vector(ptr,val);
 }
 observe(0);
}
static PLI_INT32 startup(p_cb_data){for(unsigned j=0;j<5;j++){targets[j]=new vvp_net_t;targets[j]->fun=new Sink(j);}enqueue(true);return 0;}
static PLI_INT32 drive(PLI_BYTE8*){++phase;enqueue(false);return 0;}
static PLI_INT32 settled(PLI_BYTE8*){observe(-1);return 0;}
static void setup(){
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;vpi_register_cb(&cb);
 s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$raw_drive";t.calltf=drive;vpi_register_systf(&t);
 t.tfname="$raw_settled";t.calltf=settled;vpi_register_systf(&t);
}
extern "C" {void(*vlog_startup_routines[])(void)={setup,0};}
