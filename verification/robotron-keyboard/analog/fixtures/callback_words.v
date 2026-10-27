`timescale 1ns/1ps
module probe;
reg [3:0] a=0,b=15;
reg [1:0] select=0;
wire [3:0] words[0:1],aliases[0:2];
assign words[0]=a;assign words[1]=b;
assign aliases[0]=a;assign aliases[1]=a;assign aliases[2]=b;
wire [3:0] selected_word=words[select[0]],selected_alias=aliases[select];
initial begin
 #1; $word_inspect; $display("VALUE %0t %b %b",$time,selected_word,selected_alias);
 #1; a=3;b=12;select=1;
 #1; $word_inspect; $display("VALUE %0t %b %b",$time,selected_word,selected_alias);
 #1; a=5;b=10;select=2;
 #1; $word_inspect; $display("VALUE %0t %b %b",$time,selected_word,selected_alias);
 #1; a=4'b10xz;b=4'bz01x;select=0;
 #1; $word_inspect; $display("VALUE %0t %b %b",$time,selected_word,selected_alias);
 #1; $finish;
end
endmodule
