`timescale 1ns/1ps
// Synthetic qualified engine activity at the controller boundary, not real EXEC.
module tb_npu_phase2_active;
    logic clk=0,rst_n=0,start=0,load_engine_active=0,gemm_engine_active=0;
    always #5 clk=~clk;
    wire busy,done,fault,imem_en;
    wire [31:0] imem_addr,status;
    wire [7:0] error_code;
    logic [31:0] imem_rdata=0,imem[0:15];
    // Interface adaptation only: this existing test executes no block transfers.
    wire dmem_en,dmem_we,sram_en,sram_we,xfer_busy,xfer_load_active;
    wire [31:0] dmem_addr,dmem_wdata,sram_address,sram_wdata;
    logic [31:0] dmem_rdata=0,sram_rdata=0;
    logic [7:0] sram_error=0;
    instruction_controller #(.IMEM_BYTES(64)) u_dut(.*);
    integer checks=0,cycles=0,age=0,commits=0;
    logic [31:0] word=0,expected_read=0,ref_count=0;
    bit pending=0,ref_armed=0,is_start,is_stop;
    task automatic check(input bit ok,input string reason);
        checks++;
        if(!ok) begin
            $display("[FAIL] active cycle=%0d word=%08h reason=%s count=%08h/%08h armed=%b/%b",
                cycles,word,reason,u_dut.perf_count,ref_count,u_dut.timer_armed,ref_armed);
            $fatal(1,"active controller failure");
        end
    endtask
    always @(posedge clk) if(rst_n && imem_en) imem_rdata<=imem[imem_addr>>2];
    initial begin
        for(integer i=0;i<16;i++) imem[i]=0;
        imem[0]=32'h0000_302b; // TSTART
        imem[1]=32'h0030_0093; // ADDI r1,r0,3
        imem[2]=32'h7f00_2173; // CSRR r2,PERF_COUNT
        imem[3]=32'h0200_302b; // TSTOP
        imem[4]=32'h7f00_21f3; // CSRR r3,PERF_COUNT
        imem[5]=32'h0000_302b; // TSTART
        imem[6]=32'h7f00_2273; // CSRR r4,PERF_COUNT
        imem[7]=32'h0200_302b; // TSTOP
        imem[8]=32'h0400_302b; // END
        repeat(3) @(negedge clk);
        rst_n=1;start=1;
        @(negedge clk);start=0;
        while(!done && !fault) begin
            load_engine_active=(cycles%3!=0);
            gemm_engine_active=(cycles%4==0);
            @(posedge clk);
            is_start=0;is_stop=0;
            if(imem_en) begin pending=1;age=0;word=imem[imem_addr>>2]; end
            else if(pending) age++;
            if(pending && age==2) begin
                is_start=(word==32'h0000_302b);is_stop=(word==32'h0200_302b);
                expected_read=ref_count; // CSRR observes the value before this edge.
            end
            if(is_start) begin ref_count=0;ref_armed=1;end
            else if(is_stop) ref_armed=0;
            else if(ref_armed && (load_engine_active || gemm_engine_active)) ref_count++;
            #1;
            check(u_dut.perf_count===ref_count,"qualified active count");
            check(u_dut.timer_armed===ref_armed,"TSTART/TSTOP commit");
            check(u_dut.perf_overflow===0,"no overflow in short run");
            if(pending && age==2) begin
                if(word==32'h7f00_2173) check(u_dut.u_register_file.registers[2]===expected_read,"CSRR dynamic count r2");
                if(word==32'h7f00_21f3) check(u_dut.u_register_file.registers[3]===expected_read,"CSRR stopped count r3");
                if(word==32'h7f00_2273) check(u_dut.u_register_file.registers[4]===expected_read,"CSRR restarted count r4");
                commits++;pending=0;
            end
            cycles++;check(cycles<100,"timeout");
            @(negedge clk);
        end
        load_engine_active=0;gemm_engine_active=0;
        check(done===1 && fault===0 && status===1 && error_code===0,"normal END");
        check(commits==9,"instruction count");
        check(u_dut.u_register_file.registers[1]===3,"scalar instruction preserved");
        $display("[PHASE2_ACTIVE] result=PASS instructions=%0d cycles=%0d checks=%0d",commits,cycles,checks);
        $finish;
    end
    initial begin repeat(200) @(negedge clk);$fatal(1,"active timeout");end
endmodule
