// Check async assertion/sync release, reset write blocking, retention and first read.
`timescale 1ns/1ps
module tb_npu_reset_sync;
    logic clk=0,rst_n=0,en=0,we=0;
    logic [7:0] addr=0;
    logic [31:0] wdata=0;
    wire core_rst_n;
    wire [31:0] rdata;
    integer checks=0;
    always #5 clk=~clk;
    npu_reset_sync u_reset(.clk(clk),.async_rst_n(rst_n),.core_rst_n(core_rst_n));
    single_port_bram #(.DEPTH(196),.ADDR_WIDTH(8)) u_ram(
        .clk(clk),.rst_n(core_rst_n),.en(en),.we(we),.addr(addr),.wdata(wdata),.rdata(rdata));
    task automatic check(input bit condition,input string reason);
        checks++;
        if(!condition)$fatal(1,"Reset/SRAM check failed: %s",reason);
    endtask
    task automatic release_reset;
        @(negedge clk);#2;rst_n=1;
        #1;check(core_rst_n===0,"release between edges remains asserted");
        @(posedge clk);#1;check(core_rst_n===0,"first rising edge");
        @(posedge clk);#1;check(core_rst_n===1,"second rising edge");
    endtask
    initial begin
        #1;check(core_rst_n===0 && rdata===0,"initial reset");
        release_reset();
        @(negedge clk);en=1;we=1;addr=195;wdata=32'h89abcdef;
        @(posedge clk);#1;check(rdata===0,"write holds output");
        @(negedge clk);we=0;
        #1;check(rdata===0,"read does not respond before edge");
        @(posedge clk);#1;check(rdata===32'h89abcdef,"one-cycle read");
        @(negedge clk);en=0;
        @(posedge clk);#1;check(rdata===32'h89abcdef,"disabled hold");
        @(negedge clk);#2;rst_n=0;
        #1;check(core_rst_n===0 && rdata===0,"async assertion without clock");
        en=1;we=1;wdata=32'hdeadbeef;
        repeat(2)@(posedge clk);
        #1;check(rdata===0,"write blocked during reset");
        release_reset();
        // At both release edges the SRAM saw core reset asserted before the edge.
        we=0;
        #1;check(rdata===0,"output remains zero before first post-reset read");
        @(posedge clk);#1;check(rdata===32'h89abcdef,"first read retains pre-reset word");
        @(negedge clk);we=1;wdata=32'h12345678;
        @(posedge clk);#1;check(rdata===32'h89abcdef,"read-during-write holds");
        @(negedge clk);we=0;
        @(posedge clk);#1;check(rdata===32'h12345678,"new committed write");
        $display("[RESET_SRAM] result=PASS checks=%0d",checks);
        $finish;
    end
    initial begin #2000;$fatal(1,"Reset unit timeout");end
endmodule
