module external_imem(input logic clk,en,input logic [31:0] addr,output logic [31:0] rdata);
logic [31:0] words[0:16383];
string file_name; integer count;
initial begin
    rdata=0; for(integer i=0;i<16384;i=i+1) words[i]=0;
    if(!$value$plusargs("IMEM=%s",file_name) || !$value$plusargs("IMEM_WORDS=%d",count)) $fatal(1,"IMEM args");
    $readmemh(file_name,words,0,count-1);
end
always @(posedge clk) if(en) words_read();
task words_read; begin rdata<=words[addr>>2]; end endtask
endmodule
