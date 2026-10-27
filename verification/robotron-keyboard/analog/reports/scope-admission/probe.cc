#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <algorithm>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*inventory)(FILE*);static unsigned round_id;
static std::string snapshot(bool refuse=false){
 if(!inventory)return "";
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=inventory(f);if(fclose(f))exit(2);std::string s(p,n);free(p);
 if(refuse ? (rc>=0||n) : rc!=0)exit(2);return s;
}
static void refused(const char*kind){snapshot(true);printf("REFUSED %s\n",kind);}
static PLI_INT32 run(PLI_BYTE8*){
 auto scope=dynamic_cast<__vpiScope*>(vpi_handle_by_name("test",0));
 auto child=dynamic_cast<__vpiScope*>(vpi_handle_by_name("test.child",0));
 if(!scope||!child||scope->intern.empty())exit(2);
 const char*mode=getenv("K7658_SCOPE_ADMISSION");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_inventory");if(!inventory)exit(2);
 }
 ++round_id;printf("ROUND %u\n",round_id);auto before=snapshot();
 if(inventory)printf("IMAGE before%u\n%s",round_id,before.c_str());
 __vpiHandle**roots=0;unsigned count=0;vpip_make_root_iterator(roots,count);if(!count)exit(2);
 auto root=roots[0];roots[0]=reinterpret_cast<vpiHandle>(1);refused("root");roots[0]=root;
 auto item=scope->intern.front();scope->intern.front()=reinterpret_cast<vpiHandle>(1);refused("intern");scope->intern.front()=item;
 auto parent=child->scope;child->scope=reinterpret_cast<__vpiScope*>(1);refused("parent");child->scope=parent;
 auto intern=scope->intern;auto found=std::find(scope->intern.begin(),scope->intern.end(),child);
 if(found==scope->intern.end())exit(2);scope->intern.erase(found);refused("missing-child");scope->intern=intern;
 auto after=snapshot();if(after!=before)exit(2);
 if(inventory)printf("IMAGE restored%u\n%s",round_id,after.c_str());
 printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$scope_admission";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
