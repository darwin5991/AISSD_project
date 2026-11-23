`timescale 1ns/1ps
module tb_npu_phase4;
    `include "npu_phase4_profile.vh"
    localparam integer RW=29,MAX_STEPS=1024,MAX_EVENTS=131072,MAX_FINAL=65536;
    logic clk=0,rst_n=0,start=0;
    always #5 clk=~clk;
    wire busy,done,fault,imem_en,dmem_en,dmem_we;
    wire [31:0] imem_addr,dmem_addr,dmem_wdata;
    logic [31:0] imem_rdata=0,dmem_rdata=0;
    logic [31:0] imem[0:IMEM_BYTES/4-1],dmem[0:DMEM_BYTES/4-1];
    logic [31:0] trace[0:MAX_STEPS*RW-1],events[0:MAX_EVENTS*5-1],final_data[0:MAX_FINAL*2-1];
    string data_dir,path;
    integer meta,scanned,id,steps,event_count,final_count,inject_pc;
    integer checks=0,cases=0,total_steps=0,total_events=0,step_index,event_index,age,cycles,done_count;
    bit pending,injected,commit_now,want_active;
    logic [31:0] word,actual_addr,actual_data,read_hold;
    integer kind,base,bank,observed_trace,observed_final;
    logic [31:0] fetched_pc;
    npu_top #(.IMEM_BYTES(IMEM_BYTES),.DMEM_BYTES(DMEM_BYTES)) u_dut(.*);
    task automatic check(input bit ok,input string reason);
        checks++;
        if(!ok) begin
            $display("[FAIL] case=%0d step=%0d age=%0d event=%0d time=%0t %s pc=%08h error=%02h",
                id,step_index,age,event_index,$time,reason,u_dut.u_instruction_controller.pc,u_dut.error_code);
            $fatal(1,"Phase 4 scoreboard mismatch");
        end
    endtask
    always @(posedge clk) begin
        if(!rst_n) begin imem_rdata<=0;dmem_rdata<=0;end
        else begin
            if(imem_en) begin
                if(imem_addr%4 || imem_addr>=IMEM_BYTES) $fatal(1,"invalid IMEM request");
                imem_rdata<=imem[imem_addr>>2];
            end
            if(dmem_en) begin
                if(dmem_addr%4 || dmem_addr<32'h10000000 ||
                   {1'b0,dmem_addr}+4>33'h010000000+DMEM_BYTES) $fatal(1,"invalid DMEM request");
                if(dmem_we) dmem[(dmem_addr-32'h10000000)>>2]<=dmem_wdata;
                else dmem_rdata<=dmem[(dmem_addr-32'h10000000)>>2];
            end
        end
    end
    initial begin
        if(!$value$plusargs("DATA_DIR=%s",data_dir)) $fatal(1,"DATA_DIR required");
        meta=$fopen({data_dir,"/cases.txt"},"r");
        if(!meta) $fatal(1,"case metadata missing");
        while(!$feof(meta)) begin
            scanned=$fscanf(meta,"%d %d %d %d %d\n",id,steps,event_count,final_count,inject_pc);
            if(scanned!=5) $fatal(1,"case metadata invalid");
            check(steps>0 && steps<=MAX_STEPS && event_count<=MAX_EVENTS && final_count<=MAX_FINAL,"fixture capacity");
            @(negedge clk);rst_n=0;start=0;
            for(integer i=0;i<IMEM_BYTES/4;i++) imem[i]=0;
            for(integer i=0;i<DMEM_BYTES/4;i++) dmem[i]=0;
            path=$sformatf("%s/case_%0d.observed_trace.hex",data_dir,id);observed_trace=$fopen(path,"w");
            path=$sformatf("%s/case_%0d.observed_final.hex",data_dir,id);observed_final=$fopen(path,"w");
            if(!observed_trace || !observed_final) $fatal(1,"cannot open observed results");
            path=$sformatf("%s/case_%0d.imem.hex",data_dir,id);$readmemh(path,imem);
            path=$sformatf("%s/case_%0d.dmem.hex",data_dir,id);$readmemh(path,dmem);
            path=$sformatf("%s/case_%0d.trace.hex",data_dir,id);$readmemh(path,trace,0,steps*RW-1);
            if(event_count>0) begin
                path=$sformatf("%s/case_%0d.bus.hex",data_dir,id);$readmemh(path,events,0,event_count*5-1);
            end
            if(final_count>0) begin
                path=$sformatf("%s/case_%0d.final.hex",data_dir,id);$readmemh(path,final_data,0,final_count*2-1);
            end
            repeat(3) @(negedge clk);
            #1;
            check({busy,done,fault,imem_en,dmem_en,u_dut.sram_en}===6'd0,"reset ports");
            for(integer r=0;r<8;r++) check(u_dut.u_instruction_controller.u_register_file.registers[r]===0,"reset GPR");
            for(integer c=0;c<12;c++) check(u_dut.u_instruction_controller.u_csr.settings[c]===0,"reset CSR");
            check(u_dut.u_instruction_controller.perf_count===0,"reset timer");
            rst_n=1;start=1;
            @(negedge clk);start=0;
            step_index=0;event_index=0;pending=0;injected=0;age=0;cycles=0;done_count=0;
            while(step_index<steps) begin
                @(posedge clk);
                if(imem_en) begin
                    check(!pending,"fetch during outstanding instruction");
                    check(imem_addr===trace[step_index*RW],"fetch PC");
                    fetched_pc=imem_addr;word=trace[step_index*RW+1];
                    check(imem[imem_addr>>2]===word,"instruction word");
                    pending=1;age=0;
                end else if(pending) age++;
                commit_now=pending && age==trace[step_index*RW+28];
                want_active=pending && word[6:0]==7'h2b && word[14:12]==0 &&
                    age>=4 && age<trace[step_index*RW+28];
                check(u_dut.xfer_load_active===want_active,"LOAD active first request through final write/abort");
                read_hold=dmem_rdata;
                // Serial transfer: at most one external/internal access in each edge.
                check(!(dmem_en && u_dut.sram_en),"overlapped read/write transfer");
                if(dmem_en || u_dut.sram_en) begin
                    check(event_index<event_count,"unexpected memory side effect");
                    base=event_index*5;
                    kind=dmem_en?(dmem_we?1:0):(u_dut.sram_we?3:2);
                    actual_addr=dmem_en?dmem_addr:u_dut.sram_address;
                    actual_data=dmem_en?(dmem_we?dmem_wdata:dmem[(dmem_addr-32'h10000000)>>2]):u_dut.sram_wdata;
                    check(step_index==events[base] && age==events[base+1],"memory event timing");
                    check(kind==events[base+2] && actual_addr===events[base+3],"memory event address/operation");
                    if(kind!=2) check(actual_data===events[base+4],$sformatf("memory data actual=%08h expected=%08h",actual_data,events[base+4]));
                    if(u_dut.sram_en) begin
                        bank=actual_addr[19:17];
                        check(u_dut.u_memory.ram_en===(7'b1<<bank),"single physical SRAM selected");
                        check(u_dut.sram_error===0,"valid SRAM decode");
                    end
                end
                if(event_index<event_count && events[event_index*5]==step_index && events[event_index*5+1]==age)
                    check(dmem_en || u_dut.sram_en,"missing memory request");
                #1;
                if(event_index<event_count && events[event_index*5]==step_index &&
                   events[event_index*5+1]==age) begin
                    if(events[event_index*5+2]==2)
                        check(u_dut.sram_rdata===events[event_index*5+4],"SRAM registered response, no extra output stage");
                    if(events[event_index*5+2]==0)
                        check(dmem_rdata===events[event_index*5+4],"DMEM registered response");
                    else check(dmem_rdata===read_hold,"DMEM read data holds on write/disable");
                    event_index++;total_events++;
                end else check(dmem_rdata===read_hold,"disabled DMEM read hold");
                if(pending && age==1)
                    check(u_dut.u_instruction_controller.instruction===word,"IR R+1 capture");
                check(u_dut.u_instruction_controller.u_register_file.registers[0]===0,"r0 invariant");
                // Architectural state cannot change early while a read is outstanding.
                if(!commit_now) begin
                    for(integer r=0;r<8;r++)
                        check(u_dut.u_instruction_controller.u_register_file.registers[r]===
                            ((step_index==0)?32'd0:trace[(step_index-1)*RW+5+r]),"GPR stable before commit");
                    for(integer c=0;c<12;c++)
                        check(u_dut.u_instruction_controller.u_csr.settings[c]===
                            ((step_index==0)?32'd0:trace[(step_index-1)*RW+13+c]),"CSR stable before commit");
                end
                if(commit_now) begin
                    $fdisplay(observed_trace,"%08h\n%08h\n%08h\n%08h\n%08h",
                        fetched_pc,word,u_dut.u_instruction_controller.pc,u_dut.status,{24'd0,u_dut.error_code});
                    for(integer r=0;r<8;r++)
                        $fdisplay(observed_trace,"%08h",u_dut.u_instruction_controller.u_register_file.registers[r]);
                    for(integer c=0;c<12;c++)
                        $fdisplay(observed_trace,"%08h",u_dut.u_instruction_controller.u_csr.settings[c]);
                    $fdisplay(observed_trace,"%08h\n%08h\n%08h\n%08h",
                        u_dut.u_instruction_controller.perf_count,{31'd0,u_dut.u_instruction_controller.perf_overflow},
                        {31'd0,u_dut.u_instruction_controller.timer_armed},age);
                    check(u_dut.u_instruction_controller.pc===trace[step_index*RW+2],"post-commit PC");
                    check(u_dut.status===trace[step_index*RW+3] && {24'd0,u_dut.error_code}===trace[step_index*RW+4],"Status/Error");
                    for(integer r=0;r<8;r++)
                        check(u_dut.u_instruction_controller.u_register_file.registers[r]===trace[step_index*RW+5+r],$sformatf("GPR r%0d",r));
                    for(integer c=0;c<12;c++)
                        check(u_dut.u_instruction_controller.u_csr.settings[c]===trace[step_index*RW+13+c],"CSR preserved");
                    check(u_dut.u_instruction_controller.perf_count===trace[step_index*RW+25],"Timer exact active count");
                    check({31'd0,u_dut.u_instruction_controller.perf_overflow}===trace[step_index*RW+26],"Timer overflow");
                    check({31'd0,u_dut.u_instruction_controller.timer_armed}===trace[step_index*RW+27],"Timer armed");
                    check(done===(trace[step_index*RW+3]==1) && fault===(trace[step_index*RW+3]==2),"END/Fault");
                    check(busy===(trace[step_index*RW+3]==0),"blocking busy");
                    if(done)done_count++;
                    $display("[STEP] case=%0d step=%0d pc=%08h age=%0d count=%0d error=%02h",id,step_index,trace[step_index*RW],age,u_dut.u_instruction_controller.perf_count,u_dut.error_code);
                    step_index++;total_steps++;pending=0;
                end
                cycles++;check(cycles<1000000,"instruction timeout");
                @(negedge clk);
                start=(cycles%7==0);
            end
            check(event_index==event_count,"complete bus trace");
            check(done_count==((u_dut.status==1)?1:0),"done pulse count");
            for(integer i=0;i<final_count;i++) begin
                check(dmem[(final_data[2*i]-32'h10000000)>>2]===final_data[2*i+1],"final DMEM/guard value");
                $fdisplay(observed_final,"%08h\n%08h",final_data[2*i],dmem[(final_data[2*i]-32'h10000000)>>2]);
            end
            $fclose(observed_trace);$fclose(observed_final);
            start=1;
            repeat(10) begin
                @(posedge clk);#1;
                check({busy,done,imem_en,dmem_en,u_dut.sram_en}===0,"Halt prohibits access/restart");
                check(u_dut.status===trace[(steps-1)*RW+3] && {24'd0,u_dut.error_code}===trace[(steps-1)*RW+4],"sticky first error");
                for(integer r=0;r<8;r++) check(u_dut.u_instruction_controller.u_register_file.registers[r]===trace[(steps-1)*RW+5+r],"Halt GPR");
                for(integer c=0;c<12;c++) check(u_dut.u_instruction_controller.u_csr.settings[c]===trace[(steps-1)*RW+13+c],"Halt CSR");
            end
            cases++;$display("[CASE] id=%0d result=PASS events=%0d timer=%0d",id,event_count,u_dut.u_instruction_controller.perf_count);
        end
        $fclose(meta);
        check(cases==EXPECTED_CASES && total_steps==EXPECTED_STEPS,"complete case/step counts");
        $display("[PHASE4] result=PASS capacity=%0d cases=%0d steps=%0d events=%0d checks=%0d",DMEM_BYTES,cases,total_steps,total_events,checks);
        $finish;
    end
    initial begin repeat(8000000) @(negedge clk);$fatal(1,"Phase 4 timeout");end
endmodule
