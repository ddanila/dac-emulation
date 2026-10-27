`timescale 1ns/1ps
module probe;
reg gate=0;
integer index=0;
reg [15:0] bus=16'habcd;
real result;
reg [79:0] wideout;
string textout;
function automatic [79:0] widefn(input [79:0] x);
 begin $thread_observe; widefn=x; end
endfunction
function automatic string textfn(input string x);
 begin $thread_observe; textfn=x; end
endfunction
function automatic real calculate(input real x,input string text,input [79:0] wide);
 begin $thread_observe; calculate=x+text.len()+wide[7:0]; end
endfunction
initial begin
 #1; $thread_observe;
 for(index=0;index<3;index=index+1) begin
  #1;
  $display("STEP %0t %0d %b",$time,index,bus[index]);
  if ((index<2) && (bus[index] !== 1'bx)) $display("BRANCH %0d",index);
  bus[index]=~bus[index];
  $thread_observe;
 end
 result=calculate(1.25,"hello",80'h123456789abcdef01234);
 $display("RESULT %0t %.2f",$time,result);
 wideout=80'hfedcba9876543210fedc ^ widefn(80'h0123456789abcdef0123);
 textout={"kept",textfn("arg")};
 $display("VALUES %h %s",wideout,textout);
 gate=1;
 #1; $thread_observe;
 fork
  begin #1; $display("CHILD_A %0t",$time); end
  begin #2; $display("CHILD_B %0t",$time); end
 join
 $thread_observe;
 #1; $finish;
end
initial begin
 @(posedge gate);
 $display("WAKE %0t",$time);
 #1; $thread_observe;
end
endmodule
