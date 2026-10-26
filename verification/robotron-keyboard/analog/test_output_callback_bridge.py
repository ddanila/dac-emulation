import os,subprocess,tempfile,unittest
from pathlib import Path
from build_output_callback_bridge import HERE,output_vpi,output_header
from build_port_identity_bridge import ports_vpi


class OutputCallbackBridge(unittest.TestCase):
    def test_watch_handoff_keeps_port_initialization_boundary(self):
        source='    vpi_register_cb(&cb);\n    cbd.user_data = (PLI_BYTE8 *)Get_ng_vvp();\n    vpi_register_cb(&cbd);\n    /* Make a direct call to the "end-of-advance" callback to start running. */\n'
        result=output_vpi(source)
        handoff='''    extern void Robotron_output_registration(void*, vpiHandle, PLI_INT32(*)(struct t_cb_data*), vpiHandle);
    vpiHandle registered = vpi_register_cb(&cb);
    Robotron_output_registration(pp, registered, output_cb, handle);'''
        self.assertEqual(result.replace(handoff,'    vpi_register_cb(&cb);'),ports_vpi(source))
        with self.assertRaises(ValueError):output_vpi(source+source)
        header=output_header((HERE/'fixtures/display_board_bridge.h').read_text())
        self.assertIn('robotron_output_inventory(f, ctx)',header)
        self.assertLess(header.index('robotron_output_fault(output_field)!=1) exit(3)'),header.index('int rejected=changed==NULL;'))

    def test_registration_accepts_poisoned_uninitialized_ports_and_rejects_rebinding(self):
        prefix=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
struct __vpiHandle;struct t_cb_data;
struct ng_vvp;
struct ngvp_port {struct __vpiHandle *handle;struct ng_vvp *ctx;};
struct ng_vvp {struct ngvp_port *ports;unsigned ins,outs,inouts;void *vvp_handle;};
static struct ng_vvp *robotron_identity_context,*robotron_ports_context;
static struct ngvp_port ports[3];static int bad;
static int32_t callback(struct t_cb_data *cb) {(void)cb;return 0;}
static unsigned long long lookup(const void *h,int32_t(*fn)(struct t_cb_data*),char *u,struct __vpiHandle *s) {
 if(bad || fn!=callback) return 0;
 for(unsigned i=1;i<3;i++) if(h==(void*)(uintptr_t)(i*32) && u==(char*)(ports+i) && s==(void*)(uintptr_t)(i*16)) return 100+i;
 return 0;
}
static int toggle(const void *h,int32_t(*fn)(struct t_cb_data*),char *u,struct __vpiHandle *s,int field) {
 (void)h;(void)fn;(void)u;(void)s;if(field<0 || field>3) return -1;bad=!bad;return 1;
}
static void *fake_dlsym(void *lib,const char *name) {
 if(lib!=(void*)1) exit(9);
 if(!strcmp(name,"robotron_vvp_value_identity")) return (void*)lookup;
 if(!strcmp(name,"robotron_vvp_value_toggle")) return (void*)toggle;
 return NULL;
}
#define dlsym fake_dlsym
'''
        suffix=r'''
static char *shot(struct ng_vvp *ctx) {char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);int r=robotron_output_inventory(f,ctx);fclose(f);if(r){free(p);return NULL;}return p;}
int main(int argc,char **argv) {
 (void)argc;struct ng_vvp ctx={ports,1,1,1,(void*)1};robotron_identity_context=&ctx;
 memset(ports,0xa5,sizeof ports);
 Robotron_output_registration(ports+2,(void*)64,callback,(void*)32);
 Robotron_output_registration(ports+1,(void*)32,callback,(void*)16);
 if(!strcmp(argv[1],"duplicate")) {Robotron_output_registration(ports+1,(void*)32,callback,(void*)16);return 8;}
 if(shot(&ctx)) return 10;
 for(unsigned i=1;i<3;i++) {ports[i].ctx=&ctx;ports[i].handle=(void*)(uintptr_t)(i*16);}
 robotron_ports_context=&ctx;
 char *before=shot(&ctx);if(!before) return 11;
 for(int field=0;field<4;field++) {
  if(robotron_output_fault(field)!=1 || shot(&ctx) || robotron_output_fault(field)!=1) return 12;
  char *after=shot(&ctx);if(!after || strcmp(before,after)) return 13;free(after);
 }
 ports[1].ctx=NULL;if(shot(&ctx)) return 14;ports[1].ctx=&ctx;
 ports[1].handle=(void*)1;if(shot(&ctx)) return 15;ports[1].handle=(void*)16;
 puts(before);free(before);return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'probe.c').write_text(prefix+(HERE/'fixtures/output_callback_bridge.h').read_text()+suffix)
            subprocess.run([os.environ.get('CC','cc'),'-Werror=incompatible-pointer-types',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True,text=True)
            result=subprocess.run([str(p/'probe'),'normal'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip().splitlines(),['VW_BEGIN 1 2','VW_LINK 1 101','VW_LINK 2 102','VW_END'])
            self.assertEqual(subprocess.run([str(p/'probe'),'duplicate']).returncode,2)


if __name__=='__main__':unittest.main()
