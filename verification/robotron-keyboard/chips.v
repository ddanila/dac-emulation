// Digital models of the numbered pins used by the Zander reference circuit.
// Open collectors release to Z; external pullups establish high levels.
// Analog oscillator/reset/sense stages are explicit testbench boundaries.
module chip_7406(input p1,p3,p5,p9,p11,p13,p7,p14,
 output p2,p4,p6,p8,p10,p12);
 assign p2=p1?1'b0:1'bz, p4=p3?1'b0:1'bz, p6=p5?1'b0:1'bz,
        p8=p9?1'b0:1'bz,p10=p11?1'b0:1'bz,p12=p13?1'b0:1'bz;
endmodule
module chip_DL003(input p1,p2,p4,p5,p9,p10,p12,p13,p7,p14,
 output p3,p6,p8,p11);
 assign p3=(p1&p2)?1'b0:1'bz,p6=(p4&p5)?1'b0:1'bz,
        p8=(p9&p10)?1'b0:1'bz,p11=(p12&p13)?1'b0:1'bz;
endmodule
// LS74 logical truth table: TI SDLS119, function table (page 1).
// Both asynchronous inputs asserted force Q/Qn high; their simultaneous
// release does not select a deterministic stored state. No timing model.
module dl074_state(output reg q, input preset_n, clear_n, d, clk);
 reg previous_clk;
 // Observe both control pins together, including release. A UDP can resolve
 // simultaneous releases in simulator-dependent pin-event order.
 always @(preset_n or clear_n or clk) begin
  case ({preset_n,clear_n})
   2'b00: q<=1'bx;
   2'b01: q<=1'b1;
   2'b10: q<=1'b0;
   2'b11: begin
    if(previous_clk===1'b0 && clk===1'b1) q<=(d===1'b0)?1'b0:(d===1'b1)?1'b1:1'bx;
    else if(clk!==1'b0 && clk!==previous_clk) q<=1'bx;
   end
   default: q<=1'bx;
  endcase
  previous_clk=clk;
 end
endmodule
module chip_DL074(input p1,p2,p3,p4,p10,p11,p12,p13,p7,p14,
 output p5,p9,p6,p8);
 wire q1,q2;
 dl074_state first(q1,p4,p1,p2,p3);
 dl074_state second(q2,p10,p13,p12,p11);
 assign p5=(p4===1'b0 && p1===1'b0)?1'b1:q1,
        p6=(p4===1'b0 && p1===1'b0)?1'b1:~q1,
        p9=(p10===1'b0 && p13===1'b0)?1'b1:q2,
        p8=(p10===1'b0 && p13===1'b0)?1'b1:~q2;
endmodule
module chip_I8282(input p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p20,
 output p12,p13,p14,p15,p16,p17,p18,p19);
 reg [7:0] latch;
 // Unresolved input voltage is not a high-impedance state of stored data.
 wire [7:0] inputs_known={p8,p7,p6,p5,p4,p3,p2,p1} & 8'hff;
 // Unknown STB may mean hold or transparency. Merge those possibilities
 // bitwise instead of silently treating an unknown control as inactive.
 always @* if(p11!==1'b0) latch=p11?inputs_known:latch;
 assign {p12,p13,p14,p15,p16,p17,p18,p19}=p9?8'bz:latch;
endmodule
