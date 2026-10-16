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
module chip_DL074(input p1,p2,p3,p4,p10,p11,p12,p13,p7,p14,
 output reg p5,p9,output p6,p8);
 always @(posedge p3 or negedge p1 or negedge p4)
  if(!p1) p5<=0; else if(!p4) p5<=1; else p5<=p2;
 always @(posedge p11 or negedge p13 or negedge p10)
  if(!p13) p9<=0; else if(!p10) p9<=1; else p9<=p12;
 assign p6=~p5,p8=~p9;
endmodule
module chip_I8282(input p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p20,
 output p12,p13,p14,p15,p16,p17,p18,p19);
 reg [7:0] latch;
 always @* if(p11) latch={p8,p7,p6,p5,p4,p3,p2,p1};
 assign {p12,p13,p14,p15,p16,p17,p18,p19}=p9?8'bz:latch;
endmodule
