// Serial fixed-latency transfer: request R, capture R+1, write R+2.
module block_transfer #(
    parameter logic [32:0] DMEM_BYTES=npu_isa_pkg::DEFAULT_DMEM_BYTES
) (
    input logic clk,rst_n,start,is_store,
    input logic [31:0] source_address,destination_address,length_bytes,
    output logic busy,done,fault,load_active,
    output logic [7:0] error_code,
    output logic dmem_en,dmem_we,
    output logic [31:0] dmem_addr,dmem_wdata,
    input logic [31:0] dmem_rdata,
    output logic sram_en,sram_we,
    output logic [31:0] sram_address,sram_wdata,
    input logic [31:0] sram_rdata,
    input logic [7:0] sram_error
);
    import npu_isa_pkg::*;
    import npu_memory_pkg::*;
    typedef enum logic [2:0] {IDLE,READ_REQ,READ_WAIT,WRITE_REQ,COMPLETE,FAILED} transfer_state_t;
    transfer_state_t state;
    logic store_mode;
    logic [31:0] src_cursor,dst_cursor,remaining,data_buffer;
    logic [7:0] start_error,current_error;
    assign start_error=transfer_error(source_address,destination_address,length_bytes,is_store,DMEM_BYTES);
    assign busy=(state==READ_REQ)||(state==READ_WAIT)||(state==WRITE_REQ);
    assign done=(state==COMPLETE);
    assign fault=(state==FAILED);
    assign load_active=busy && !store_mode;
    assign current_error=(remaining==0)?ERR_INVALID_CONFIG:
        transfer_error(src_cursor,dst_cursor,32'd4,store_mode,DMEM_BYTES);
    assign dmem_en=rst_n && busy && current_error==ERR_OK &&
        ((!store_mode && state==READ_REQ)||(store_mode && state==WRITE_REQ));
    assign dmem_we=store_mode && state==WRITE_REQ;
    assign dmem_addr=store_mode?dst_cursor:src_cursor;
    assign dmem_wdata=data_buffer;
    assign sram_en=rst_n && busy && current_error==ERR_OK &&
        ((store_mode && state==READ_REQ)||(!store_mode && state==WRITE_REQ));
    assign sram_we=!store_mode && state==WRITE_REQ;
    assign sram_address=store_mode?src_cursor:dst_cursor;
    assign sram_wdata=data_buffer;
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;store_mode<=0;src_cursor<=0;dst_cursor<=0;
            remaining<=0;data_buffer<=0;error_code<=ERR_OK;
        end else begin
            case(state)
                IDLE: if(start) begin
                    store_mode<=is_store;src_cursor<=source_address;
                    dst_cursor<=destination_address;remaining<=length_bytes;
                    error_code<=start_error;
                    if(start_error!=ERR_OK) state<=FAILED;
                    else state<=READ_REQ;
                end
                READ_REQ,READ_WAIT,WRITE_REQ: begin
                    if(current_error!=ERR_OK || sram_error!=ERR_OK) begin
                        error_code<=(current_error!=ERR_OK)?current_error:sram_error;
                        state<=FAILED;
                    end else case(state)
                        READ_REQ: state<=READ_WAIT;
                        READ_WAIT: begin
                            data_buffer<=store_mode?sram_rdata:dmem_rdata;
                            state<=WRITE_REQ;
                        end
                        WRITE_REQ: begin
                            if(remaining==4) state<=COMPLETE;
                            else begin
                                remaining<=remaining-4;
                                src_cursor<=src_cursor+4;dst_cursor<=dst_cursor+4;
                                state<=READ_REQ;
                            end
                        end
                        default: begin end
                    endcase
                end
                COMPLETE: state<=IDLE;
                FAILED: begin end
                default: begin state<=FAILED;error_code<=ERR_ILLEGAL_ENCODING;end
            endcase
        end
    end
endmodule
