// Source read R, data/metadata capture R+1, destination write R+2.
module dma_controller(input logic clk,rst_n,start,store,
    input logic [31:0] src,dst,len,output logic active,done,
    output logic dmem_en,dmem_we,output logic [31:0] dmem_addr,dmem_wdata,input logic [31:0] dmem_rdata,
    output logic sram_en,sram_we,output logic [31:0] sram_addr,sram_wdata,input logic [31:0] sram_rdata);
typedef enum logic [1:0] {IDLE,RUN,DRAIN} state_t;
state_t state;
logic direction,read_valid,write_valid;
logic [31:0] src_cursor,dst_cursor,remaining,response_addr,write_addr,write_data;
wire issue=state==RUN;
assign active=state!=IDLE;
assign dmem_en=direction?write_valid:issue;
assign dmem_we=direction;
assign dmem_addr=direction?write_addr:src_cursor;
assign dmem_wdata=write_data;
assign sram_en=direction?issue:write_valid;
assign sram_we=!direction;
assign sram_addr=direction?src_cursor:write_addr;
assign sram_wdata=write_data;
always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin state<=IDLE;direction<=0;read_valid<=0;write_valid<=0;done<=0;remaining<=0;end
    else begin
        done<=0;read_valid<=issue;write_valid<=read_valid;
        if(issue) begin response_addr<=dst_cursor;src_cursor<=src_cursor+4;dst_cursor<=dst_cursor+4;remaining<=remaining-1'b1;end
        if(read_valid) begin write_data<=direction?sram_rdata:dmem_rdata;write_addr<=response_addr;end
        case(state)
            IDLE:if(start) begin state<=RUN;direction<=store;src_cursor<=src;dst_cursor<=dst;remaining<=len>>2;end
            RUN:if(remaining==1) state<=DRAIN;
            DRAIN:if(write_valid && !read_valid) begin state<=IDLE;done<=1;end
            default:begin end
        endcase
    end
end
endmodule
