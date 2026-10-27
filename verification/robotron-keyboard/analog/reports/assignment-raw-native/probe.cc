#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <vpi_user.h>
#include "schedule.h"
typedef void(*Factory)(vvp_net_t*,unsigned,unsigned,unsigned char,int,int);
static Factory factory;
static vvp_net_t* targets[2];
static bool enabled,nested,early;
static unsigned phase,stage;
static int family;
static char* capture(int(*api)(FILE*),int* result,size_t* size){
 char* p=0;*size=0;FILE* f=open_memstream(&p,size);if(!f)exit(2);*result=api(f);if(fclose(f))exit(2);return p;
}
static void observe(const char* label){
 if(!enabled)return;
 auto api=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_raw_inventory");
 auto legacy=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_inventory");
 auto toggle=(int(*)(unsigned long long,int))dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_raw_toggle");
 if(!api || !legacy || !toggle)exit(2);
 size_t n,m;int result,again;char* first=capture(api,&result,&n);char* second=capture(api,&again,&m);
 if(result!=again || n!=m || memcmp(first,second,n))exit(2);
 printf("AF_OBSERVE %u %u %s %d\n",stage++,phase,label,result);
 if(result==-1){
  if(n)exit(2);
  int r1,r2;size_t n1,n2;auto before=capture(legacy,&r1,&n1);
  if(toggle(0,0)!=-1)exit(2);
  auto after=capture(legacy,&r2,&n2);
  if(r1 || r2 || n1!=n2 || memcmp(before,after,n1))exit(2);
  free(before);free(after);puts("AF_REFUSED_EMPTY");
 }else{if(result || !n)exit(2);fwrite(first,1,n,stdout);}
 free(first);free(second);
}
class Sink:public vvp_net_fun_t {
 unsigned index;
 public:explicit Sink(unsigned i):index(i){}
 void recv_vec8(vvp_net_ptr_t p,const vvp_vector8_t& bits) override {
  observe(index?"inner":"outer-before");
  if(nested && !index){factory(targets[1],3,80,0xb5,family,2);observe("outer-after");}
  printf("AF_VALUE %llu %u %u %u ",(unsigned long long)schedule_simtime(),phase,index,p.port());
  for(unsigned i=0;i<bits.size();i++){auto scalar=bits.value(i);unsigned char raw;memcpy(&raw,&scalar,1);printf("%02x",raw);}
  puts("");
 }
};
static PLI_INT32 start(p_cb_data){
 factory=(Factory)dlsym(RTLD_DEFAULT,"robotron_assignment_fixture");if(!factory)exit(2);
 nested=!strcmp(getenv("K7658_AF_KIND"),"nested");early=!strcmp(getenv("K7658_AF_TIMING"),"early");family=atoi(getenv("K7658_AF_FAMILY"));enabled=!strcmp(getenv("K7658_AF_MODE"),"observe");
 for(unsigned i=0;i<2;i++){targets[i]=new vvp_net_t;targets[i]->fun=new Sink(i);}
 factory(targets[0],1,9,0x88,0,0);
 if(!nested && early)factory(targets[1],3,80,0xb5,family,0);
 observe("queued");return 0;
}
static PLI_INT32 afterstart(p_cb_data){observe("settled");return 0;}
static PLI_INT32 drive(PLI_BYTE8*){
 ++phase;factory(targets[0],1,9,0x88,0,1);
 if(!nested)factory(targets[1],3,80,0xb5,family,1);
 observe("queued");return 0;
}
static PLI_INT32 settled(PLI_BYTE8*){observe("settled");return 0;}
static void setup(){
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=start;vpi_register_cb(&cb);
 cb.reason=cbStartOfSimulation;cb.cb_rtn=afterstart;vpi_register_cb(&cb);
 s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$native_drive";t.calltf=drive;vpi_register_systf(&t);
 t.tfname="$native_settled";t.calltf=settled;vpi_register_systf(&t);
}
extern "C" {void(*vlog_startup_routines[])(void)={setup,0};}
