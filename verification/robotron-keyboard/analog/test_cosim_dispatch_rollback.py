"""Exercise real ngspice hybrid dispatch with the input-barrier scheduler.

This is a source-level counterexample, not a live board capture or a claim that
its multiple-client schedule occurs in the keyboard's single-client circuit.
"""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent

MAIN=r'''
typedef struct instance MIFinstance;
typedef struct {
    struct { struct { int num_hybrids; } counts;
             struct { MIFinstance **hybrids; } info; } *evt;
    double CKTtime;
} CKTcircuit;
#define MIF_STEP_PENDING 1
static void EVTload_with_event(CKTcircuit *ckt, MIFinstance *ip, int call_type) {
    assert(call_type==MIF_STEP_PENDING);
    analog_time=ckt->CKTtime;
    run(ip);
}
/* DISPATCH */
int main(int argc,char **argv) {
    assert(argc==2);
    int reverse_order=atoi(argv[1]);
    const double base=1e-6,event=base+1e-9,trial=base+20e-9;
    struct pend_in q[1]={{event,0,1}};
    struct instance no_input={.info={base,Normal,step,input},.q_index=-1,
        .extra=bridge_delay/3,.last_step=base};
    struct instance queued={.info={base,Normal,step,input},.q_index=0,.q=q,
        .extra=bridge_delay/3,.last_step=base};
    MIFinstance *clients[2]={reverse_order?&queued:&no_input,
                            reverse_order?&no_input:&queued};
    CKTcircuit ckt={0};
    ckt.evt=calloc(1,sizeof *ckt.evt);
    ckt.evt->counts.num_hybrids=2;ckt.evt->info.hybrids=clients;
    ckt.CKTtime=trial;actual=base;history[1]=base;
    g_mif_info.breakpoint.current=INFINITY;
    EVTcall_hybrids(&ckt);
    assert(breakpoint==event&&inputs==0);
    if(reverse_order) {
        assert(steps==0&&actual==base);
        puts("queued-first: barrier stops dispatch before either client advances");
    } else {
        assert(steps==1&&actual==trial);
        /* The real dispatcher permits the first irreversible client to
         * advance before the second asks for an earlier analog boundary. */
        analog_time=event;
        run(&no_input);
        assert(reversals==1);
        puts("advance-first: later hybrid breakpoint leaves earlier client ahead of retry");
    }
    free(ckt.evt);
    return 0;
}
'''


class DispatchRollbackTests(unittest.TestCase):
    def test_client_order_exposes_remaining_rollback_limit(self):
        original=(HERE/'fixtures/ngspice-47/d_cosim.mod').read_text()
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),
                         'aa31bc8cf686914b3f667c9790aae4b79115a6f3b0e786732358a63df9340207')
        dispatcher=(HERE/'fixtures/ngspice-47/evtcall_hybrids.c').read_text()
        self.assertEqual(hashlib.sha256(dispatcher.encode()).hexdigest(),
                         '99e84099cd0420eb6e0c026baa0e28e5ae6866b47125dc77645e85712db3ffeb')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'src/xspice/icm/digital/d_cosim/cfunc.mod'
            source.parent.mkdir(parents=True);source.write_text(original)
            subprocess.run(['patch','-d',str(root),'-p1','-i',str(HERE/'engine-patches/cosim-input-barrier.patch')],check=True,capture_output=True)
            text=source.read_text()
            scheduler=text[text.index('static int advance('):text.index('/* Check whether an input value has changed.')]
            scheduler=scheduler.replace(', XSPICE_ARG','').replace(', ARGS','')
            header=(HERE/'fixtures/cosim_order_harness.c').read_text().split('/* SCHEDULER */')[0]
            header=header.replace('static int cm_analog_set_temp_bkpt',
                'static struct { struct { double current; } breakpoint; } g_mif_info;\nstatic int cm_analog_set_temp_bkpt')
            header=header.replace('breakpoint=t;return 0;',
                'breakpoint=t;g_mif_info.breakpoint.current=t;return 0;')
            harness=header+scheduler+MAIN.replace('/* DISPATCH */',dispatcher[dispatcher.index('\nvoid EVTcall_hybrids('):])
            (root/'test.c').write_text(harness)
            subprocess.run(['cc','-std=c11','-O2',str(root/'test.c'),'-o',str(root/'test')],check=True)
            for order in (0,1):
                result=subprocess.run([str(root/'test'),str(order)],check=True,capture_output=True,text=True)
                print(result.stdout.strip())


if __name__=='__main__':unittest.main()
