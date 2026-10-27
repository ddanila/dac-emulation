`timescale 1ns/1ps
module probe;
reg [3:0] a=0,keep=0;
reg [3:0] mem[0:1];
initial begin
 mem[0]=0;mem[1]=0;
 #1; $family_setup(`FAMILY_OBJECT);
 #1; $family_late;
 #1; a=1;mem[0]=1;keep=1; $family_inspect;
 #1; a=3;mem[0]=3;mem[1]=2;keep=2; $family_inspect;
 #1; a=11;mem[0]=11;keep=3; $family_inspect;
 #1; a=7;mem[0]=7;mem[1]=4;keep=4; $family_inspect;
 #1; $family_cancel;
 #1; a=5;mem[0]=5;keep=5; #0; $family_retired;
 #1; $finish;
end
endmodule
