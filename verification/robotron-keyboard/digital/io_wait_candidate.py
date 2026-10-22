#!/usr/bin/env python3
"""Isolated falling-edge WAIT acceptance for ordinary I/O reads."""
from io_flags_candidate import replace_once


def c_generate(text):
    text = replace_once(text, 'static void c_read_reset', '''static int c_read_waiting(unsigned step) {
 switch(step){case 973:case 1187:case 1221:case 1255:case 1284:case 1313:case 1351:case 1389:case 1417:case 1462:case 1494:case 1536:case 1588:return 1;default:return 0;}
}
static void c_read_reset''')
    text = replace_once(text, 'c->pending=c_read_consuming(c->cpu.step);',
                        'c->pending=c_read_consuming(c->cpu.step)?1:(c_read_waiting(c->cpu.step)?2:0);')
    text = replace_once(text, 'c->pins&=~(Z80_IORQ|Z80_RD);c->pending=0;',
                        'if(c->pending==1)c->pins&=~(Z80_IORQ|Z80_RD);\n  c->pending=0;')
    return text


def hdl_generate(text):
    text = replace_once(text, ' wire bmreq,biorq,brd,bwr;', ''' reg wait_sampled=1;
 always @(negedge clk or negedge reset_n)
  if(!reset_n)wait_sampled<=1;
  else wait_sampled<=wait_n;
 wire read_wait=base.iorq && !base.mcycle[0] && !base.write;
 wire accepted_wait=read_wait?wait_sampled:wait_n;
 wire bmreq,biorq,brd,bwr;''')
    return replace_once(text, '.wait_n(wait_n)', '.wait_n(accepted_wait)')


def core_generate(text):
    # An external wait must not restart the already-completed automatic I/O wait.
    start = "              if (T_Res == 1'b1 ) \n                begin\n                  Auto_Wait_t1"
    text = replace_once(text, start, "              if (!(iorq_i && !mcycle[0] && !write && tstate[2] && !wait_n)) begin\n" + start)
    return replace_once(text, '              Auto_Wait_t2 <= `TV80DELAY Auto_Wait_t1 & !T_Res;',
                        '              Auto_Wait_t2 <= `TV80DELAY Auto_Wait_t1 & !T_Res;\n              end')
