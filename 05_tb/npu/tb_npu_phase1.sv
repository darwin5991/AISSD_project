// Synchronous external IMEM, Python trace scoreboard, no SRAM access.
`timescale 1ns/1ps
module tb_npu_phase1;
    `include "npu_phase1_profile.vh"
    localparam integer RECORD_WORDS = 13;
    localparam integer MAX_STEPS = 4096;
    logic clk = 1'b0, rst_n = 1'b0, start = 1'b0;
    wire busy, done, fault, imem_en, dmem_en, dmem_we;
    wire [31:0] imem_addr, dmem_addr, dmem_wdata;
    logic [31:0] imem_rdata = 32'd0;
    logic [31:0] imem [0:IMEM_BYTES/4-1];
    logic [31:0] expected [0:MAX_STEPS*RECORD_WORDS-1];
    string data_dir, path;
    integer meta, scanned, case_id, steps, case_count = 0;
    integer checks = 0, total_steps = 0, step_index, age, cycles, fetches, done_pulses;
    bit pending, commit_now;
    logic [31:0] held_pc, held_regs [0:7], held_status;
    logic [7:0] held_error;
    always #5 clk = ~clk;
    npu_top #(.IMEM_BYTES(IMEM_BYTES), .DMEM_BYTES(DMEM_BYTES)) u_dut (
        .clk(clk), .rst_n(rst_n), .start(start), .busy(busy), .done(done), .fault(fault),
        .imem_en(imem_en), .imem_addr(imem_addr), .imem_rdata(imem_rdata),
        .dmem_en(dmem_en), .dmem_we(dmem_we), .dmem_addr(dmem_addr),
        .dmem_wdata(dmem_wdata), .dmem_rdata(32'hbad0_cafe)
    );

    task automatic check(input bit ok, input string reason);
        checks++;
        if (!ok) begin
            $display("[FAIL] case=%0d step=%0d time=%0t %s", case_id, step_index, $time, reason);
            $display("[ACTUAL] pc=%08h insn=%08h status=%0d error=%02h busy=%b done=%b fault=%b",
                u_dut.u_instruction_controller.pc, u_dut.u_instruction_controller.instruction,
                u_dut.status, u_dut.error_code, busy, done, fault);
            if (step_index >= 0 && step_index < steps) begin
                $display("[EXPECTED] fetch_pc=%08h insn=%08h next_pc=%08h status=%0d error=%02h",
                    expected[step_index*RECORD_WORDS], expected[step_index*RECORD_WORDS+1],
                    expected[step_index*RECORD_WORDS+2], expected[step_index*RECORD_WORDS+3],
                    expected[step_index*RECORD_WORDS+4]);
                for (integer r=0; r<8; r++)
                    $display("[GPR] r%0d actual=%08h expected=%08h", r,
                        u_dut.u_instruction_controller.u_register_file.registers[r],
                        expected[step_index*RECORD_WORDS+5+r]);
            end
            $fatal(1, "Phase 1 scoreboard mismatch");
        end
    endtask
    task automatic check_reset;
        check({busy, done, fault, imem_en} === 4'd0, "reset control");
        check(u_dut.status === 32'd0 && u_dut.error_code === 8'd0, "reset status/error");
        check(u_dut.u_instruction_controller.pc === 32'd0, "reset PC");
        for (integer r = 0; r < 8; r++)
            check(u_dut.u_instruction_controller.u_register_file.registers[r] === 32'd0, "reset GPR");
    endtask
    // Sample memory address at R; NBA updates rdata only after R. Capture is R+1.
    always @(posedge clk) begin
        if (rst_n && imem_en) begin
            if (imem_addr[1:0] !== 2'd0 || imem_addr >= IMEM_BYTES)
                $fatal(1, "invalid IMEM request addr=%h", imem_addr);
            imem_rdata <= imem[imem_addr >> 2];
        end
    end
    initial begin
        if (!$value$plusargs("DATA_DIR=%s", data_dir))
            $fatal(1, "missing DATA_DIR");
        meta = $fopen({data_dir, "/cases.txt"}, "r");
        if (meta == 0) $fatal(1, "cannot open cases.txt");
        while (!$feof(meta)) begin
            scanned = $fscanf(meta, "%d %d\n", case_id, steps);
            if (scanned != 2) $fatal(1, "invalid case metadata");
            check(steps > 0 && steps <= MAX_STEPS, "trace size");
            @(negedge clk);
            rst_n = 1'b0;
            start = 1'b0;
            for (integer i = 0; i < IMEM_BYTES/4; i++) imem[i] = 32'd0;
            path = $sformatf("%s/case_%0d.imem.hex", data_dir, case_id);
            $readmemh(path, imem);
            path = $sformatf("%s/case_%0d.trace.hex", data_dir, case_id);
            $readmemh(path, expected, 0, steps*RECORD_WORDS-1);
            repeat (3) @(negedge clk);
            #1; check_reset();
            rst_n = 1'b1;
            repeat (3) begin
                @(negedge clk);
                #1; check_reset(); // Releasing reset alone must not start.
            end
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;
            step_index = 0; age = 0; pending = 0;
            cycles = 0; fetches = 0; done_pulses = 0;
            while (step_index < steps) begin
                @(posedge clk);
                commit_now = 0;
                check({dmem_en, dmem_we, dmem_addr, dmem_wdata} === 66'd0, "unexpected DMEM access");
                if (imem_en) begin
                    check(!pending, "overlapping instruction fetch");
                    check(imem_addr === expected[step_index*RECORD_WORDS], "fetch PC");
                    check(imem[imem_addr >> 2] === expected[step_index*RECORD_WORDS+1], "machine word");
                    fetches++; pending = 1; age = 0;
                end else if (pending) begin
                    age++;
                    if (age == 2) commit_now = 1;
                end
                #1;
                check(u_dut.u_instruction_controller.u_register_file.registers[0] === 32'd0, "r0 invariant");
                if (pending && age == 1)
                    check(u_dut.u_instruction_controller.instruction === expected[step_index*RECORD_WORDS+1],
                        "R+1 instruction capture");
                if (commit_now) begin
                    check(u_dut.u_instruction_controller.pc === expected[step_index*RECORD_WORDS+2], "post-execute PC");
                    check(u_dut.status === expected[step_index*RECORD_WORDS+3], "STATUS");
                    check({24'd0,u_dut.error_code} === expected[step_index*RECORD_WORDS+4], "ERROR_CODE");
                    for (integer r = 0; r < 8; r++)
                        check(u_dut.u_instruction_controller.u_register_file.registers[r] ===
                            expected[step_index*RECORD_WORDS+5+r], $sformatf("GPR r%0d", r));
                    check(done === (expected[step_index*RECORD_WORDS+3] == 1), "done at END only");
                    check(fault === (expected[step_index*RECORD_WORDS+3] == 2), "sticky fault entry");
                    check(busy === (expected[step_index*RECORD_WORDS+3] == 0), "busy at commit");
                    $display("[STEP] profile=%0d case=%0d step=%0d pc=%08h insn=%08h next=%08h status=%0d error=%02h",
                        IMEM_BYTES,case_id,step_index,expected[step_index*RECORD_WORDS],
                        expected[step_index*RECORD_WORDS+1],u_dut.u_instruction_controller.pc,
                        u_dut.status,u_dut.error_code);
                    if (done) done_pulses++;
                    step_index++; total_steps++; pending = 0;
                end else begin
                    check(done === 1'b0 && fault === 1'b0, "premature completion");
                    check(busy === 1'b1, "busy during fetch/execute");
                end
                cycles++;
                check(cycles <= steps*3+5, "cycle timeout");
                @(negedge clk);
                // Deliberately inject extra starts while busy; these must be ignored.
                start = (cycles % 5 == 0);
            end
            check(fetches == steps, "fetch count");
            check(done_pulses == ((u_dut.status == 1) ? 1 : 0), "done pulse count");
            held_pc = u_dut.u_instruction_controller.pc;
            held_status = u_dut.status; held_error = u_dut.error_code;
            for (integer r=0; r<8; r++) held_regs[r] = u_dut.u_instruction_controller.u_register_file.registers[r];
            start = 1'b1;
            repeat (12) begin
                @(posedge clk); #1;
                check({busy,done,imem_en,dmem_en,dmem_we} === 5'd0, "Halt activity/start ignored");
                check(fault === (held_status == 2), "fault held");
                check(u_dut.status === held_status && u_dut.error_code === held_error, "first error sticky");
                check(u_dut.u_instruction_controller.pc === held_pc, "Halt PC");
                for (integer r=0; r<8; r++)
                    check(u_dut.u_instruction_controller.u_register_file.registers[r] === held_regs[r], "Halt GPR");
            end
            case_count++;
            $display("[CASE] id=%0d result=PASS steps=%0d",case_id,steps);
        end
        $fclose(meta);
        // Abort a request in flight with asynchronous reset, then remain idle.
        @(negedge clk); rst_n=0; start=0; #1; check_reset();
        imem[0]=32'h0010_0093; // ADDI r1,r0,1
        @(negedge clk); rst_n=1; start=1;
        @(negedge clk); start=0;
        @(posedge clk); // accepted request
        @(negedge clk); rst_n=0;
        #1; check_reset();
        @(negedge clk); rst_n=1;
        repeat (3) begin @(negedge clk); #1; check_reset(); end
        check(case_count == EXPECTED_CASES, "case count");
        check(total_steps == EXPECTED_STEPS, "total trace count");
        $display("[PHASE1] result=PASS profile=%0d cases=%0d steps=%0d checks=%0d",IMEM_BYTES,case_count,total_steps,checks);
        $finish;
    end
    initial begin
        repeat (200000) @(negedge clk);
        $fatal(1,"global Phase 1 timeout");
    end
endmodule
