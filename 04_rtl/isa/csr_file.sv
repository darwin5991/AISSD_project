module csr_file(input logic clk,rst_n,we,input logic [11:0] waddr,raddr,
    input logic [31:0] wdata,count,input logic halted,overflow,
    output logic [31:0] rdata,src0,src1,dst,bias,arg_src,
    output logic [20:0] dim,output logic [11:0] cfg,output logic [3:0] arg_len);
always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin src0<=0;src1<=0;dst<=0;bias<=0;dim<=0;cfg<=0;arg_src<=0;arg_len<=0;end
    else if(we) case(waddr)
        12'h7c0:src0<=wdata;12'h7c1:src1<=wdata;12'h7c2:dst<=wdata;12'h7c3:bias<=wdata;
        12'h7c4:dim<=wdata[20:0];12'h7c7:cfg<=wdata[11:0];12'h7e0:arg_src<=wdata;12'h7e1:arg_len<=wdata[3:0];
        default:begin end
    endcase
end
always_comb case(raddr)
    12'h7c0:rdata=src0;12'h7c1:rdata=src1;12'h7c2:rdata=dst;12'h7c3:rdata=bias;
    12'h7c4:rdata={11'b0,dim};12'h7c7:rdata={20'b0,cfg};12'h7e0:rdata=arg_src;12'h7e1:rdata={28'b0,arg_len};
    12'h7f0:rdata=count;12'h7f2:rdata={30'b0,overflow,halted};default:rdata=0;
endcase
endmodule
