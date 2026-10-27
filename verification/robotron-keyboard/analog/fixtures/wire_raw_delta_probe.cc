#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <string>
#include <vpi_user.h>
#include "vvp_net.h"
#include "vvp_net_sig.h"
#include "schedule.h"
static vvp_net_t* nodes[4];static unsigned widths[]={1,8,9,80};static unsigned stage;
static unsigned raw(vvp_scalar_t value){static_assert(sizeof(value)==1,"Scalar byte");unsigned char b;memcpy(&b,&value,1);return b;}
static char* snapshot(int(*api)(FILE*)){
 char* p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);int r=api(f);if(fclose(f))r=-1;if(r)exit(2);
 auto raw=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_wire_raw_inventory"));
 if(api==raw){
  auto reference=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_wire_raw_reference"));
  auto delta=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_wire_raw_delta_inventory"));
  if(!reference || !delta)exit(2);static bool ready;
  if(!ready){
   FILE* refused=tmpfile();if(!refused)exit(2);
   if(delta(refused)!=-1 || ftell(refused)!=0 || reference(stdout))exit(2);
   if(reference(refused)!=-1 || ftell(refused)!=0 || fclose(refused))exit(2);
   ready=true;
  }
  printf("WRC_PAIR\n%s",p);if(delta(stdout))exit(2);
 }
 return p;
}
static void observe(){
 const char* mode=getenv("K7658_WIRE_RAW");
 auto inventory=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_wire_raw_inventory"));
 auto legacy=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_wire_inventory"));
 auto toggle=reinterpret_cast<int(*)(unsigned long long,int)>(dlsym(RTLD_DEFAULT,"robotron_vvp_wire_raw_toggle"));
 printf("WBR_STAGE %u\n",stage);
 if(mode && strcmp(mode,"off")){
  if(!inventory || !legacy || !toggle)exit(2);
  char* before=snapshot(inventory),*repeat=snapshot(inventory),*old=snapshot(legacy);
  if(strcmp(before,repeat))exit(2);free(repeat);
  printf("WBR_BEFORE\n%sWBR_LEGACY\n%s",before,old);
  if(!strcmp(mode,"corrupt")){
   std::string text(before);size_t pos=0;
   while((pos=text.find("VWB_FILTER ",pos))!=std::string::npos){
    unsigned long long id;if(sscanf(text.c_str()+pos,"VWB_FILTER %llu",&id)!=1)exit(2);pos++;
    for(int field=0;field<2;field++){
     int found=toggle(id,field);if(found!=0 && found!=1)exit(2);if(!found)continue;
     char* changed=snapshot(inventory),*hidden=snapshot(legacy);
     if(!strcmp(before,changed) || strcmp(old,hidden))exit(2);
     if(toggle(id,field)!=1)exit(3);char* restored=snapshot(inventory),*restored_old=snapshot(legacy);
     if(strcmp(before,restored) || strcmp(old,restored_old))exit(3);
     printf("WBR_CHANGED %llu %d\n%sWBR_RESTORED\n%sWBR_COLLISION %llu %d 1 1\n",id,field,changed,restored,id,field);
     free(changed);free(hidden);free(restored);free(restored_old);
    }
   }
  }
  free(before);free(old);
 }
 for(unsigned i=0;i<4;i++){
  auto wire=static_cast<vvp_wire_vec8*>(nodes[i]->fil);auto value=wire->vec8_value();
  printf("WIRE_RAW_VALUE %u %u ",stage,i);for(unsigned j=0;j<value.size();j++)printf("%02x",raw(value.value(j)));printf("\n");
 }
 printf("WBR_DONE %u\n",stage);
}
static PLI_INT32 startup(p_cb_data){for(unsigned i=0;i<4;i++){nodes[i]=new vvp_net_t;nodes[i]->fil=new vvp_wire_vec8(widths[i]);}observe();return 0;}
static PLI_INT32 step(PLI_BYTE8*){
 ++stage;
 for(unsigned i=0;i<4;i++){
  unsigned w=widths[i];auto wire=static_cast<vvp_wire_vec8*>(nodes[i]->fil);vvp_vector8_t value(w),rep;
  if(stage==1){value.set_bit(w-1,vvp_scalar_t(BIT4_1,1,0));wire->filter_vec8(value,rep,0,w);wire->force_fil_vec8(vvp_vector8_t(w),vvp_vector2_t(vvp_vector2_t::FILL1,w));}
  if(stage==2){for(unsigned j=0;j<w;j++)value.set_bit(j,vvp_scalar_t(static_cast<vvp_bit4_t>(j%4),3,5));wire->filter_vec8(value,rep,0,w);value.set_bit(0,vvp_scalar_t(BIT4_1,1,0));wire->force_fil_vec8(value,vvp_vector2_t(vvp_vector2_t::FILL1,w));}
 }
 observe();return 0;
}
static void setup(){s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(2);s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$wire_raw_step";task.calltf=step;vpi_register_systf(&task);}
extern "C" {void(*vlog_startup_routines[])(void)={setup,0};}
