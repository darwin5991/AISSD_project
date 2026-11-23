`timescale 1ns/1ps
module tb_npu_memory_owner;
    import npu_memory_pkg::*;
    logic clk=0,rst_n=0;
    always #5 clk=~clk;
    logic [1:0] owner=OWNER_NONE;
    logic xfer_en=0,xfer_we=0;
    logic [31:0] xfer_address=0,xfer_wdata=0;
    wire [31:0] xfer_rdata;
    wire [7:0] xfer_error;
    logic [6:0] gemm_en=0,gemm_we=0;
    logic [14:0] gemm_address[0:6];
    logic [31:0] gemm_wdata[0:6];
    wire [31:0] gemm_rdata[0:6];
    logic argmax_en=0;
    logic [31:0] argmax_address=0;
    wire [31:0] argmax_rdata;
    wire [7:0] argmax_error;
    integer checks=0;
    npu_memory_wrapper u_dut(.*);
    task automatic check(input bit ok,input string reason);
        checks++;
        if(!ok) begin
            $display("[FAIL] %s owner=%0d address=%08h rdata=%08h error=%02h",reason,owner,xfer_address,xfer_rdata,xfer_error);
            $fatal(1,"owner wrapper failure");
        end
    endtask
    task automatic write_word(input logic [31:0] a,input logic [31:0] d);
        @(negedge clk);owner=OWNER_XFER;xfer_en=1;xfer_we=1;xfer_address=a;xfer_wdata=d;
        #1;check(xfer_error===0,"valid write decode");
        @(posedge clk);#1;
        @(negedge clk);xfer_en=0;
    endtask
    initial begin
        for(integer b=0;b<7;b++) begin gemm_address[b]=0;gemm_wdata[b]=0;end
        repeat(3) @(negedge clk);rst_n=1;
        for(integer b=0;b<7;b++) begin
            write_word(bank_base(b),32'h9100_0000+b);
            write_word(bank_base(b)+4*(bank_depth(b)-1),32'ha200_0000+b);
        end
        // Independent physical banks return all seven words in parallel at R.
        @(negedge clk);owner=OWNER_GEMM;gemm_en=7'h7f;
        xfer_en=1;xfer_we=1;xfer_address=32'h8000_0000;xfer_wdata=32'hbad0_0000;
        @(posedge clk);#1;
        for(integer b=0;b<7;b++) check(gemm_rdata[b]===(32'h9100_0000+b),"parallel first-word read, no output stage");
        @(negedge clk);
        for(integer b=0;b<7;b++) gemm_address[b]=bank_depth(b)-1;
        @(posedge clk);#1;
        for(integer b=0;b<7;b++) check(gemm_rdata[b]===(32'ha200_0000+b),"parallel last-word read");
        @(negedge clk);gemm_en=0;
        repeat(2) begin
            @(posedge clk);#1;
            for(integer b=0;b<7;b++) check(gemm_rdata[b]===(32'ha200_0000+b),"disabled RAM read hold");
        end
        // ARGMAX port selects A/B; an unselected XFER write must not alter A.
        @(negedge clk);owner=OWNER_ARGMAX;argmax_en=1;argmax_address=32'h8000_0000;
        @(posedge clk);#1;check(argmax_rdata===32'h9100_0000,"ARGMAX A and owner isolation");
        @(negedge clk);argmax_address=32'h8002_0000;
        @(posedge clk);#1;check(argmax_rdata===32'h9100_0001,"ARGMAX B");
        @(negedge clk);argmax_en=0;owner=OWNER_XFER;
        xfer_en=1;xfer_we=0;xfer_address=32'h800a_0000+4*(29280-1);
        @(posedge clk);#1;check(xfer_rdata===32'ha200_0005,"bank5 registered read selection");
        @(negedge clk);xfer_we=1;xfer_address=32'h800c_0000;xfer_wdata=32'h1234_5678;
        @(posedge clk);#1;check(xfer_rdata===32'ha200_0005,"write does not change read register");
        @(negedge clk);xfer_en=0;
        @(posedge clk);#1;check(xfer_rdata===32'ha200_0005,"XFER disabled hold");
        // Invalid XFER addresses are blocked before physical address truncation.
        @(negedge clk);xfer_en=1;xfer_we=1;xfer_address=32'h8002_0200;
        #1;check(xfer_error===8'd6 && u_dut.ram_en===0,"Buffer B hole blocked");
        @(negedge clk);xfer_address=32'h8000_0001;
        #1;check(xfer_error===8'd5 && u_dut.ram_en===0,"misalignment blocked");
        @(negedge clk);xfer_address=32'h800e_0000;
        #1;check(xfer_error===8'd4 && u_dut.ram_en===0,"reserved bank blocked");
        @(negedge clk);owner=OWNER_NONE;gemm_en=7'h7f;argmax_en=1;
        #1;check(u_dut.ram_en===0,"NONE owner blocks all");
        @(negedge clk);rst_n=0;#1;
        check(xfer_rdata===0 && argmax_rdata===0,"read register reset");
        @(negedge clk);rst_n=1;owner=OWNER_XFER;xfer_en=1;xfer_we=0;xfer_address=32'h8000_0000;
        @(posedge clk);#1;check(xfer_rdata===32'h9100_0000,"Reset preserves stored SRAM words");
        $display("[MEMORY_OWNER] result=PASS banks=7 checks=%0d",checks);
        $finish;
    end
    initial begin repeat(500) @(negedge clk);$fatal(1,"wrapper timeout");end
endmodule
