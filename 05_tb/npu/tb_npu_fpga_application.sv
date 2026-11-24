// Port-only scoreboard shared by RTL reset-wrapper and synthesized-netlist checks.
`timescale 1ns/1ps
`ifndef DUT_TOP
`define DUT_TOP npu_fpga_top
`endif
module tb_npu_fpga_application;
    `include "npu_application_profile.vh"
    logic clk=0,rst_n=0,start=0;
    always #5 clk=~clk;
    wire busy,done,fault,imem_en,dmem_en,dmem_we;
    wire [31:0] imem_addr,dmem_addr,dmem_wdata;
    logic [31:0] imem_rdata=0,dmem_rdata=0;
    logic [31:0] imem[0:IMEM_BYTES/4-1],dmem[0:DMEM_BYTES/4-1];
    logic [31:0] golden[0:IMAGE_COUNT-1],layers[0:162],word;
    string data_dir;
    integer predictions=0,layer_words=0,instructions=0,loads=0,gemms=0,args=0,branches=0,handle;
    logic [31:0] last_pc;
    longint unsigned cycles=0;
    `DUT_TOP u_dut(.*);
    task automatic fail(input string reason);
        $display("[FPGA_APP_FAIL] cycles=%0d predictions=%0d last_pc=%08h %s",cycles,predictions,last_pc,reason);
        $fatal(1,"FPGA application mismatch");
    endtask
    always @(posedge clk)begin
        if(!rst_n)begin imem_rdata<=0;dmem_rdata<=0;end
        else begin
            if(imem_en)begin
                if(imem_addr%4 || imem_addr>=CODE_WORDS*4)fail("IMEM request");
                word=imem[imem_addr>>2];last_pc=imem_addr;instructions++;
                if(word==32'h002081ab)loads++;
                if(word==32'h0000202b)gemms++;
                if(word==32'h020022ab)args++;
                if(word[6:0]==7'h63)branches++;
                imem_rdata<=word;
            end
            if(dmem_en)begin
                if(dmem_addr%4 || dmem_addr<32'h10000000 ||
                   {1'b0,dmem_addr}+4>33'h010000000+DMEM_BYTES)fail("DMEM bounds/alignment");
                if(dmem_we)begin
                    dmem[(dmem_addr-32'h10000000)>>2]<=dmem_wdata;
                    if(dmem_addr>=PRED_BASE && dmem_addr<PRED_BASE+4*IMAGE_COUNT)begin
                        $fdisplay(handle,"%08h %08h",dmem_addr,dmem_wdata);
                        if(predictions>=IMAGE_COUNT || dmem_addr!==PRED_BASE+4*predictions ||
                           dmem_wdata!==golden[predictions])fail("prediction value/address");
                        predictions++;
                        if(predictions%25==0 || predictions==IMAGE_COUNT)
                            $display("[PROGRESS] images=%0d cycles=%0d",predictions,cycles);
                    end else if(DEBUG_LAYERS && dmem_addr>=LAYER_BASE && dmem_addr<LAYER_BASE+652)begin
                        if(layer_words>=163 || dmem_addr!==LAYER_BASE+4*layer_words ||
                           dmem_wdata!==layers[layer_words])fail("layer value/address");
                        layer_words++;
                    end else fail("unexpected write");
                end else dmem_rdata<=dmem[(dmem_addr-32'h10000000)>>2];
            end
        end
    end
    initial begin
        if(!$value$plusargs("DATA_DIR=%s",data_dir))$fatal(1,"DATA_DIR required");
        for(integer i=0;i<IMEM_BYTES/4;i++)imem[i]=0;
        for(integer i=0;i<DMEM_BYTES/4;i++)dmem[i]=0;
        $readmemh({data_dir,"/imem.hex"},imem,0,CODE_WORDS-1);
        $readmemh({data_dir,"/dmem.hex"},dmem,0,DMEM_INIT_WORDS-1);
        $readmemh({data_dir,"/golden_prediction.hex"},golden);
        if(DEBUG_LAYERS)$readmemh({data_dir,"/golden_layers.hex"},layers);
        handle=$fopen({data_dir,"/observed_prediction.txt"},"w");
        if(!handle)$fatal(1,"result open");
        // Also covers the vendor global-set/reset interval in functional netlists.
        repeat(20)@(negedge clk);
        #2;rst_n=1;
        repeat(4)@(negedge clk);
        start=1;@(negedge clk);start=0;
        while(!done)begin
            @(posedge clk);#1;cycles++;
            if(fault)fail("DUT Fault");
            if(cycles>=MAX_CYCLES)fail("timeout");
        end
        if(busy || fault || predictions!=IMAGE_COUNT || instructions!=EXPECTED_INSTRUCTIONS ||
           loads!=5+IMAGE_COUNT || gemms!=3*IMAGE_COUNT || args!=IMAGE_COUNT ||
           branches!=IMAGE_COUNT || last_pc!==END_PC ||
           layer_words!=(DEBUG_LAYERS?163:0))fail("END/counter check");
        for(integer i=0;i<IMAGE_COUNT;i++)
            if(dmem[(PRED_BASE-32'h10000000)/4+i]!==golden[i])fail("final DMEM");
        $fclose(handle);
        repeat(3)begin @(posedge clk);#1;if(done || busy || fault || imem_en || dmem_en)fail("END/Halt");end
        $display("[FPGA_APP] result=PASS images=%0d predictions=%0d loads=%0d gemm=%0d argmax=%0d cycles=%0d layer_words=%0d",
                 IMAGE_COUNT,predictions,loads,gemms,args,cycles,layer_words);
        $finish;
    end
endmodule
