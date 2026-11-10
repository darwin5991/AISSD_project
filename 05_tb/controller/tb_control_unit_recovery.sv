`timescale 1ns / 1ps
`default_nettype none

// Supplemental diagnostic for the user-approved unused-state recovery policy.
// Normal MNIST verification remains tb_control_unit + its unchanged golden.
// Force injects a fault; all checks observe only external Control ports.
module tb_control_unit_recovery;
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    wire busy, done, in_en, weight_en, bias_en, out_we;
    wire mac_input_valid, bias_load, result_load;
    wire [7:0] in_addr, bias_addr;
    wire [14:0] weight_addr;
    integer cases_checked = 0;

    always #5 clk = ~clk;

    control_unit u_dut (
        .clk(clk), .rst_n(rst_n), .start(start), .argmax_data(32'd0),
        .busy(busy), .done(done), .prediction(), .buf_sel(),
        .in_addr(in_addr), .in_en(in_en), .out_addr(), .out_we(out_we),
        .weight_addr(weight_addr), .weight_en(weight_en),
        .bias_addr(bias_addr), .bias_en(bias_en),
        .mac_input_valid(mac_input_valid), .bias_load(bias_load),
        .bias_shift(), .result_load(result_load), .relu_en(), .output_shift()
    );

    task automatic check_idle;
        if ({busy, done, in_en, weight_en, bias_en, out_we,
             mac_input_valid, bias_load, result_load} !== 9'b0)
            $fatal(1, "recovery: external control pulse survived recovery at %0t", $time);
    endtask

    task automatic start_and_check_first_read;
        start = 1'b1;
        @(negedge clk);
        if ({busy, done, in_en, weight_en, out_we} !== 5'b10000)
            $fatal(1, "recovery: new start was not accepted at %0t", $time);
        start = 1'b0;
        @(negedge clk);
        if ({busy, done, in_en, weight_en, bias_en, out_we} !== 6'b101110 ||
            in_addr !== 8'd0 || weight_addr !== 15'd0 || bias_addr !== 8'd0)
            $fatal(1, "recovery: FC1 first read did not restart at address zero at %0t", $time);
    endtask

    initial begin
        $timeformat(-9, 0, " ns", 10);
        for (integer code = 5; code <= 7; code = code + 1) begin
            rst_n = 1'b0;
            start = 1'b0;
            repeat (3) @(negedge clk);
            rst_n <= 1'b1;
            @(negedge clk);
            check_idle();
            start_and_check_first_read();

            // Inject just before the first output write while later group
            // events are still in the metadata pipes.
            while (out_we !== 1'b1) @(negedge clk);
            case (code)
                5: force u_dut.u_fsm.state = 3'd5;
                6: force u_dut.u_fsm.state = 3'd6;
                7: force u_dut.u_fsm.state = 3'd7;
            endcase
            @(negedge clk);
            check_idle();
            release u_dut.u_fsm.state;
            // Include all six delayed-event stages in the leakage check.
            repeat (7) begin
                @(negedge clk);
                check_idle();
            end
            start_and_check_first_read();
            cases_checked = cases_checked + 1;
        end
        $display("[RECOVERY] result=PASS unused_states=%0d", cases_checked);
        $finish;
    end

    initial begin
        repeat (2000) @(negedge clk);
        $fatal(1, "recovery diagnostic timed out");
    end
endmodule
`default_nettype wire
