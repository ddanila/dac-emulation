#!/usr/bin/env python3
"""Z80 repeated-I/O flag effects during the PC rewind, including interrupts.

Reference: David Banks, Z80Decoder/Undocumented-Flags, INxR/OTxR interrupted.
These are reference Z80 semantics, not measured U880 variant identification.
"""
from io_flags_candidate import replace_once
from io_complete_candidate import c_core as base_c,hdl_core as base_hdl


def c_core(text):
    text=base_c(text)
    helper='''static void _z80_repeat_io_flags(z80_t *cpu) {
    unsigned b=cpu->b, d=cpu->dlatch, f=cpu->f;
    unsigned term=b;
    f=(f&~(Z80_YF|Z80_XF))|((cpu->pc>>8)&(Z80_YF|Z80_XF));
    if(f&Z80_CF){
        term=(d&0x80)?b-1:b+1;
        f&=~Z80_HF;
        if((b&15)==((d&0x80)?0:15))f|=Z80_HF;
    }
    unsigned low=term&7;
    unsigned odd=(low^(low>>1)^(low>>2))&1;
    if(odd)f^=Z80_PF;
    cpu->f=(uint8_t)f;
}
'''
    anchor='uint64_t z80_tick(z80_t* cpu, uint64_t pins) {'
    text=replace_once(text,anchor,helper+'\n'+anchor)
    for state,target,name in [(1541,1542,'INIR'),(1554,1555,'OTIR'),(1593,1594,'INDR'),(1606,1607,'OTDR')]:
        old=f'case {state}: cpu->wz=--cpu->pc;--cpu->pc;_goto({target}); // {name}'
        text=replace_once(text,old,old.replace(';_goto',';_z80_repeat_io_flags(cpu);_goto'))
    return text


def hdl_core(text):
    text=base_hdl(text)
    text=replace_once(text,'  reg [7:0] block_data, block_b, block_term;', '''  reg [7:0] block_data, block_b, block_term;
  reg [7:0] repeat_data,repeat_count;
  wire [7:0] repeat_adjusted=repeat_data[7]?repeat_count-8'd1:repeat_count+8'd1;
  wire [2:0] repeat_parity_term=F[Flag_C]?repeat_adjusted[2:0]:repeat_count[2:0];
''')
    text=replace_once(text,'  always @(posedge clk or negedge reset_n)','  always @(posedge clk or negedge reset_n)\n    if(!reset_n)begin repeat_data<=0;repeat_count<=0;end\n    else if(ClkEn && block_io && mcycle[2] && T_Res)begin\n      repeat_data<=block_value;repeat_count<=block_count;\n    end\n  always @(posedge clk or negedge reset_n)')
    anchor='''                          //PC <= `TV80DELAY PC - 2;
                          PC <= `TV80DELAY PC16;'''
    text=replace_once(text,anchor,anchor+'''
                          if(block_io)begin
                            F[Flag_Y]<=`TV80DELAY PC16[13];
                            F[Flag_X]<=`TV80DELAY PC16[11];
                            F[Flag_P]<=`TV80DELAY F[Flag_P] ^ (^repeat_parity_term);
                            if(F[Flag_C])F[Flag_H]<=`TV80DELAY
                              (repeat_count[3:0]==(repeat_data[7]?4'h0:4'hf));
                          end''')
    return text
