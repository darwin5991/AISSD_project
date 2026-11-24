module register_file(input logic clk,rst_n,we,input logic [2:0] wa,ra,rb,rc,
    input logic [31:0] wd,output logic [31:0] a,b,c);
logic [31:0] r[1:7];
assign a=ra==0?32'b0:r[ra];
assign b=rb==0?32'b0:r[rb];
assign c=rc==0?32'b0:r[rc];
always_ff @(posedge clk or negedge rst_n)
    if(!rst_n) begin for(integer i=1;i<8;i=i+1) r[i]<=0; end
    else if(we && wa!=0) r[wa]<=wd;
endmodule
