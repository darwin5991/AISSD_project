// One GEMM; legacy read/bubble and R+1/5/6 pipeline tags retained.
module gemm_controller(input logic clk,rst_n,start,
    input logic [31:0] src0,src1,dst,bias,input logic [20:0] dim,input logic [11:0] cfg,
    output logic active,done,buf_sel,read_en,bias_en,
    output logic [7:0] in_addr,out_addr,bias_addr,output logic [14:0] weight_addr,
    output logic mac_input_valid,bias_load,result_load,out_we,
    output logic signed [5:0] bias_shift,output logic [4:0] output_shift,output logic relu_en);
typedef enum logic [1:0] {IDLE,PREP,RUN,DRAIN} state_t;
state_t state;
logic [7:0] q,groups,input_word,input_base,output_base,bias_base;
logic [6:0] group_index,stored_group;
logic [14:0] weight_cursor;
logic last_input,last_read,next_bias,first_read,first_d1,next_d5,last_d6;
assign active=state!=IDLE;
assign read_en=(state==RUN && input_word<q);
assign bias_en=read_en && input_word==0;
assign first_read=bias_en && group_index==0;
assign last_input=read_en && input_word==q-1'b1;
assign last_read=last_input && {1'b0,group_index}==groups-1'b1;
assign next_bias=last_input && !last_read;
assign in_addr=input_base+input_word;
assign weight_addr=weight_cursor;
assign bias_addr=bias_base+{1'b0,group_index};
assign out_addr=output_base+{1'b0,stored_group};
assign bias_load=first_d1 || next_d5;
delay_line #(.WIDTH(1),.DEPTH(1)) u_valid(clk,rst_n,read_en,mac_input_valid);
delay_line #(.WIDTH(1),.DEPTH(1)) u_first(clk,rst_n,first_read,first_d1);
delay_line #(.WIDTH(1),.DEPTH(5)) u_result(clk,rst_n,last_input,result_load);
delay_line #(.WIDTH(1),.DEPTH(5)) u_bias(clk,rst_n,next_bias,next_d5);
delay_line #(.WIDTH(1),.DEPTH(6)) u_write(clk,rst_n,last_input,out_we);
delay_line #(.WIDTH(7),.DEPTH(6)) u_group(clk,rst_n,group_index,stored_group);
delay_line #(.WIDTH(1),.DEPTH(6)) u_last(clk,rst_n,last_read,last_d6);
always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin
        state<=IDLE;done<=0;input_word<=0;group_index<=0;weight_cursor<=0;
        buf_sel<=0;bias_shift<=0;output_shift<=0;relu_en<=0;
    end else begin
        done<=0;
        case(state)
            IDLE:if(start) begin
                state<=PREP;q<=dim[9:2];groups<=({1'b0,dim[19:10]}+11'd3)>>2;
                input_word<=0;group_index<=0;weight_cursor<=src1[16:2];
                input_base<=src0[9:2];output_base<=dst[9:2];bias_base<=bias[9:2];buf_sel<=src0[17];
                bias_shift<=cfg[5:0];output_shift<=cfg[10:6];relu_en<=cfg[11];
            end
            PREP:state<=RUN;
            RUN:begin
                if(read_en) begin input_word<=input_word+1'b1;weight_cursor<=weight_cursor+1'b1;end
                else begin input_word<=0;group_index<=group_index+1'b1;end
                if(last_read) state<=DRAIN;
            end
            DRAIN:if(last_d6) begin state<=IDLE;done<=1;end
            default:begin end
        endcase
    end
end
endmodule
