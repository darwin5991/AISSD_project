`timescale 1ns/1ps
module tb_npu_phase6;
    `include "npu_phase6_profile.vh"
    localparam integer RW=29,MAX_STEPS=1024,MAX_EVENTS=524288,MAX_FINAL=262144,MAX_CONTROL=131072,MAX_NUMERIC=65536;
    logic clk=0,rst_n=0,start=0;
    always #5 clk=~clk;
    wire busy,done,fault,imem_en,dmem_en,dmem_we;
    wire [31:0] imem_addr,dmem_addr,dmem_wdata;
    logic [31:0] imem_rdata=0,dmem_rdata=0;
    logic [31:0] imem[0:IMEM_BYTES/4-1],dmem[0:DMEM_BYTES/4-1];
    logic [31:0] trace[0:MAX_STEPS*RW-1],events[0:MAX_EVENTS*5-1],final_data[0:MAX_FINAL*2-1];
    logic [31:0] control_data[0:MAX_CONTROL*3-1],numeric_data[0:MAX_NUMERIC*10-1];
    logic [31:0] arg_data[0:4096*10-1];
    integer arg_count,arg_index,observed_arg,total_args=0;
    integer saved_steps,saved_events,saved_controls,saved_numeric,saved_args,reset_aborts=0;
    bit is_arg,arg_consume;
    integer arg_offset;
    logic [31:0] expected_timer;
    wire [31:0] probe_acc[0:3],probe_result[0:3];
    wire [31:0] probe_a=u_dut.u_memory.ram_rdata[0];
    wire [31:0] probe_b=u_dut.u_memory.ram_rdata[1];
    string data_dir,path;
    integer meta,scanned,id,steps,event_count,final_count,control_count,numeric_count,hook;
    integer checks=0,cases=0,total_steps=0,total_events=0,total_controls=0,total_numeric=0;
    integer step_index,event_index,control_index,numeric_index,age,cycles,done_count;
    integer observed_trace,observed_final,observed_numeric;
    bit pending,commit_now,want_load,want_gemm,injected,restored,forced_csr;
    bit ext_read;
    logic [6:0] read_banks;
    logic [31:0] word,fetched_pc,read_hold,ext_expected,expected_read[0:6],ram_hold[0:6];
    logic [4:0] wanted_control,actual_control;
    npu_top #(.IMEM_BYTES(IMEM_BYTES),.DMEM_BYTES(DMEM_BYTES)) u_dut(.*);
    for(genvar l=0;l<4;l++) begin:g_probe
        assign probe_acc[l]=u_dut.u_gemm.u_accumulator.g_accumulator[l].u_lane.acc32;
        assign probe_result[l]=u_dut.u_gemm.u_accumulator.g_accumulator[l].u_lane.result32;
    end
    task automatic check(input bit ok,input string reason);
        checks++;
        if(!ok) begin
            $display("[FAIL] case=%0d step=%0d age=%0d event=%0d time=%0t %s pc=%08h error=%02h",
                id,step_index,age,event_index,$time,reason,u_dut.u_instruction_controller.pc,u_dut.error_code);
            $fatal(1,"Phase 6 scoreboard mismatch");
        end
    endtask
    task automatic observe(input integer kind,input logic [31:0] address,input logic [31:0] data);
        integer offset,b;
        begin
            check(event_index<event_count,"unexpected memory request");
            offset=event_index*5;
            check(events[offset]==step_index && events[offset+1]==age,"memory event edge");
            check(events[offset+2]==kind && events[offset+3]===address,"memory event kind/address");
            if(kind==1 || kind==3) check(data===events[offset+4],$sformatf("write value actual=%08h expected=%08h",data,events[offset+4]));
            else if(kind==0) begin ext_read=1;ext_expected=events[offset+4];end
            else begin b=address[19:17];read_banks[b]=1;expected_read[b]=events[offset+4];end
            event_index++;total_events++;
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
                if(dmem_we)dmem[(dmem_addr-32'h10000000)>>2]<=dmem_wdata;
                else dmem_rdata<=dmem[(dmem_addr-32'h10000000)>>2];
            end
        end
    end
    initial begin
        if(!$value$plusargs("DATA_DIR=%s",data_dir)) $fatal(1,"DATA_DIR required");
        meta=$fopen({data_dir,"/cases.txt"},"r");
        if(!meta)$fatal(1,"metadata missing");
        while(!$feof(meta)) begin
            scanned=$fscanf(meta,"%d %d %d %d %d %d %d %d\n",id,steps,event_count,final_count,control_count,numeric_count,arg_count,hook);
            if(scanned!=8)$fatal(1,"metadata invalid");
            check(steps>0 && steps<=MAX_STEPS && event_count<=MAX_EVENTS && final_count<=MAX_FINAL &&
                control_count<=MAX_CONTROL && numeric_count<=MAX_NUMERIC && arg_count<=4096,"fixture capacity");
            saved_steps=total_steps;saved_events=total_events;saved_controls=total_controls;
            saved_numeric=total_numeric;saved_args=total_args;
            @(negedge clk);rst_n=0;start=0;
            for(integer i=0;i<IMEM_BYTES/4;i++)imem[i]=0;
            for(integer i=0;i<DMEM_BYTES/4;i++)dmem[i]=0;
            path=$sformatf("%s/case_%0d.imem.hex",data_dir,id);$readmemh(path,imem);
            path=$sformatf("%s/case_%0d.dmem.hex",data_dir,id);$readmemh(path,dmem);
            path=$sformatf("%s/case_%0d.trace.hex",data_dir,id);$readmemh(path,trace,0,steps*RW-1);
            if(event_count>0)begin path=$sformatf("%s/case_%0d.bus.hex",data_dir,id);$readmemh(path,events,0,event_count*5-1);end
            if(final_count>0)begin path=$sformatf("%s/case_%0d.final.hex",data_dir,id);$readmemh(path,final_data,0,final_count*2-1);end
            if(control_count>0)begin path=$sformatf("%s/case_%0d.control.hex",data_dir,id);$readmemh(path,control_data,0,control_count*3-1);end
            if(numeric_count>0)begin path=$sformatf("%s/case_%0d.numeric.hex",data_dir,id);$readmemh(path,numeric_data,0,numeric_count*10-1);end
            if(arg_count>0)begin path=$sformatf("%s/case_%0d.arg.hex",data_dir,id);$readmemh(path,arg_data,0,arg_count*10-1);end
            path=$sformatf("%s/case_%0d.observed_arg.hex",data_dir,id);observed_arg=$fopen(path,"w");
            path=$sformatf("%s/case_%0d.observed_trace.hex",data_dir,id);observed_trace=$fopen(path,"w");
            path=$sformatf("%s/case_%0d.observed_final.hex",data_dir,id);observed_final=$fopen(path,"w");
            path=$sformatf("%s/case_%0d.observed_numeric.hex",data_dir,id);observed_numeric=$fopen(path,"w");
            if(!observed_trace || !observed_final || !observed_numeric || !observed_arg)$fatal(1,"cannot write observed results");
            repeat(3)@(negedge clk);
            #1;check({busy,done,fault,imem_en,dmem_en,u_dut.gemm_active,u_dut.argmax_active,u_dut.argmax_en}===0,"reset outputs");
            for(integer r=0;r<8;r++)check(u_dut.u_instruction_controller.u_register_file.registers[r]===0,"reset GPR");
            for(integer c=0;c<12;c++)check(u_dut.u_instruction_controller.u_csr.settings[c]===0,"reset CSR");
            rst_n=1;start=1;@(negedge clk);start=0;
            step_index=0;event_index=0;control_index=0;numeric_index=0;arg_index=0;pending=0;
            injected=0;restored=0;forced_csr=0;age=0;cycles=0;done_count=0;
            while(step_index<steps) begin
                @(posedge clk);
                if(imem_en) begin
                    check(!pending,"fetch before completion");
                    check(imem_addr===trace[step_index*RW],"fetch PC");
                    word=imem[imem_addr>>2];fetched_pc=imem_addr;
                    check(word===trace[step_index*RW+1],"instruction");
                    pending=1;age=0;
                end else if(pending)age++;
                commit_now=pending && age==trace[step_index*RW+28];
                want_load=pending && word[6:0]==7'h2b && word[14:12]==0 && age>=4 && age<trace[step_index*RW+28];
                want_gemm=pending && word==32'h0000202b && age>=5 && age<trace[step_index*RW+28];
                check(u_dut.xfer_load_active===want_load,"LOAD active unchanged");
                check(u_dut.gemm_active===want_gemm,"GEMM active PREP through last write/abort");
                check(u_dut.gemm_start===(pending && word==32'h0000202b && age==4 && trace[step_index*RW+28]>3),"one validated engine start");
                if(pending && word==32'h0000202b && age>=3)
                    for(integer c=0;c<10;c++)check(u_dut.gemm_config[c]===trace[step_index*RW+13+c],"atomic stable snapshot");
                is_arg=pending && ((word & 32'hfffff07f)==32'h0200202b);
                check(u_dut.argmax_start===(is_arg && age==4 && trace[step_index*RW+28]>3),"ARGMAX one prevalidated start");
                check(u_dut.argmax_active===(is_arg && age>=5 && age<trace[step_index*RW+28]),"ARGMAX active READ through last compare");
                check(u_dut.argmax_done===(is_arg && trace[step_index*RW+4]==0 && trace[step_index*RW+28]>3 && age==trace[step_index*RW+28]),"ARGMAX done after final compare");
                check(u_dut.u_instruction_controller.argmax_writeback===
                    (is_arg && trace[step_index*RW+4]==0 && trace[step_index*RW+28]>3 && age==trace[step_index*RW+28] && word[11:7]!=0),"delayed ARGMAX GPR write only");
                check(int'(u_dut.argmax_active)+int'(u_dut.gemm_active)+int'(u_dut.xfer_busy)<=1,"one SRAM owner");
                if(u_dut.argmax_active)begin
                    check(u_dut.u_memory.owner==npu_memory_pkg::OWNER_ARGMAX,"ARGMAX owner");
                    check(dmem_en===0 && u_dut.u_memory.ram_we===0 &&
                          u_dut.u_memory.ram_en[6:2]===0,"ARGMAX read-only Buffer path");
                end
                if(is_arg && age>=3 && trace[step_index*RW+28]>=3)begin
                    for(integer c=0;c<2;c++)check(u_dut.argmax_config[c]===trace[step_index*RW+23+c],"both raw CSR snapshots stable");
                    check(u_dut.u_instruction_controller.argmax_rd===word[11:7],"rd snapshot");
                end
                if(is_arg && trace[step_index*RW+4]!=0 && trace[step_index*RW+28]<=3)begin
                    check(u_dut.argmax_start===0 && u_dut.argmax_en===0 && dmem_en===0 &&
                          u_dut.u_memory.ram_en===0 && u_dut.u_instruction_controller.register_write===0,"preflight rejects all accesses/writes");
                end
                if(hook==11 && forced_csr)begin
                    check(u_dut.u_instruction_controller.u_csr.settings[10]===32'h80040001 &&
                          u_dut.u_instruction_controller.u_csr.settings[11]===32'hffffffff,"both live CSR mutations observed");
                    if(age==3)$display("[ARG_SNAPSHOT] live_src=%08h live_len=%08h snapshot_src=%08h snapshot_len=%08h",
                        u_dut.u_instruction_controller.u_csr.settings[10],u_dut.u_instruction_controller.u_csr.settings[11],
                        u_dut.argmax_config[0],u_dut.argmax_config[1]);
                end
                arg_consume=0;arg_offset=arg_index*10;
                if(arg_index<arg_count && arg_data[arg_offset]==step_index && arg_data[arg_offset+1]==age)begin
                    arg_consume=1;
                    check(u_dut.u_argmax.index===arg_data[arg_offset+2],"ARGMAX element index/word boundary");
                    check(u_dut.argmax_rdata===arg_data[arg_offset+3],"ARGMAX held word R+1 consume");
                    check({{24{u_dut.u_argmax.u_compare.candidate[7]}},u_dut.u_argmax.u_compare.candidate}===
                        arg_data[arg_offset+4],"signed byte extraction");
                    check({{24{u_dut.u_argmax.u_compare.max_value[7]}},u_dut.u_argmax.u_compare.max_value}===
                        arg_data[arg_offset+5],"old signed maximum");
                    check({31'd0,u_dut.u_argmax.u_compare.greater}===arg_data[arg_offset+6],"strict signed greater/tie");
                    check({31'd0,u_dut.u_argmax.initialize}===arg_data[arg_offset+7],"first element unconditional initialize");
                    check(u_dut.u_argmax.compare_en===(arg_data[arg_offset+2]!=0),"compare only after first");
                    $fdisplay(observed_arg,"%08h\n%08h\n%08h\n%08h\n%08h\n%08h\n%08h\n%08h",
                        step_index,age,{28'd0,u_dut.u_argmax.index},u_dut.argmax_rdata,
                        {{24{u_dut.u_argmax.u_compare.candidate[7]}},u_dut.u_argmax.u_compare.candidate},
                        {{24{u_dut.u_argmax.u_compare.max_value[7]}},u_dut.u_argmax.u_compare.max_value},
                        {31'd0,u_dut.u_argmax.u_compare.greater},{31'd0,u_dut.u_argmax.initialize});
                end
                check((u_dut.u_argmax.initialize || u_dut.u_argmax.compare_en)===arg_consume,"exactly LEN consumers, no padding compare");
                wanted_control=0;
                if(control_index<control_count && control_data[control_index*3]==step_index &&
                   control_data[control_index*3+1]==age)begin
                    wanted_control=control_data[control_index*3+2][4:0];control_index++;total_controls++;
                end
                actual_control={|u_dut.gemm_we,u_dut.u_gemm.result_load,u_dut.u_gemm.bias_load,
                    u_dut.u_gemm.u_accumulator.psum_valid,u_dut.u_gemm.mac_input_valid};
                check(actual_control===wanted_control,"R+1/R+4/R+5/R+6 and bias schedule");
                check(!(u_dut.u_gemm.bias_load && u_dut.u_gemm.u_accumulator.psum_valid),"no bias/psum overlap");
                check(!(dmem_en && u_dut.gemm_active),"GEMM does not access DMEM");
                read_hold=dmem_rdata;ext_read=0;read_banks=0;
                for(integer b=0;b<7;b++)ram_hold[b]=u_dut.u_memory.ram_rdata[b];
                if(dmem_en)observe(dmem_we?1:0,dmem_addr,dmem_wdata);
                for(integer b=0;b<7;b++)if(u_dut.u_memory.ram_en[b])
                    observe(u_dut.u_memory.ram_we[b]?3:2,32'h80000000+(b<<17)+{15'd0,u_dut.u_memory.ram_addr[b],2'd0},
                        u_dut.u_memory.ram_wdata[b]);
                if(event_index<event_count && events[event_index*5]==step_index && events[event_index*5+1]==age)
                    check(0,"missing memory request");
                #1;
                check(dmem_rdata===(ext_read?ext_expected:read_hold),"DMEM registered response/hold");
                for(integer b=0;b<7;b++)
                    check(u_dut.u_memory.ram_rdata[b]===(read_banks[b]?expected_read[b]:ram_hold[b]),"SRAM 1clk response/hold");
                if(arg_consume)begin
                    check({{24{u_dut.u_argmax.u_compare.max_value[7]}},u_dut.u_argmax.u_compare.max_value}===
                        arg_data[arg_offset+8],"new signed maximum");
                    check({28'd0,u_dut.argmax_result}===arg_data[arg_offset+9],"lowest index/final comparison");
                    $fdisplay(observed_arg,"%08h\n%08h",
                        {{24{u_dut.u_argmax.u_compare.max_value[7]}},u_dut.u_argmax.u_compare.max_value},
                        {28'd0,u_dut.argmax_result});
                    arg_index++;total_args++;
                end
                if(is_arg)begin
                    expected_timer=(hook==12 && injected)?32'hfffffffe:
                        ((step_index==0)?32'd0:trace[(step_index-1)*RW+25]);
                    check(u_dut.u_instruction_controller.perf_count===expected_timer,"ARGMAX never counts");
                    check({31'd0,u_dut.u_instruction_controller.perf_overflow}===
                        ((hook==12 && injected)?32'd1:((step_index==0)?32'd0:trace[(step_index-1)*RW+26])),"ARGMAX overflow held");
                    check({31'd0,u_dut.u_instruction_controller.timer_armed}===
                        ((hook==12 && injected)?32'd1:((step_index==0)?32'd0:trace[(step_index-1)*RW+27])),"ARGMAX armed held");
                end
                if(numeric_index<numeric_count && numeric_data[numeric_index*10]==step_index &&
                   numeric_data[numeric_index*10+1]==age)begin
                    $fdisplay(observed_numeric,"%08h\n%08h",step_index,age);
                    for(integer l=0;l<4;l++)begin
                        check(probe_acc[l]===numeric_data[numeric_index*10+2+l],$sformatf("INT32 acc lane%0d actual=%08h expected=%08h",l,probe_acc[l],numeric_data[numeric_index*10+2+l]));
                        $fdisplay(observed_numeric,"%08h",probe_acc[l]);
                    end
                    for(integer l=0;l<4;l++)begin
                        check(probe_result[l]===numeric_data[numeric_index*10+6+l],"result captures old completed accumulator");
                        $fdisplay(observed_numeric,"%08h",probe_result[l]);
                    end
                    numeric_index++;total_numeric++;
                end
                check(u_dut.u_instruction_controller.u_register_file.registers[0]===0,"r0");
                if(!commit_now)begin
                    check(u_dut.u_instruction_controller.pc===fetched_pc,"PC stable before complete");
                    for(integer r=0;r<8;r++)check(u_dut.u_instruction_controller.u_register_file.registers[r]===
                        ((step_index==0)?32'd0:trace[(step_index-1)*RW+5+r]),"no early GPR update");
                    for(integer c=0;c<12;c++)if(!(forced_csr && (c==10 || c==11)))
                        check(u_dut.u_instruction_controller.u_csr.settings[c]===
                            ((step_index==0)?32'd0:trace[(step_index-1)*RW+13+c]),"no early CSR update");
                end
                if(commit_now)begin
                    check(u_dut.u_instruction_controller.pc===trace[step_index*RW+2],"next PC");
                    check(u_dut.status===trace[step_index*RW+3] && {24'd0,u_dut.error_code}===trace[step_index*RW+4],"status/error");
                    for(integer r=0;r<8;r++)check(u_dut.u_instruction_controller.u_register_file.registers[r]===trace[step_index*RW+5+r],"GPR");
                    for(integer c=0;c<12;c++)check(u_dut.u_instruction_controller.u_csr.settings[c]===trace[step_index*RW+13+c],"raw CSR");
                    check(u_dut.u_instruction_controller.perf_count===trace[step_index*RW+25],"Timer exact");
                    check({31'd0,u_dut.u_instruction_controller.perf_overflow}===trace[step_index*RW+26],"Timer overflow");
                    check({31'd0,u_dut.u_instruction_controller.timer_armed}===trace[step_index*RW+27],"Timer armed");
                    check(done===(trace[step_index*RW+3]==1) && fault===(trace[step_index*RW+3]==2),"GEMM done differs from END/Fault");
                    check(busy===(trace[step_index*RW+3]==0),"busy");
                    $fdisplay(observed_trace,"%08h\n%08h\n%08h\n%08h\n%08h",fetched_pc,word,u_dut.u_instruction_controller.pc,u_dut.status,{24'd0,u_dut.error_code});
                    for(integer r=0;r<8;r++)$fdisplay(observed_trace,"%08h",u_dut.u_instruction_controller.u_register_file.registers[r]);
                    for(integer c=0;c<12;c++)$fdisplay(observed_trace,"%08h",u_dut.u_instruction_controller.u_csr.settings[c]);
                    $fdisplay(observed_trace,"%08h\n%08h\n%08h\n%08h",u_dut.u_instruction_controller.perf_count,
                        {31'd0,u_dut.u_instruction_controller.perf_overflow},{31'd0,u_dut.u_instruction_controller.timer_armed},age);
                    if(done)done_count++;
                    step_index++;total_steps++;pending=0;
                end
                cycles++;check(cycles<1000000,"timeout");
                @(negedge clk);
                if(hook==11 && is_arg && pending)begin
                    if(!injected && age==2)begin
                        u_dut.u_instruction_controller.u_csr.settings[10]=32'h80040001;
                        u_dut.u_instruction_controller.u_csr.settings[11]=32'hffffffff;
                        injected=1;forced_csr=1;
                    end
                    if(injected && !restored && age==10)begin
                        u_dut.u_instruction_controller.u_csr.settings[10]=trace[step_index*RW+23];
                        u_dut.u_instruction_controller.u_csr.settings[11]=trace[step_index*RW+24];
                        restored=1;forced_csr=0;
                    end
                end
                if(hook==12 && !injected && is_arg && pending && age==3)begin
                    // Test-only seed; no synthesizable counter-write path.
                    force u_dut.u_instruction_controller.u_timer.count=32'hfffffffe;
                    force u_dut.u_instruction_controller.u_timer.overflow=1'b1;
                    #1;release u_dut.u_instruction_controller.u_timer.count;
                    release u_dut.u_instruction_controller.u_timer.overflow;injected=1;
                end
                if(hook==14 && !injected && is_arg && pending && age==6)begin
                    force u_dut.u_argmax.index=4'd15;injected=1;
                end
                if(hook==13 && !injected && is_arg && pending && age==6)begin
                    rst_n=0;start=0;#1;
                    check({busy,done,fault,imem_en,dmem_en,u_dut.argmax_active,u_dut.argmax_en,
                           u_dut.u_instruction_controller.register_write}===0,"asynchronous in-flight ARGMAX abort");
                    for(integer r=0;r<8;r++)check(u_dut.u_instruction_controller.u_register_file.registers[r]===0,"abort GPR reset");
                    for(integer c=0;c<12;c++)check(u_dut.u_instruction_controller.u_csr.settings[c]===0,"abort CSR reset");
                    check(u_dut.u_instruction_controller.perf_count===0,"abort Timer reset");
                    repeat(3)@(negedge clk);
                    step_index=0;event_index=0;control_index=0;numeric_index=0;arg_index=0;pending=0;
                    total_steps=saved_steps;total_events=saved_events;total_controls=saved_controls;
                    total_numeric=saved_numeric;total_args=saved_args;done_count=0;cycles=0;age=0;fetched_pc=0;
                    $fclose(observed_trace);$fclose(observed_numeric);$fclose(observed_arg);
                    path=$sformatf("%s/case_%0d.observed_trace.hex",data_dir,id);observed_trace=$fopen(path,"w");
                    path=$sformatf("%s/case_%0d.observed_numeric.hex",data_dir,id);observed_numeric=$fopen(path,"w");
                    path=$sformatf("%s/case_%0d.observed_arg.hex",data_dir,id);observed_arg=$fopen(path,"w");
                    check(observed_trace!=0 && observed_numeric!=0 && observed_arg!=0,"restart dumps");
                    injected=1;restored=1;reset_aborts++;
                    rst_n=1;start=1;@(negedge clk);start=0;
                end
                start=(cycles%7==0);
            end
            if(hook==14)release u_dut.u_argmax.index;
            if(hook!=0)check(injected && (hook!=11 || restored),"test hook executed/restored");
            check(event_index==event_count && control_index==control_count && numeric_index==numeric_count && arg_index==arg_count,"complete traces");
            check(done_count==((u_dut.status==1)?1:0),"END pulse count");
            for(integer i=0;i<final_count;i++)begin
                check(dmem[(final_data[2*i]-32'h10000000)>>2]===final_data[2*i+1],"final DMEM/guard");
                $fdisplay(observed_final,"%08h\n%08h",final_data[2*i],dmem[(final_data[2*i]-32'h10000000)>>2]);
            end
            $fclose(observed_trace);$fclose(observed_final);$fclose(observed_numeric);$fclose(observed_arg);
            start=1;
            repeat(10)begin
                @(posedge clk);#1;
                check({busy,done,imem_en,dmem_en,u_dut.gemm_active,u_dut.sram_en,u_dut.argmax_active,u_dut.argmax_en,u_dut.u_instruction_controller.register_write}===0,"halt prevents restart/access");
                check(u_dut.u_instruction_controller.pc===trace[(steps-1)*RW+2],"Halt PC");
                check(u_dut.u_instruction_controller.perf_count===trace[(steps-1)*RW+25] &&
                      {31'd0,u_dut.u_instruction_controller.perf_overflow}===trace[(steps-1)*RW+26] &&
                      {31'd0,u_dut.u_instruction_controller.timer_armed}===trace[(steps-1)*RW+27],"Halt Timer state");
                check(u_dut.status===trace[(steps-1)*RW+3] && {24'd0,u_dut.error_code}===trace[(steps-1)*RW+4],"sticky status/error");
                for(integer r=0;r<8;r++)check(u_dut.u_instruction_controller.u_register_file.registers[r]===trace[(steps-1)*RW+5+r],"Halt GPR");
                for(integer c=0;c<12;c++)check(u_dut.u_instruction_controller.u_csr.settings[c]===trace[(steps-1)*RW+13+c],"Halt CSR");
            end
            cases++;$display("[CASE] id=%0d result=PASS events=%0d controls=%0d numeric=%0d timer=%0d",id,event_count,control_count,numeric_count,u_dut.u_instruction_controller.perf_count);
        end
        $fclose(meta);
        check(cases==EXPECTED_CASES && total_steps==EXPECTED_STEPS,"case/step totals");
        $display("[PHASE6] result=PASS capacity=%0d cases=%0d steps=%0d events=%0d controls=%0d numeric=%0d checks=%0d args=%0d reset_aborts=%0d",
            DMEM_BYTES,cases,total_steps,total_events,total_controls,total_numeric,checks,total_args,reset_aborts);
        $finish;
    end
    initial begin repeat(8000000)@(negedge clk);$fatal(1,"Phase 6 timeout");end
endmodule
