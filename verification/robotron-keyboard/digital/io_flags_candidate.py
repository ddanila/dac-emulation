#!/usr/bin/env python3
"""Isolated TV80 Z80 I/O flags; never modifies the vendored core.

Normal-completion rules: Sean Young, The Undocumented Z80 Documented v0.9,
sections 4.3 and 8.11. Interrupted repeat flags require separate qualification.
"""

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('TV80 template changed: ' + old[:70])
    return text.replace(old, new)


def generate(text):
    text = replace_once(text, '                  F[Flag_S] <= `TV80DELAY DI_Reg[7];',
        '''                  F[Flag_X] <= `TV80DELAY DI_Reg[3];
                  F[Flag_Y] <= `TV80DELAY DI_Reg[5];
                  F[Flag_S] <= `TV80DELAY DI_Reg[7];''')
    text = replace_once(text, '  wire           I_INRC;', '''  wire           I_INRC;
  wire block_io = ISet == 2'b10 && (IR & 8'he6) == 8'ha2;
  reg [7:0] block_data, block_b, block_term;
  wire [7:0] block_c_adjusted = A[7:0] + (IR[3] ? 8'hff : 8'h01);
  wire [7:0] block_l_adjusted = A[7:0] + (IR[3] ? 8'hff : 8'h01);
  wire [7:0] block_value = IR[0] ? dout : block_data;
  wire [7:0] block_count = IR[0] ? A[15:8] : block_b;
  wire [8:0] block_sum = {1'b0, block_value} + {1'b0, block_term};
  wire [7:0] block_parity = {5'b0, block_sum[2:0]} ^ block_count;
  always @(posedge clk or negedge reset_n)
    if (!reset_n) begin
      block_data <= 0; block_b <= 0; block_term <= 0;
    end else if (ClkEn && block_io && mcycle[1] && T_Res) begin
      block_data <= DI_Reg;
      block_b <= A[15:8] - 8'd1;
      block_term <= IR[0] ? block_l_adjusted : block_c_adjusted;
    end''')
    anchor = '              if (tstate[1] && I_BT == 1\'b1 )'
    text = replace_once(text, anchor, '''              // Only normal-completion flags; repeat-interrupt quirks are separate.
              if (block_io && mcycle[2] && T_Res) begin
                F <= `TV80DELAY {block_count[7], block_count == 0,
                  block_count[5], block_sum[8], block_count[3],
                  ~(^block_parity), block_value[7], block_sum[8]};
              end

''' + anchor)
    return text
