`timescale 1ns/1ps
// Intel I8282 non-inverting latch, AFN-01413B pp. 9-92/93.
// https://tvsat.com.pl/PDF/8/8282_intel.pdf
// SHA256 761fcbe1118cc82536491fc96e9513c814159304cbc7fe7145c660afdf28e4a5
// Reference envelope at VCC 5 V +/-10%, -40..85 C, specified 300 pF load.
// Unspecified timing intervals and violated storage constraints produce X,
// not a prediction of metastability, physical pin voltage or specimen behavior.
module chip_I8282_timed(input p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p20,
 output p12,p13,p14,p15,p16,p17,p18,p19);
 wire [7:0] data={p8,p7,p6,p5,p4,p3,p2,p1}&8'hff;
 reg [7:0] stored=8'hxx,previous_data=8'hxx;
 reg previous_strobe=1'bx,closed=0;
 realtime opened_at=0,closed_at=0;
 integer bit_index;
 always @(data or p11) begin
  if(p11===1'b1) begin
   if(previous_strobe!==1'b1) opened_at=$realtime;
   stored=data;
   closed=0;
  end else if(p11===1'b0) begin
   if(previous_strobe===1'b1) begin
    // Setup minimum is zero; high pulse minimum is 15 ns.
    stored=($realtime-opened_at<15) ? 8'hxx : data;
    closed_at=$realtime;
    closed=1;
   end else if(closed && $realtime-closed_at<25) begin
    // Only changed bits lose their stored guarantee during the hold interval.
    for(bit_index=0;bit_index<8;bit_index=bit_index+1)
     if(data[bit_index]!==previous_data[bit_index]) stored[bit_index]=1'bx;
   end
  end else begin
   stored=p11 ? data : stored;
   closed=0;
  end
  previous_strobe=p11;
  previous_data=data;
 end
 integer strobe_epoch=0,strobe_ready=-1,enable_epoch=0,enable_ready=-1;
 always @(p11) begin
  strobe_epoch=strobe_epoch+1;
  strobe_ready <= #55 strobe_epoch;
 end
 always @(p9) begin
  enable_epoch=enable_epoch+1;
  enable_ready <= #50 enable_epoch;
 end
 initial begin
  #0;
  strobe_ready <= #55 strobe_epoch;
  enable_ready <= #50 enable_epoch;
 end
 wire released;
 assign #25 released=(p9===1'b1);
 wire [7:0] q;
 genvar bit_number;
 generate for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin: output_bit
  integer data_epoch=0,data_ready=-1;
  always @(stored[bit_number]) begin
   data_epoch=data_epoch+1;
   data_ready <= #35 data_epoch;
  end
  initial begin #0;data_ready <= #35 data_epoch;end
  // Conservatively wait the full reference maximum after either strobe edge.
  // No calibrated output slew, leakage, supply current or power-up model.
  assign q[bit_number]=p9===1'b1 ? (released===1'b1 ? 1'bz : 1'bx) :
      p9!==1'b0 ? 1'bx :
      (enable_epoch==enable_ready && strobe_epoch==strobe_ready && data_epoch==data_ready) ?
      stored[bit_number] : 1'bx;
 end endgenerate
 assign {p12,p13,p14,p15,p16,p17,p18,p19}=q;
endmodule
