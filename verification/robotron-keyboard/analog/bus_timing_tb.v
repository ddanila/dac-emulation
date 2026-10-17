`timescale 1ns/1ps
module bus_timing_tb;
 reg clk=0,reset_n=0;
 always #5 clk=~clk;
 boot_cosim #(.EXPLICIT_CPU_DRIVE(1)) dut(.clk(clk),.reset_n(reset_n),.sense(8'b0));
 boot_cosim #(.EXPLICIT_CPU_DRIVE(0)) old(.clk(clk),.reset_n(reset_n),.sense(8'b0));
 realtime last_new=0,last_old=0,edge_time;
 integer writes=0,mem_writes=0,io_writes=0,old_setup_failures=0;
 reg held_bit;
 always @(dut.electrical.board.n_D0) last_new=$realtime;
 always @(old.digital.board.n_D0) last_old=$realtime;
 always @(negedge dut.wr_n) if(reset_n) begin
  edge_time=$realtime;
  #0.001;
  if(dut.cpu_data_drive!==1 || dut.electrical.board.n_D0!==dut.dout[0])
   $fatal(1,"write data absent or contended at WR");
  if(edge_time-last_new < 4.999)
   $fatal(1,"new data setup shorter than half a test clock: %f ns",edge_time-last_new);
  if(edge_time-last_old < 0.01) old_setup_failures=old_setup_failures+1;
  if(old.dout!==dut.dout || old.wr_n!==dut.wr_n)
   $fatal(1,"diagnostic control changed CPU execution");
  writes=writes+1;
  if(!dut.mreq_n) mem_writes=mem_writes+1;
  if(!dut.iorq_n) io_writes=io_writes+1;
  $display("SETUP %0d %b %b %02x %f %f",writes,dut.mreq_n,dut.iorq_n,dut.dout,edge_time-last_new,edge_time-last_old);
 end
 always @(posedge dut.wr_n) if(reset_n && writes>0) begin
  held_bit=dut.electrical.board.n_D0;
  #4.999;
  if(dut.cpu_data_drive!==1 || dut.electrical.board.n_D0!==held_bit)
   $fatal(1,"write data not held for half a test clock after WR");
 end
 initial begin
  #40;reset_n=1;
  #5000;
  if(mem_writes<4 || io_writes<4 || old_setup_failures<4)
   $fatal(1,"insufficient memory/I/O write or negative-control coverage");
  $display("BUS_TIMING_PASS %0d %0d %0d",mem_writes,io_writes,old_setup_failures);
  $finish;
 end
endmodule
