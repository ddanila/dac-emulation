`timescale 1ns/1ps
module bridge_probe #(parameter DIRECT_Z=0)(input vin, output drive, output echo);
 wire oc;
 // Transport drive intent explicitly; SPICE owns pullup, impedance and load.
 assign drive = DIRECT_Z ? oc : (oc === 1'bz ? 1'b0 : oc === 1'b0 ? 1'b1 : 1'bx);
 chip_7406 driver(.p1(vin), .p2(oc), .p3(1'b0), .p5(1'b0),
   .p9(1'b0), .p11(1'b0), .p13(1'b0), .p7(1'b0), .p14(1'b1));
 // Known delay exercises HDL time units independently of SPICE step size.
 assign #17 echo = vin;
endmodule
