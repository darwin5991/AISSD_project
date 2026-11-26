// Seven independent single-port bank muxes. Response selection follows request.
module npu_memory_wrapper(input logic clk,rst_n,input logic [1:0] owner,
    input logic dma_en,dma_we,input logic [31:0] dma_addr,dma_wdata,output logic [31:0] dma_rdata,
    input logic buf_sel,in_en,out_we,input logic [7:0] in_addr,out_addr,input logic [31:0] out_data,
    output logic [31:0] in_data,
    input logic weight_en,input logic [14:0] weight_addr,output logic [31:0] weight_data[0:3],
    input logic bias_en,input logic [7:0] bias_addr,output logic [31:0] bias_data,
    input logic arg_bank,arg_en,input logic [7:0] arg_addr,output logic [31:0] arg_data);
logic [6:0] en,we;
logic [14:0] addr[0:6];
logic [31:0] wdata[0:6],rdata[0:6];
logic [2:0] dma_bank;
always_ff @(posedge clk or negedge rst_n)
    if(!rst_n) dma_bank<=0;
    else if(owner==1 && dma_en && !dma_we) dma_bank<=dma_addr[19:17];
assign dma_rdata=rdata[dma_bank];
assign in_data=buf_sel?rdata[1]:rdata[0];
assign arg_data=arg_bank?rdata[1]:rdata[0];
assign bias_data=rdata[6];
for(genvar j=0;j<4;j=j+1) assign weight_data[j]=rdata[j+2];
always_comb begin
    en=0;we=0;
    for(integer j=0;j<7;j=j+1) begin addr[j]=0;wdata[j]=0;end
    case(owner)
        1:begin
            for(integer j=0;j<7;j=j+1) if(dma_addr[19:17]==j) begin
                en[j]=dma_en;we[j]=dma_we;addr[j]=dma_addr[16:2];wdata[j]=dma_wdata;
            end
        end
        2:begin
            en[0]=buf_sel?out_we:in_en;we[0]=buf_sel && out_we;
            en[1]=buf_sel?in_en:out_we;we[1]=!buf_sel && out_we;
            addr[0]={7'b0,buf_sel?out_addr:in_addr};addr[1]={7'b0,buf_sel?in_addr:out_addr};
            wdata[0]=out_data;wdata[1]=out_data;
            for(integer j=2;j<6;j=j+1) begin en[j]=weight_en;addr[j]=weight_addr;end
            en[6]=bias_en;addr[6]={7'b0,bias_addr};
        end
        3:begin en[0]=arg_en && !arg_bank;en[1]=arg_en && arg_bank;addr[0]={7'b0,arg_addr};addr[1]={7'b0,arg_addr};end
        default:begin end
    endcase
end
single_port_bram #(.DEPTH(196),.ADDR_WIDTH(8)) u_a(clk,rst_n,en[0],we[0],addr[0][7:0],wdata[0],rdata[0]);
single_port_bram #(.DEPTH(128),.ADDR_WIDTH(7)) u_b(clk,rst_n,en[1],we[1],addr[1][6:0],wdata[1],rdata[1]);
for(genvar j=2;j<6;j=j+1) begin:g_w
    single_port_bram #(.DEPTH(29280),.ADDR_WIDTH(15),.RAM_DECOMP("area")) u_w(clk,rst_n,en[j],we[j],addr[j],wdata[j],rdata[j]);
end
single_port_bram #(.DEPTH(163),.ADDR_WIDTH(8)) u_bias(clk,rst_n,en[6],we[6],addr[6][7:0],wdata[6],rdata[6]);
endmodule
