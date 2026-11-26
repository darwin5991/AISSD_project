module external_dmem(input logic clk,en,we,input logic [31:0] addr,wdata,output logic [31:0] rdata);
logic [31:0] words[0:4194303];
integer writes[0:4194303];
string file_name; integer count,dump_base,dump_words,fd;
initial begin
    rdata=0;
    for(integer i=0;i<4194304;i=i+1) begin words[i]=0;writes[i]=0;end
    if(!$value$plusargs("DMEM=%s",file_name) || !$value$plusargs("DMEM_WORDS=%d",count) ||
       !$value$plusargs("DUMP_BASE=%d",dump_base) || !$value$plusargs("DUMP_WORDS=%d",dump_words)) $fatal(1,"DMEM args");
    $readmemh(file_name,words,0,count-1);
end
always @(posedge clk) if(en) begin
    if(we) begin words[(addr-32'h10000000)>>2]<=wdata;writes[(addr-32'h10000000)>>2]<=writes[(addr-32'h10000000)>>2]+1;end
    else rdata<=words[(addr-32'h10000000)>>2];
end
task dump_results;
    integer idx;
    begin
        if(!$value$plusargs("OUTPUT=%s",file_name)) $fatal(1,"OUTPUT arg");
        fd=$fopen(file_name,"w"); if(!fd) $fatal(1,"output open");
        for(integer i=0;i<dump_words;i=i+1) begin
            idx=(dump_base-32'h10000000)/4+i;
            if(writes[idx]!=1) $fatal(1,"result word %0d write count %0d",i,writes[idx]);
            $fdisplay(fd,"%08x",words[idx]);
        end
        $fclose(fd);
    end
endtask
endmodule
