import os,subprocess,tempfile,unittest
from pathlib import Path
from build_port_identity_bridge import HERE,ports_header,ports_vpi
from build_private_sync_family_bridge import identity_vpi
from port_identity_review import snapshot


class PortIdentityTests(unittest.TestCase):
    def test_vpi_binds_after_initialization_before_first_yield_only(self):
        source='    cbd.user_data = (PLI_BYTE8 *)Get_ng_vvp();\n    vpi_register_cb(&cbd);\n    /* Make a direct call to the "end-of-advance" callback to start running. */\n    cr_init(&ctx->cr_ctx);\n'
        result=ports_vpi(source)
        self.assertLess(result.index('Robotron_ports_identity(ctx,'),result.index('cr_init(&ctx->cr_ctx)'))
        removed=result.replace('    extern void Robotron_ports_identity(struct ng_vvp*, char*(*)(PLI_INT32,vpiHandle), PLI_INT32);\n    Robotron_ports_identity(ctx, vpi_get_str, vpiFullName);\n\n','')
        self.assertEqual(removed,identity_vpi(source))
        with self.assertRaises(ValueError):ports_vpi(source+source)
        header=(HERE/'fixtures/display_board_bridge.h').read_text();ports=(HERE/'fixtures/port_identity_bridge.h').read_text()
        self.assertIn('robotron_ports_inventory(f, ctx)',ports_header(header,ports))
        with self.assertRaises(ValueError):ports_header(header.replace('api.association(f, api.lookup)','changed'),ports)

    def test_compiled_identity_checks_and_ignored_input_new_storage(self):
        prefix=r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
struct __vpiHandle;
struct co_info {int unused;};
struct ng_vvp;
struct ngvp_port {uint16_t bits,flags;uint32_t position;struct {int32_t aval,bval;} previous,new;struct __vpiHandle *handle;struct ng_vvp *ctx;};
struct ng_vvp {struct co_info *cosim_context;uint32_t ins,outs,inouts;double base_time,tick_length;int stop;uint32_t in_pending,out_pending;struct ngvp_port *ports;void *vvp_handle;};
#define IN_PENDING 1
#define OUT_PENDING 2
static struct ng_vvp *robotron_identity_context;
static unsigned name_reads;
static char *name(int32_t property,struct __vpiHandle *handle) {
 if(property!=3) exit(8);
 ++name_reads;
 if(handle==(void*)(uintptr_t)16) return "input";
 if(handle==(void*)(uintptr_t)32) return "output";
 if(handle==(void*)(uintptr_t)48) return "bidirectional";
 exit(9);
}
'''
        suffix=r'''
static char *shot(struct ng_vvp *ctx) {
 char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);
 int result=robotron_ports_inventory(f,ctx);fclose(f);
 if(result) {free(text);return NULL;} return text;
}
int main(int argc,char **argv) {
 (void)argc;struct co_info co={0};struct ngvp_port p[3];memset(p,0,sizeof p);
 struct ng_vvp ctx={.cosim_context=&co,.ins=1,.outs=1,.inouts=1,.tick_length=1e-12,.in_pending=2,.out_pending=2,.ports=p,.vvp_handle=(void*)1};
 robotron_identity_context=&ctx;
 for(unsigned i=0;i<3;++i) {p[i].handle=(void*)(uintptr_t)((i+1)*16);p[i].ctx=&ctx;p[i].bits=i?2:8;p[i].flags=i+1;p[i].previous.aval=i;}
 p[1].new.aval=1;p[2].new.aval=2;
 if(shot(&ctx)) return 10;
 Robotron_ports_identity(&ctx,name,3);
 if(!strcmp(argv[1],"duplicate")) {Robotron_ports_identity(&ctx,name,3);return 11;}
 char *before=shot(&ctx);if(!before) return 12;
 memset(&p[0].new,0xa5,sizeof(p[0].new));char *after=shot(&ctx);
 if(!after || strcmp(before,after)) return 13;free(after);
 memset(&p[0].new,0x5a,sizeof(p[0].new));after=shot(&ctx);
 if(!after || strcmp(before,after)) return 14;free(after);
 p[0].handle=(void*)1;if(shot(&ctx)) return 15;p[0].handle=(void*)16;
 p[0].ctx=(void*)1;if(shot(&ctx)) return 16;p[0].ctx=&ctx;
 ctx.ports=(void*)1;if(shot(&ctx)) return 17;ctx.ports=p;
 ctx.ins=2;if(shot(&ctx)) return 18;ctx.ins=1;
 ctx.cosim_context=(void*)1;if(shot(&ctx)) return 19;ctx.cosim_context=&co;
 ctx.vvp_handle=(void*)2;if(shot(&ctx)) return 20;ctx.vvp_handle=(void*)1;
 p[0].bits=7;if(shot(&ctx)) return 21;p[0].bits=8;
 p[0].flags=3;if(shot(&ctx)) return 22;p[0].flags=1;
 ctx.in_pending=1;if(shot(&ctx)) return 23;ctx.in_pending=2;
 p[0].previous.aval^=1;after=shot(&ctx);if(!after || !strcmp(before,after)) return 24;free(after);p[0].previous.aval^=1;
 after=shot(&ctx);if(!after || strcmp(before,after) || name_reads!=3) return 25;
 puts(after);free(before);free(after);return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'probe.c').write_text(prefix+(HERE/'fixtures/port_identity_bridge.h').read_text()+suffix)
            subprocess.run([os.environ.get('CC','cc'),'-Werror=incompatible-pointer-types',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True,text=True)
            result=subprocess.run([str(p/'probe'),'normal'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            parsed=snapshot(result.stdout.strip().splitlines())
            self.assertIsNone(parsed['ports'][0]['new']);self.assertEqual(parsed['ports'][2]['new'],[2,0])
            duplicate=subprocess.run([str(p/'probe'),'duplicate'],capture_output=True,text=True)
            self.assertEqual(duplicate.returncode,2)

    def test_parser_rejects_input_new_missing_ports_and_pending_mismatch(self):
        lines=['VP_BEGIN 1 1 0 0','VP_CONTEXT 0x0p+0 0x1p-40 1 0 0','VP_PORT 0 1 8 0 1 0 0 - - 696e','VP_END']
        snapshot(lines)
        for before,after in [('- -','0 0'),(' 1 0 0',' 0 0 0'),('8 0 1','8 1 1')]:
            with self.assertRaises(ValueError):snapshot([l.replace(before,after) for l in lines])
        with self.assertRaises(ValueError):snapshot(lines[:2]+lines[-1:])


if __name__=='__main__':unittest.main()
