`timescale 1ns/1ps

module probe;
 reg clk=0, reset_n=0, late=0;
 reg [7:0] ram_byte=1;
 wire [15:0] address;
 wire [7:0] dout, di;
 wire m1_n,mreq_n,iorq_n,rd_n,wr_n,rfsh_n,halt_n,busak_n;
 // LD IX,0010; DD CB 00 86/C6; LD A,(IX+0); OUT (80),A; HALT.
 // The late opcode selects SET 0 instead of RES 0.
 assign di=address==0 ? 8'hdd : address==1 ? 8'h21 :
           address==2 ? 8'h10 : address==3 ? 8'h00 :
           address==4 ? 8'hdd : address==5 ? 8'hcb :
           address==6 ? 8'h00 : address==7 ? (late ? 8'hc6 : 8'h86) :
           address==8 ? 8'hdd : address==9 ? 8'h7e : address==10 ? 8'h00 :
           address==11 ? 8'hd3 : address==12 ? 8'h80 :
           address==16 ? ram_byte : 8'h76;
 tv80n cpu(.clk(clk),.reset_n(reset_n),.wait_n(1'b1),.int_n(1'b1),.nmi_n(1'b1),
 .busrq_n(1'b1),.di(di),.A(address),.dout(dout),.m1_n(m1_n),.mreq_n(mreq_n),
 .iorq_n(iorq_n),.rd_n(rd_n),.wr_n(wr_n),.rfsh_n(rfsh_n),.halt_n(halt_n),.busak_n(busak_n));
 always #500 clk=~clk;
 initial begin #2200 reset_n=1; #200000 $fatal(1,"No output"); end
 always @(posedge clk) if(reset_n && cpu.tstate[2] && !cpu.mcycle[0] &&
                            !mreq_n && !rd_n && address==7) begin
   $display("OPERAND_RISE %0t %02x",$time,di);
   #100; late=1;
   $display("OPERAND_CHANGE %0t",$time);
 end
 always @(negedge clk) if(reset_n && late && !mreq_n && !rd_n && address==7)
   $display("OPERAND_FALL %0t %02x %02x",$time,di,cpu.i_tv80_core.IR);
 always @(negedge wr_n) if(reset_n) begin
   if(!mreq_n && address==16) begin
     ram_byte=dout;
     $display("MEMORY_WRITE %0t %04x %02x",$time,address,dout);
   end
   if(!iorq_n) begin
     $display("OUTPUT %0t %04x %02x",$time,address,dout);
     if(dout!==8'h00)$fatal(1,"Expected current core to execute earlier RES opcode");
     $display("READ_PHASE_DIAGNOSTIC_PASS");$finish;
   end
 end
endmodule
