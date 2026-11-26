// Legacy word_loaded scheduling and signed strict-first-max datapath.
module argmax_engine(input logic clk,rst_n,start,input logic [31:0] src,input logic [3:0] len,
    output logic done,output logic [3:0] result,output logic bank,read_en,
    output logic [7:0] addr,input logic [31:0] rdata);
logic active,word_loaded;
logic [3:0] index,length;
logic [7:0] base;
wire compare=active && word_loaded;
assign read_en=active && !word_loaded;
assign addr=base+{6'b0,index[3:2]};
argmax_unit u_argmax(.clk(clk),.rst_n(rst_n),.word_data(rdata),.class_index(index),
    .initialize(compare && index==0),.compare_en(compare && index!=0),.prediction(result));
always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin active<=0;word_loaded<=0;index<=0;length<=0;done<=0;bank<=0;base<=0;end
    else begin
        done<=0;
        if(!active) begin
            if(start) begin active<=1;word_loaded<=0;index<=0;length<=len;base<=src[9:2];bank<=src[17];end
        end else if(read_en) word_loaded<=1;
        else if(compare) begin
            if(index==length-1'b1) begin active<=0;word_loaded<=0;done<=1;end
            else begin index<=index+1'b1;if(index[1:0]==3) word_loaded<=0;end
        end
    end
end
endmodule
