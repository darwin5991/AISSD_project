// One CSR-configured M=1 GEMM. No layer LUT or automatic ARGMAX.
module gemm_controller(
    input logic clk,rst_n,start,
    input logic [31:0] config_words [0:9],
    output logic [7:0] config_error,
    output logic active,done,fault,execute_enable,
    output logic [7:0] error_code,
    output logic [6:0] ram_en,ram_we,
    output logic [14:0] ram_address [0:6],
    output logic mac_input_valid,bias_load,result_load,
    output logic signed [5:0] bias_shift,
    output logic [4:0] output_shift,
    output logic relu_en,source_buffer,destination_buffer
);
    import npu_isa_pkg::*;
    import npu_memory_pkg::*;
    typedef enum logic [2:0] {IDLE,PREP,RUN,DRAIN,COMPLETE,FAILED} state_t;
    state_t state;
    logic [7:0] input_word,input_words,output_groups;
    logic [6:0] output_group,write_group;
    logic read_issue,bias_read,first_read,last_input,last_read,next_bias;
    logic valid_d1,first_bias_d1,result_d5,next_bias_d5,write_d6,last_d6;
    logic [7:0] runtime_error;
    logic [6:0] request_en,request_we;
    logic [63:0] address_full [0:6];
    logic [63:0] groups_full,weight_bytes;
    logic bad_region,bad_bounds;
    logic [63:0] input_end,output_end,weight_end,bias_end;
    assign groups_full=({32'd0,config_words[5]}+64'd3)>>2;
    assign weight_bytes={32'd0,config_words[6]}*groups_full;
    assign input_end={32'd0,config_words[0]}+{32'd0,config_words[6]};
    assign output_end={32'd0,config_words[2]}+(groups_full<<2);
    assign weight_end={32'd0,config_words[1]}+weight_bytes;
    assign bias_end={32'd0,config_words[3]}+(groups_full<<2);
    assign bad_region=!(sram_region(config_words[0]) && config_words[0][19:17]<=1 &&
        sram_region(config_words[2]) && config_words[2][19:17]<=1 &&
        sram_region(config_words[1]) && config_words[1][19:17]==2 &&
        sram_region(config_words[3]) && config_words[3][19:17]==6);
    always_comb begin
        bad_bounds=0;
        if(!bad_region) begin
            bad_bounds=({32'd0,config_words[0]} >= {32'd0,bank_base(config_words[0][19:17])}+bank_depth(config_words[0][19:17])*4) ||
                ({32'd0,config_words[2]} >= {32'd0,bank_base(config_words[2][19:17])}+bank_depth(config_words[2][19:17])*4) ||
                ({32'd0,config_words[1]} >= 64'h80040000+29280*4) ||
                ({32'd0,config_words[3]} >= 64'h800c0000+163*4) ||
                (input_end > {32'd0,bank_base(config_words[0][19:17])}+bank_depth(config_words[0][19:17])*4) ||
                (output_end > {32'd0,bank_base(config_words[2][19:17])}+bank_depth(config_words[2][19:17])*4) ||
                (weight_end > 64'h80040000+29280*4) || (bias_end > 64'h800c0000+163*4);
        end
        config_error=ERR_OK;
        if(config_words[0][1:0]!=0 || config_words[1][1:0]!=0 ||
           config_words[2][1:0]!=0 || config_words[3][1:0]!=0)
            config_error=ERR_MISALIGNED;
        else if(bad_region) config_error=ERR_INVALID_REGION;
        else if(bad_bounds) config_error=ERR_MEMORY_BOUNDS;
        else if(config_words[4]!=1 || config_words[5]==0 || config_words[5]>512 ||
            config_words[6]<8 || config_words[6][1:0]!=0 ||
            $signed(config_words[7]) < -32 || $signed(config_words[7]) > 31 ||
            config_words[8]>31 || config_words[9]>1 ||
            config_words[0][19:17]==config_words[2][19:17])
            config_error=ERR_INVALID_CONFIG;
    end
    // These slices are consumed only after full raw-value validation.
    assign input_words=config_words[6][9:2];
    assign output_groups=groups_full[7:0];
    assign source_buffer=config_words[0][17];
    assign destination_buffer=config_words[2][17];
    assign bias_shift=config_words[7][5:0];
    assign output_shift=config_words[8][4:0];
    assign relu_en=config_words[9][0];
    assign active=(state==PREP)||(state==RUN)||(state==DRAIN);
    assign execute_enable=active && runtime_error==ERR_OK;
    assign done=(state==COMPLETE);
    assign fault=(state==FAILED);
    assign read_issue=(state==RUN)&&(input_word<input_words)&&({1'b0,output_group}<output_groups);
    assign bias_read=read_issue && input_word==0;
    assign first_read=bias_read && output_group==0;
    assign last_input=read_issue && input_word==input_words-1'b1;
    assign last_read=last_input && {1'b0,output_group}==output_groups-1'b1;
    assign next_bias=last_input && !last_read;
    delay_line #(.WIDTH(1),.DEPTH(1)) u_valid(.clk(clk),.rst_n(rst_n),.data_in(read_issue),.data_out(valid_d1));
    delay_line #(.WIDTH(1),.DEPTH(1)) u_first(.clk(clk),.rst_n(rst_n),.data_in(first_read),.data_out(first_bias_d1));
    delay_line #(.WIDTH(1),.DEPTH(5)) u_result(.clk(clk),.rst_n(rst_n),.data_in(last_input),.data_out(result_d5));
    delay_line #(.WIDTH(1),.DEPTH(5)) u_bias(.clk(clk),.rst_n(rst_n),.data_in(next_bias),.data_out(next_bias_d5));
    delay_line #(.WIDTH(1),.DEPTH(6)) u_write(.clk(clk),.rst_n(rst_n),.data_in(last_input),.data_out(write_d6));
    delay_line #(.WIDTH(7),.DEPTH(6)) u_group(.clk(clk),.rst_n(rst_n),.data_in(output_group),.data_out(write_group));
    delay_line #(.WIDTH(1),.DEPTH(6)) u_last(.clk(clk),.rst_n(rst_n),.data_in(last_read),.data_out(last_d6));
    always_comb begin
        request_en=0;request_we=0;
        for(integer b=0;b<7;b++) address_full[b]=0;
        if(read_issue) begin
            request_en[source_buffer]=1;
            address_full[source_buffer]=(({32'd0,config_words[0]}-{32'd0,bank_base(config_words[0][19:17])})>>2)+input_word;
            for(integer b=2;b<6;b++) begin
                request_en[b]=1;
                address_full[b]=(({32'd0,config_words[1]}-64'h80040000)>>2)+
                    {57'd0,output_group}*{56'd0,input_words}+input_word;
            end
        end
        if(bias_read) begin
            request_en[6]=1;
            address_full[6]=(({32'd0,config_words[3]}-64'h800c0000)>>2)+output_group;
        end
        if(active && write_d6) begin
            request_en[destination_buffer]=1;request_we[destination_buffer]=1;
            address_full[destination_buffer]=(({32'd0,config_words[2]}-{32'd0,bank_base(config_words[2][19:17])})>>2)+write_group;
        end
        runtime_error=ERR_OK;
        if(state==RUN && (input_word>input_words || {1'b0,output_group}>=output_groups))
            runtime_error=ERR_MEMORY_BOUNDS;
        for(integer b=0;b<7;b++)
            if(request_en[b] && address_full[b]>=bank_depth(b)) runtime_error=ERR_MEMORY_BOUNDS;
        ram_en=0;ram_we=0;
        for(integer b=0;b<7;b++) begin
            ram_address[b]=address_full[b][14:0];
            if(rst_n && active && runtime_error==ERR_OK) begin
                ram_en[b]=request_en[b];ram_we[b]=request_we[b];
            end
        end
    end
    assign mac_input_valid=active && runtime_error==ERR_OK && valid_d1;
    assign bias_load=active && runtime_error==ERR_OK && (first_bias_d1 || next_bias_d5);
    assign result_load=active && runtime_error==ERR_OK && result_d5;
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin state<=IDLE;input_word<=0;output_group<=0;error_code<=ERR_OK;end
        else begin
            case(state)
                IDLE: if(start) begin
                    input_word<=0;output_group<=0;error_code<=config_error;
                    if(config_error!=ERR_OK) state<=FAILED;
                    else state<=PREP;
                end
                PREP: state<=RUN;
                RUN,DRAIN: begin
                    if(runtime_error!=ERR_OK) begin state<=FAILED;error_code<=runtime_error;end
                    else if(state==RUN) begin
                        if(last_read) state<=DRAIN;
                        if(read_issue) input_word<=input_word+1'b1;
                        else if(input_word==input_words) begin input_word<=0;output_group<=output_group+1'b1;end
                    end else if(last_d6) state<=COMPLETE;
                end
                COMPLETE: state<=IDLE;
                FAILED: begin end
                default: begin state<=FAILED;error_code<=ERR_ILLEGAL_ENCODING;end
            endcase
        end
    end
endmodule
