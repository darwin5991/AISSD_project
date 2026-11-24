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
    import control_state_pkg::*;
    // This is the Legacy execution-state type, not a coincident numeric encoding.
    control_state_t state;
    logic [7:0] input_word,input_words,output_groups;
    logic [6:0] output_group,write_group;
    logic [7:0] input_base_word,output_base_word,bias_base_word;
    logic [14:0] weight_cursor;
    logic [32:0] groups_from_snapshot;
    logic read_issue,bias_read,write_d6,prep_done,last_read,layer_stored;
    logic input_clear,input_advance,group_clear,group_advance;
    assign groups_from_snapshot=({1'b0,config_words[5]}+33'd3)>>2;
    // Software validates the complete raw Snapshot before generating EXEC GEMM.
    // Unsupported configurations have no hardware execution/fault guarantee.
    assign config_error=ERR_OK;
    assign error_code=ERR_OK;
    assign fault=1'b0;
    assign active=(state==PREP)||(state==RUN)||(state==DRAIN);
    assign execute_enable=active;
    counter_en #(.WIDTH(8)) u_input_counter(
        .clk(clk),.rst_n(rst_n),.clear(input_clear),.advance(input_advance),.value(input_word));
    counter_en #(.WIDTH(7)) u_group_counter(
        .clk(clk),.rst_n(rst_n),.clear(group_clear),.advance(group_advance),.value(output_group));
    pipeline_control u_pipeline(
        .clk(clk),.rst_n(rst_n),.start(start),.state(state),.layer_index(2'd0),
        .input_words(input_words),.output_groups(output_groups),
        .input_word(input_word),.output_group(output_group),
        .read_en(read_issue),.bias_read(bias_read),.mac_input_valid(mac_input_valid),
        .bias_load(bias_load),.result_load(result_load),.out_we(write_d6),.out_addr(write_group),
        .prep_done(prep_done),.last_read(last_read),.layer_stored(layer_stored),
        .layer_clear(),.layer_advance(),.input_clear(input_clear),.input_advance(input_advance),
        .group_clear(group_clear),.group_advance(group_advance));
    always_comb begin
        ram_en='0;ram_we='0;
        for(integer b=0;b<7;b++) ram_address[b]='0;
        if(rst_n && active) begin
            if(read_issue) begin
                ram_en[source_buffer]=1'b1;
                ram_address[source_buffer]={7'd0,input_base_word}+{7'd0,input_word};
                for(integer b=2;b<6;b++) begin
                    ram_en[b]=1'b1;
                    ram_address[b]=weight_cursor;
                end
            end
            if(bias_read) begin
                ram_en[6]=1'b1;
                ram_address[6]={7'd0,bias_base_word}+{8'd0,output_group};
            end
            if(write_d6) begin
                ram_en[destination_buffer]=1'b1;ram_we[destination_buffer]=1'b1;
                // Eight-bit Buffer A offsets above 127 remain intact.
                ram_address[destination_buffer]={7'd0,output_base_word}+{8'd0,write_group};
            end
        end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;done<=1'b0;
            input_words<=0;output_groups<=0;input_base_word<=0;output_base_word<=0;
            weight_cursor<=0;bias_base_word<=0;
            source_buffer<=0;destination_buffer<=0;bias_shift<=0;output_shift<=0;relu_en<=0;
        end else begin
            done<=1'b0;
            // Actual reads only: no advance during the Legacy one-cycle group gap.
            if(read_issue) weight_cursor<=weight_cursor+15'd1;
            case(state)
                IDLE: if(start) begin
                    input_words<=config_words[6][9:2];output_groups<=groups_from_snapshot[7:0];
                    input_base_word<=config_words[0][9:2];output_base_word<=config_words[2][9:2];
                    weight_cursor<=config_words[1][16:2];bias_base_word<=config_words[3][9:2];
                    source_buffer<=config_words[0][17];destination_buffer<=config_words[2][17];
                    bias_shift<=config_words[7][5:0];output_shift<=config_words[8][4:0];relu_en<=config_words[9][0];
                    state<=PREP;
                end
                PREP: if(prep_done) state<=RUN;
                RUN: if(last_read) state<=DRAIN;
                DRAIN: if(layer_stored) begin state<=IDLE;done<=1'b1;end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
