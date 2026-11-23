// Application scoreboard: fixed-latency memories, no per-cycle/event fixtures.
`timescale 1ns/1ps
module tb_npu_application;
    `include "npu_application_profile.vh"
    logic clk=0,rst_n=0,start=0;
    always #5 clk=~clk;
    wire busy,done,fault,imem_en,dmem_en,dmem_we;
    wire [31:0] imem_addr,dmem_addr,dmem_wdata;
    logic [31:0] imem_rdata=0,dmem_rdata=0;
    logic [31:0] imem[0:IMEM_BYTES/4-1],dmem[0:DMEM_BYTES/4-1];
    logic [31:0] golden[0:IMAGE_COUNT-1],layer_golden[0:162];
    string data_dir;
    integer predictions,loads,stores,instructions,branches,gemm_starts,gemm_dones,arg_starts,arg_dones;
    integer current_words,read_words,write_words,debug_words,pred_file,layer_file,summary_file,image_index;
    logic [31:0] current_src,current_dst,word;
    bit load_pending;
    longint unsigned cycles;
    npu_top #(.IMEM_BYTES(IMEM_BYTES),.DMEM_BYTES(DMEM_BYTES)) u_dut(.*);

    task automatic fail(input string reason);
        $display("[APPLICATION_FAIL] cycles=%0d image=%0d predictions=%0d pc=%08h status=%0d error=%02h %s",
                 cycles,predictions,predictions,u_dut.u_instruction_controller.pc,u_dut.status,u_dut.error_code,reason);
        for(integer i=0;i<8;i++)
            $display("GPR r%0d=%08h",i,u_dut.u_instruction_controller.u_register_file.registers[i]);
        for(integer i=0;i<12;i++) $display("CSR setting[%0d]=%08h",i,u_dut.u_instruction_controller.u_csr.settings[i]);
        $fatal(1,"Application verification failed");
    endtask

    // R accepts a read; nonblocking rdata is consumed by DUT at R+1.
    always @(posedge clk) begin
        if(!rst_n)begin imem_rdata<=0;dmem_rdata<=0;end
        else begin
            if(imem_en)begin
                if(imem_addr%4 || imem_addr>=CODE_WORDS*4)fail("IMEM request outside assembled program");
                imem_rdata<=imem[imem_addr>>2];
            end
            if(dmem_en)begin
                if(dmem_addr%4 || dmem_addr<32'h10000000 ||
                   {1'b0,dmem_addr}+4>33'h010000000+DMEM_BYTES)fail("DMEM request bounds/alignment");
                if(dmem_we)dmem[(dmem_addr-32'h10000000)>>2]<=dmem_wdata;
                else dmem_rdata<=dmem[(dmem_addr-32'h10000000)>>2];
            end
        end
    end

    always @(posedge clk) if(rst_n)begin
        if(imem_en)begin
            instructions++;
            if(load_pending)begin
                if(read_words!=current_words || write_words!=current_words)fail("incomplete LOAD");
                load_pending=0;
            end
            word=imem[imem_addr>>2];
            if(word==32'h002081ab)begin
                if(loads<5)begin
                    current_src=model_src(loads);current_dst=model_dst(loads);current_words=model_bytes(loads)/4;
                end else begin
                    image_index=loads-5;
                    if(image_index>=IMAGE_COUNT)fail("extra Input LOAD");
                    current_src=INPUT_BASE+image_index*784;current_dst=32'h80000000;current_words=196;
                    if(u_dut.u_instruction_controller.u_register_file.registers[6]!==PRED_BASE+image_index*4 ||
                       u_dut.u_instruction_controller.u_register_file.registers[7]!==INPUT_END)
                        fail("loop-live Prediction/Input end register clobbered");
                end
                if(u_dut.u_instruction_controller.u_register_file.registers[1]!==current_src ||
                   u_dut.u_instruction_controller.u_register_file.registers[2]!==current_dst ||
                   u_dut.u_instruction_controller.u_register_file.registers[3]!==current_words*4)
                    fail("LOAD operands/pointer/length");
                read_words=0;write_words=0;load_pending=1;loads++;
            end else if(word[6:0]==7'h2b && word[14:12]==0)fail("unexpected LOAD encoding");
            if(word[6:0]==7'h2b && word[14:12]==1)stores++;
            if(word[6:0]==7'h63)begin
                if(word[14:12]!=1)fail("unexpected branch type");
                branches++;
            end
            if(word==32'h0000302b || word==32'h0200302b)fail("Timer instruction in application");
        end
        if(dmem_en && !dmem_we)begin
            if(!load_pending || read_words>=current_words || dmem_addr!==current_src+4*read_words)
                fail("unexpected/repeated LOAD DMEM read");
            read_words++;
        end
        if(u_dut.xfer_busy && u_dut.sram_en && u_dut.sram_we)begin
            if(!load_pending || write_words>=current_words ||
               u_dut.sram_address!==current_dst+4*write_words ||
               u_dut.sram_wdata!==dmem[(current_src+4*write_words-32'h10000000)>>2])
                fail("LOAD destination/data/order");
            write_words++;
        end
        if(u_dut.gemm_start)begin
            for(integer i=0;i<10;i++)
                if(u_dut.gemm_config[i]!==fc_config(gemm_starts%3,i))fail("GEMM raw CSR Snapshot");
            gemm_starts++;
        end
        if(u_dut.gemm_done)gemm_dones++;
        if(u_dut.argmax_start)begin
            if(u_dut.argmax_config[0]!==32'h80020000 || u_dut.argmax_config[1]!==10)
                fail("ARGMAX Snapshot");
            arg_starts++;
        end
        if(u_dut.argmax_done)arg_dones++;
        if(dmem_en && dmem_we)begin
            if(dmem_addr>=PRED_BASE && dmem_addr<PRED_BASE+IMAGE_COUNT*4)begin
                $fdisplay(pred_file,"%08h %08h",dmem_addr,dmem_wdata);
                if(predictions>=IMAGE_COUNT || dmem_addr!==PRED_BASE+predictions*4)
                    fail("prediction address/order/count");
                if(dmem_wdata!==golden[predictions])
                    fail($sformatf("prediction mismatch RTL=%0d Golden=%0d",dmem_wdata,golden[predictions]));
                predictions++;
                if(predictions%25==0 || predictions==IMAGE_COUNT)
                    $display("[PROGRESS] images=%0d cycles=%0d",predictions,cycles);
            end else if(DEBUG_LAYERS && dmem_addr>=LAYER_BASE && dmem_addr<LAYER_BASE+652)begin
                $fdisplay(layer_file,"%08h %08h",dmem_addr,dmem_wdata);
                if(debug_words>=163 || dmem_addr!==LAYER_BASE+debug_words*4 ||
                   dmem_wdata!==layer_golden[debug_words])fail("intermediate layer bit-exact mismatch");
                debug_words++;
            end else fail("write outside Prediction/debug outputs");
        end
    end

    initial begin
        predictions=0;loads=0;stores=0;instructions=0;branches=0;
        gemm_starts=0;gemm_dones=0;arg_starts=0;arg_dones=0;
        cycles=0;load_pending=0;debug_words=0;read_words=0;write_words=0;
        if(!$value$plusargs("DATA_DIR=%s",data_dir))$fatal(1,"DATA_DIR required");
        for(integer i=0;i<IMEM_BYTES/4;i++)imem[i]=0;
        for(integer i=0;i<DMEM_BYTES/4;i++)dmem[i]=0;
        $readmemh({data_dir,"/imem.hex"},imem,0,CODE_WORDS-1);
        $readmemh({data_dir,"/dmem.hex"},dmem,0,DMEM_INIT_WORDS-1);
        $readmemh({data_dir,"/golden_prediction.hex"},golden);
        if(DEBUG_LAYERS)$readmemh({data_dir,"/golden_layers.hex"},layer_golden);
        pred_file=$fopen({data_dir,"/observed_prediction.txt"},"w");
        layer_file=$fopen({data_dir,"/observed_layers.txt"},"w");
        summary_file=$fopen({data_dir,"/tb_summary.txt"},"w");
        if(!pred_file || !layer_file || !summary_file)$fatal(1,"cannot open application results");
        repeat(3)@(negedge clk);
        rst_n=1;start=1;@(negedge clk);start=0;
        while(!done)begin
            @(posedge clk);#1;cycles++;
            if(fault)fail("DUT Fault");
            if(u_dut.u_instruction_controller.timer_armed!==0 ||
               u_dut.u_instruction_controller.perf_count!==0 ||
               u_dut.u_instruction_controller.perf_overflow!==0)fail("Timer OFF invariant");
            if(cycles>=MAX_CYCLES)fail("simulation timeout");
        end
        if(load_pending || loads!=5+IMAGE_COUNT || predictions!=IMAGE_COUNT ||
           stores!=(DEBUG_LAYERS?3:0) || branches!=IMAGE_COUNT ||
           gemm_starts!=3*IMAGE_COUNT || gemm_dones!=gemm_starts ||
           arg_starts!=IMAGE_COUNT || arg_dones!=arg_starts ||
           instructions!=EXPECTED_INSTRUCTIONS)fail("final execution counts");
        if(u_dut.status!==1 || u_dut.error_code!==0 || busy!==0 ||
           u_dut.u_instruction_controller.pc!==END_PC)fail("END status/PC");
        if(u_dut.u_instruction_controller.u_register_file.registers[0]!==0 ||
           u_dut.u_instruction_controller.u_register_file.registers[1]!==INPUT_END ||
           u_dut.u_instruction_controller.u_register_file.registers[3]!==784 ||
           u_dut.u_instruction_controller.u_register_file.registers[6]!==PRED_BASE+4*IMAGE_COUNT ||
           u_dut.u_instruction_controller.u_register_file.registers[7]!==INPUT_END)fail("final loop GPRs");
        for(integer i=0;i<IMAGE_COUNT;i++)
            if(dmem[(PRED_BASE-32'h10000000)/4+i]!==golden[i])fail("final prediction DMEM");
        if(debug_words!=(DEBUG_LAYERS?163:0))fail("layer output count");
        $fclose(pred_file);$fclose(layer_file);
        repeat(3)begin
            @(posedge clk);#1;
            if(done || busy || fault || imem_en || dmem_en)fail("END pulse/Halt");
        end
        $display("[APPLICATION] result=PASS images=%0d predictions=%0d loads=%0d gemm=%0d argmax=%0d branches=%0d instructions=%0d cycles=%0d layer_words=%0d timer=0",
                 IMAGE_COUNT,predictions,loads,gemm_dones,arg_dones,branches,instructions,cycles,debug_words);
        $fdisplay(summary_file,"%0d %0d %0d %0d %0d %0d %0d %0d %0d",
                  IMAGE_COUNT,predictions,loads,gemm_dones,arg_dones,branches,instructions,cycles,debug_words);
        $fclose(summary_file);
        $finish;
    end
endmodule
