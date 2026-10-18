`timescale 1ns/1ps

module probe;
 reg clk=0, reset_n=0, late=0, wait_n=1, waited=0;
 wire [15:0] address;
 wire [7:0] dout, di;
 wire m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n;
 assign di=!iorq_n ? (late ? 8'h34 : 8'h12) : address==0 ? 8'hdb : address==1 ? 8'h80 :
           address==2 ? 8'hd3 : address==3 ? 8'h80 : 8'h76;
 tv80n cpu(.clk(clk),.reset_n(reset_n),.wait_n(wait_n),.int_n(1'b1),.nmi_n(1'b1),
 .busrq_n(1'b1),.di(di),.A(address),.dout(dout),.m1_n(m1_n),.mreq_n(mreq_n),
 .iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),.rfsh_n(rfsh_n),.halt_n(halt_n),.busak_n(busak_n));
 always @(negedge iorq_n) if(reset_n && !rd_n && !waited) begin
   waited=1;wait_n=0;$display("WAIT_ASSERT %0t",$time);
   #4000;wait_n=1;$display("WAIT_RELEASE %0t",$time);
 end
 always #500 clk=~clk;
 initial begin #2200 reset_n=1; #50000 $fatal(1,"No output"); end
 always @(posedge clk) if(reset_n && cpu.wait_n && cpu.i_tv80_core.Auto_Wait_t1 && cpu.tstate[2] && !cpu.mcycle[0] &&
                            !iorq_n && !rd_n) begin
   $display("OPERAND_RISE %0t %02x",$time,di);
   #100; late=1;
   $display("OPERAND_CHANGE %0t",$time);
 end
 always @(negedge clk) if(reset_n && late && !iorq_n && !rd_n)
   $display("OPERAND_FALL %0t %02x %02x",$time,di,cpu.di_reg);
 always @(negedge wr_n) if(reset_n && !iorq_n) begin
   $display("OUTPUT %0t %04x %02x",$time,address,dout);
   if(dout!==8'h34)$fatal(1,"Expected TV80 rising-edge operand");
   $display("READ_PHASE_DIAGNOSTIC_PASS");$finish;
 end
endmodule
