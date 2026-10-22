`timescale 1ns/1ps
module c_read_instructions;
 parameter LATE=0;reg late=0;
 reg clk=0,reset_n=0,wait_n=1,waited=0,reset_done=0;
 always #5 clk=~clk;
 wire [15:0] address;wire [7:0] dout;wire mreq_n,iorq_n,rd_n,wr_n,halt_n;
 reg [7:0] memory[0:65535];reg [1023:0] file;
 integer mode,reset_mode,i;integer cycles=0;
 wire [7:0] port_data=LATE?(late?8'h34:8'h12):(address[7:0]^address[15:8]^8'h5a);
 always @(posedge clk)if(LATE && reset_n && cpu.base.tstate[2] && wait_n && cpu.base.iorq && !cpu.base.write)begin #2;late=1;end
 always @(posedge iorq_n)late=0;
 wire [7:0] di=!mreq_n?memory[address]:port_data;
 tv80_io_candidate cpu(.clk(clk),.reset_n(reset_n),.wait_n(wait_n),.int_n(1'b1),.nmi_n(1'b1),.busrq_n(1'b1),.di(di),.A(address),.dout(dout),.mreq_n(mreq_n),.iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),.halt_n(halt_n));
 initial begin
  for(i=0;i<65536;i=i+1)memory[i]=0;
  if(!$value$plusargs("rom=%s",file))$fatal(1,"rom missing");
  if(!$value$plusargs("mode=%d",mode))$fatal(1,"mode missing");
  if(!$value$plusargs("reset=%d",reset_mode))$fatal(1,"reset missing");
  $readmemh(file,memory);#42;reset_n=1;
  #40000;
  $display("HALT %0d",!halt_n);
  $display("AF %0d %0d",cpu.base.i_tv80_core.ACC,cpu.base.i_tv80_core.F);
  for(i=32768;i<32800;i=i+1)$display("RAM %0d %0d",i,memory[i]);
  $finish;
 end
 always @(posedge clk)cycles<=cycles+1;
 always @(negedge iorq_n)if(reset_n&&!rd_n)begin
  if(reset_mode&&!reset_done)begin reset_done=1;#1;reset_n=0;$display("RESET %0d",cycles);#160;reset_n=1;end
  else if(mode&&!waited)begin waited=1;#1;wait_n=0;#30;wait_n=1;end
 end
 always @(negedge wr_n)if(reset_n)begin
  if(!mreq_n)begin memory[address]=dout;$display("MEM %0d %0d %0d",cycles,address,dout);end
  if(!iorq_n)$display("OUT %0d %0d %0d",cycles,address,dout);
 end
endmodule
