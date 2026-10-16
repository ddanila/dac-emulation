`timescale 1ns/1ps
module firmware_tb;
 reg clk=0,reset_n=0;always #5 clk=~clk;
 wire [15:0] address;wire [7:0] dout,di,read_data;wire m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n;
 reg [103:0] contacts=0;wire [1:0] leds;wire ta_daten,ta_takt;
 reg [7:0] rom[0:2047];reg [1023:0] file,wave;integer cycle=-16;
 tv80n cpu(.reset_n(reset_n),.clk(clk),.wait_n(1'b1),.int_n(1'b1),.nmi_n(1'b1),.busrq_n(1'b1),.di(di),.A(address),.dout(dout),.m1_n(m1_n),.mreq_n(mreq_n),.iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),.rfsh_n(rfsh_n),.halt_n(halt_n),.busak_n(busak_n));
 controller board(address,dout,iorq_n,wr_n,contacts,read_data,leds,ta_daten,ta_takt);
 assign di=!mreq_n?rom[address[10:0]]:read_data;
 initial begin
  if(!$value$plusargs("rom=%s",file))$fatal(1,"rom missing");$readmemh(file,rom);
  if($value$plusargs("wave=%s",wave))begin $dumpfile(wave);$dumpvars(0,firmware_tb);end
 end
 always @(negedge clk)begin
  cycle=cycle+1;
  if(cycle==0)reset_n=1;
  case(cycle)
   200000:contacts[61]=1;
   400000:contacts[61]=0;
   600000:contacts[65]=1;
   800000:contacts[61]=1;
   1000000:contacts=0;
   1200000:contacts[71]=1;
   1400000:contacts=0;
   1450000:contacts[69]=1;
   1550000:contacts=0;
   1600000:contacts[64]=1;
   1800000:contacts[61]=1;
   2000000:contacts=0;
   2200000:contacts[61]=1;
   2400000:contacts[70]=1;
   3800000:contacts[70]=0;
   4200000:begin reset_n=0;contacts=0;end
   4200016:reset_n=1;
   4400000:contacts[61]=1;
  endcase
  if(cycle>=0&&cycle%200000==199999)$display("LED %0d %0d",cycle,leds);
  if(cycle==4600000)$finish;
 end
 always @(leds) if(reset_n && cycle>=0)$display("EDGE %0d %0d",cycle,leds);
 always @(posedge ta_takt) if(reset_n)begin #1;$display("BIT %0d %0d",cycle,~ta_daten);end
endmodule
