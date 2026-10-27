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
static std::string before;
static void changed(const char*kind){auto s=snapshot();if(inventory){if(s==before)exit(2);printf("IMAGE %s%u\n%s",kind,round_id,s.c_str());}printf("CHANGED %s\n",kind);}
static void restored(){if(snapshot()!=before)exit(2);}
static void refused(const char*kind){snapshot(true);printf("REFUSED %s\n",kind);}
static PLI_INT32 run(PLI_BYTE8*){
 auto scope=dynamic_cast<__vpiScope*>(vpi_handle_by_name("test",0));
 auto child=dynamic_cast<__vpiScope*>(vpi_handle_by_name("test.child",0));
 auto value=vpi_handle_by_name("test.value",0);
 if(!scope||!child||!value||scope->intern.size()<2)exit(2);
 const char*mode=getenv("K7658_SCOPE_METADATA");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_metadata_inventory");if(!inventory)exit(2);
 }
 ++round_id;printf("ROUND %u\n",round_id);before=snapshot();
 if(inventory)printf("IMAGE before%u\n%s",round_id,before.c_str());
 int units=scope->time_units;scope->time_units=units+1;changed("units");scope->time_units=units;restored();
 int precision=scope->time_precision;scope->time_precision=precision+1;changed("precision");scope->time_precision=precision;restored();
 unsigned f=scope->file_idx;scope->file_idx=f+1;changed("file");scope->file_idx=f;restored();
 unsigned l=scope->lineno;scope->lineno=l+17;changed("line");scope->lineno=l;restored();
 f=scope->def_file_idx;scope->def_file_idx=f+1;changed("deffile");scope->def_file_idx=f;restored();
 l=scope->def_lineno;scope->def_lineno=l+17;changed("defline");scope->def_lineno=l;restored();
 bool cell=scope->is_cell;scope->is_cell=!cell;changed("cell");scope->is_cell=cell;restored();
 char*name=const_cast<char*>(scope->scope_name());char c=name[0];name[0]='X';changed("name");name[0]=c;restored();
 char*definition=const_cast<char*>(scope->scope_def_name());c=definition[0];definition[0]='Y';changed("definition");definition[0]=c;restored();
 auto intern=scope->intern;auto found=std::find(scope->intern.begin(),scope->intern.end(),value);
 if(found==scope->intern.end())exit(2);scope->intern.erase(found);changed("omit");scope->intern=intern;restored();
 std::swap(scope->intern[0],scope->intern[1]);changed("order");scope->intern=intern;restored();
 auto time=scope->scoped_time.scope;auto stime=scope->scoped_stime.scope;auto realtime=scope->scoped_realtime.scope;
 if(time||stime||realtime)exit(2);
 vpip_sim_time(scope,false);changed("time");scope->scoped_time.scope=time;restored();
 vpip_sim_time(scope,true);changed("stime");scope->scoped_stime.scope=stime;restored();
 vpip_sim_realtime(scope);changed("realtime");scope->scoped_realtime.scope=realtime;restored();
 scope->scoped_time.scope=reinterpret_cast<__vpiScope*>(1);refused("time");scope->scoped_time.scope=time;restored();
 scope->scoped_stime.scope=child;refused("stime");scope->scoped_stime.scope=stime;restored();
 scope->scoped_realtime.scope=reinterpret_cast<__vpiScope*>(1);refused("realtime");scope->scoped_realtime.scope=realtime;restored();
 scope->classes["foreign"]=reinterpret_cast<class_type*>(1);refused("classes");scope->classes.clear();restored();
 __vpiHandle**roots=0;unsigned count=0;vpip_make_root_iterator(roots,count);if(!count)exit(2);
 auto root=roots[0];roots[0]=reinterpret_cast<vpiHandle>(1);refused("root");roots[0]=root;restored();
 auto item=scope->intern.front();scope->intern.front()=reinterpret_cast<vpiHandle>(1);refused("intern");scope->intern.front()=item;restored();
 auto parent=child->scope;child->scope=reinterpret_cast<__vpiScope*>(1);refused("parent");child->scope=parent;restored();
 found=std::find(scope->intern.begin(),scope->intern.end(),child);if(found==scope->intern.end())exit(2);
 scope->intern.erase(found);refused("missing-child");scope->intern=intern;restored();
 if(inventory)printf("IMAGE restored%u\n%s",round_id,before.c_str());printf("RESTORED %u\n",round_id);return 0;
}
static PLI_INT32 unsupported(PLI_BYTE8*){
 const char*mode=getenv("K7658_SCOPE_METADATA");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_metadata_inventory");if(!inventory)exit(2);
 }
 snapshot(true);printf("REFUSED automatic\n");return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$scope_metadata";t.calltf=run;vpi_register_systf(&t);t.tfname="$scope_metadata_refuse";t.calltf=unsupported;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
