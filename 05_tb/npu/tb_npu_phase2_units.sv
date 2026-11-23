`timescale 1ns/1ps
module tb_npu_phase2_units;
    logic clk=0, rst_n=0;
    always #5 clk=~clk;
    logic timer_start=0,timer_stop=0,load_active=0,gemm_active=0;
    wire [31:0] count;
    wire overflow,armed;
    perf_timer u_timer(.*);
    logic access_en=0,write_request=0,commit_en=0;
    logic [11:0] address=0;
    logic [31:0] write_data=0,perf_count=32'hffff_ffe3,status=0;
    logic perf_overflow=1;
    logic [7:0] error_code=0;
    wire [31:0] read_data;
    wire [7:0] access_error;
    csr_file u_csr(.*);
    integer checks=0, timer_edges=0;
    logic [31:0] expected_settings[0:11];
    logic [31:0] ref_count=0, pattern, random_state=32'hc0de_1234;
    bit ref_overflow=0, ref_armed=0;
    integer index;
    function automatic integer slot(input integer a);
        if (a>=12'h7c0 && a<=12'h7c9) slot=a-12'h7c0;
        else if(a==12'h7e0) slot=10;
        else if(a==12'h7e1) slot=11;
        else slot=-1;
    endfunction
    function automatic integer csr_addr(input integer i);
        if(i<10) csr_addr=12'h7c0+i;
        else csr_addr=12'h7e0+i-10;
    endfunction
    function automatic bit is_ro(input integer a);
        is_ro=(a>=12'h7f0 && a<=12'h7f3);
    endfunction
    task automatic check(input bit ok,input string reason);
        checks++;
        if(!ok) begin
            $display("[FAIL] %s address=%03h read=%08h error=%02h timer=%08h expected_timer=%08h overflow=%b/%b armed=%b/%b",
                reason,address,read_data,access_error,count,ref_count,overflow,ref_overflow,armed,ref_armed);
            $fatal(1,"Phase 2 unit failure");
        end
    endtask
    task automatic read_setting(input integer i);
        @(negedge clk); access_en=1; write_request=0; commit_en=0; address=csr_addr(i);
        #1; check(access_error===0,"RW read address");
        check(read_data===expected_settings[i],$sformatf("RW value slot=%0d expected=%08h",i,expected_settings[i]));
    endtask
    task automatic tick(input bit ts,input bit tp,input bit la,input bit ga);
        @(negedge clk); timer_start=ts;timer_stop=tp;load_active=la;gemm_active=ga;
        @(posedge clk);
        if(ts) begin ref_count=0;ref_overflow=0;ref_armed=1; end
        else if(tp) ref_armed=0;
        else if(ref_armed && (la || ga)) begin
            if(ref_count==32'hffff_ffff) ref_overflow=1;
            ref_count=ref_count+32'd1;
        end
        #1;
        check(count===ref_count,"Timer count");
        check(overflow===ref_overflow,"Timer overflow");
        check(armed===ref_armed,"Timer armed");
        timer_edges++;
        $display("[TIMER_EDGE] start=%b stop=%b load=%b gemm=%b count=%08h overflow=%b armed=%b",
            ts,tp,la,ga,count,overflow,armed);
    endtask
    initial begin
        for(integer i=0;i<12;i++) expected_settings[i]=0;
        repeat(3) @(negedge clk);
        #1;check(count===0 && overflow===0 && armed===0,"reset Timer");
        rst_n=1;
        for(integer i=0;i<12;i++) read_setting(i);
        // Exhaustive address and write-permission check over all 4096 CSR IDs.
        for(integer a=0;a<4096;a++) begin
            @(negedge clk); address=a; access_en=1;write_request=0;commit_en=0;
            #1;check(access_error===((slot(a)>=0 || is_ro(a)) ? 8'd0 : 8'd3),"all-CSR read permission");
            if(slot(a)>=0) check(read_data===expected_settings[slot(a)],"all-CSR read value");
            @(negedge clk); write_request=1;commit_en=1;write_data=32'hdead_beef ^ a;
            #1;check(access_error===((slot(a)>=0) ? 8'd0 : 8'd3),"all-CSR write permission");
            @(posedge clk); #1;
            if(slot(a)>=0) expected_settings[slot(a)]=write_data;
        end
        for(integer i=0;i<12;i++) read_setting(i);
        // Combinational access validation must not itself commit a write.
        @(negedge clk);address=12'h7c4;write_request=1;write_data=32'hffff_ffff;commit_en=0;
        @(posedge clk);#1;check(access_error===0,"D01 no value validation");
        read_setting(4);
        @(negedge clk);access_en=0;write_request=1;commit_en=1;
        @(posedge clk);#1;
        read_setting(4);
        // Read-only live views, including Halt status/error values.
        for(integer s=0;s<3;s++) begin
            @(negedge clk);status=s;error_code=(s==2)?8'h08:8'h00;
            access_en=1;write_request=0;commit_en=0;
            address=12'h7f0;#1;check(read_data===perf_count,"PERF_COUNT full width");
            address=12'h7f1;#1;check(read_data===32'd1,"overflow zero extension");
            address=12'h7f2;#1;check(read_data===status,"STATUS live read");
            address=12'h7f3;#1;check(read_data==={24'd0,error_code},"ERROR_CODE zero extension");
        end
        @(negedge clk);access_en=0;write_request=0;commit_en=0;
        // Unarmed activity, scalar/idle gaps, overlapping active inputs, final edge.
        tick(0,0,1,1);
        tick(1,0,1,1);
        repeat(4) tick(0,0,0,0);
        repeat(3) tick(0,0,1,0);
        repeat(2) tick(0,0,0,1);
        repeat(2) tick(0,0,1,1); // OR: one increment per edge, not two.
        tick(0,0,1,0); // final active edge included
        tick(0,0,0,0);
        tick(0,1,1,1); // TSTOP edge excluded
        repeat(3) tick(0,0,1,1);
        tick(1,0,0,0);
        tick(0,0,1,0);
        tick(1,0,1,1); // restart clears count/overflow even if active
        // TB-only seed: no synthesizable counter-load port/CSR/parameter.
        @(negedge clk);
        timer_start=0;timer_stop=0;load_active=0;gemm_active=0;
        force u_timer.count=32'hffff_fffe;
        #1;release u_timer.count;ref_count=32'hffff_fffe;
        #1;check(count===ref_count,"TB overflow seed retained");
        tick(0,0,1,0);
        tick(0,0,0,1);
        tick(0,0,0,0);
        tick(0,1,1,1);
        tick(0,0,1,1);
        tick(1,0,0,0);
        for(integer i=0;i<128;i++) begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            tick(i%29==0,(i%17==0)&&(i%29!=0),random_state[0],random_state[1]);
        end
        @(negedge clk);rst_n=0;
        #1;check(count===0 && overflow===0 && armed===0,"asynchronous timer reset");
        for(integer i=0;i<12;i++)
            check(u_csr.settings[i]===0,"asynchronous CSR reset");
        $display("[PHASE2_UNITS] result=PASS csr_addresses=4096 timer_edges=%0d checks=%0d",timer_edges,checks);
        $finish;
    end
    initial begin repeat(20000) @(negedge clk);$fatal(1,"unit timeout");end
endmodule
