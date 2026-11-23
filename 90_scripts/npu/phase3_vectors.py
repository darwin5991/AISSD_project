"""Independent Phase 3 block transfer fixtures and ISA/memory reference."""
import json
import random
import phase2_vectors as p2
import run_phase1 as s
BASE=0x10000000
BANKS=[(0x80000000,196),(0x80020000,128),
       (0x80040000,29280),(0x80060000,29280),(0x80080000,29280),(0x800a0000,29280),(0x800c0000,163)]

def transfer(a,b,c,store=False):
    return (b<<20)|(a<<15)|(int(store)<<12)|(c<<7)|0x2b

def merge_memory_errors(*errors):
    """Approved memory/next-PC priority, independent of the RTL implementation."""
    order={5:0,4:1,6:2,7:3}
    faults=[e for e in errors if e]
    return min(faults,key=order.__getitem__) if faults else 0

def error_for(src,dst,n,store,capacity):
    ext,inside=(dst,src) if store else (src,dst)
    bank=next(((base,depth) for base,depth in BANKS if base<=inside<base+0x20000),None)
    if src%4 or dst%4 or n%4:return 5
    if ext>>28!=1 or bank is None:return 4
    base,depth=bank
    if ext+n>0xffffffff or inside+n>0xffffffff or not BASE<=ext<BASE+capacity or ext+n>BASE+capacity or ext+n>0x20000000 or inside>=base+depth*4 or inside+n>base+depth*4:return 6
    if not n:return 7
    return 0

def fixtures(capacity,full):
    cases=[]
    def payload(n,seed):
        rng=random.Random(seed);return [rng.getrandbits(32) for _ in range(n)]
    def push(name,words,init=None,extra=None,inject_pc=-1):
        # Every RW CSR starts nonzero, often invalid for GEMM: transfers must ignore it.
        prefix=[p2.seti(address,100+i) for i,address in enumerate(p2.RW.values())]
        words=prefix+list(words)
        if name=="last_imem_word_load":
            words[-1]=s.jal(0,4092-4*(len(words)-1))
        if inject_pc>=0:inject_pc+=4*len(prefix)
        image=dict(enumerate(words))
        if extra:image.update(extra)
        cases.append((name,image,init or {},inject_pc))
    def setup(src,dst,n):return p2.li(1,src)+p2.li(2,dst)+p2.li(3,n)
    def roundtrip(bank,n,offset=0,src=BASE,out=BASE+0x20000,armed=True):
        address=BANKS[bank][0]+offset
        initial={src+4*i:w for i,w in enumerate(payload(n,3000+bank+n+offset))}
        initial.update({out-4:0xa5a55a5a,out+4*n:0x5a5aa5a5})
        words=([p2.TSTART] if armed else [])+setup(src,address,4*n)+[transfer(1,2,3),p2.csrr(5,p2.RO["PERF_COUNT"])]
        words+=p2.li(4,out)+[transfer(2,4,3,True),p2.csrr(6,p2.RO["PERF_COUNT"]),p2.TSTOP,p2.csrr(7,p2.RO["PERF_COUNT"]),s.END]
        push(f"bank{bank}_roundtrip_n{n}_offset{offset}",words,initial)
    for bank,(_,depth) in enumerate(BANKS):
        for n in ([1,2,7,depth] if full else [1]):
            roundtrip(bank,n)
        if full:roundtrip(bank,1,4*(depth-1),BASE+capacity-4,BASE+0x20000)
    if full:
        # Different banks and repeated commands in one program exercise ownership/retention.
        init={BASE+4*i:(0xc0000000+i*0x10203)&s.MASK for i in range(14)}
        words=[p2.TSTART]
        for b in range(7):
            words+=setup(BASE+8*b,BANKS[b][0],8)+[transfer(1,2,3)]
        for b in range(7):
            words+=setup(BANKS[b][0],BASE+0x20000+8*b,8)+[transfer(1,2,3,True)]
        words += [p2.csrr(5,p2.RO["PERF_COUNT"]),p2.TSTOP,s.END]
        push("all_banks_independent_reuse",words,init)
        roundtrip(0,3,armed=False)
    invalid=[
        ("zero_length",BASE,BANKS[0][0],0,False),
        ("length2",BASE,BANKS[0][0],2,False),
        ("length6",BASE,BANKS[0][0],6,False),
        ("src_misaligned",BASE+1,BANKS[0][0],4,False),
        ("dst_misaligned",BASE,BANKS[0][0]+2,4,False),
        ("dmem_last_overrun",BASE+capacity-4,BANKS[0][0],8,False),
        ("dmem_at_end",BASE+capacity,BANKS[0][0],4,False),
        ("dmem_before_base",BASE-4,BANKS[0][0],4,False),
        ("dmem_bad_region",0x20000000,BANKS[0][0],4,False),
        ("dmem_imem",0,BANKS[0][0],4,False),
        ("dmem_mmio",0xf0000000,BANKS[0][0],4,False),
        ("reserved_bank",BASE,0x800e0000,4,False),
        ("unknown_sram_region",BASE,0x90000000,4,False),
        ("direction_load",BANKS[0][0],BASE,4,False),
        ("direction_store",BASE,BANKS[0][0],4,True),
        ("external_wrap",BASE,BANKS[0][0],0xf0000000,False),
        ("internal_wrap",BASE,BANKS[0][0],0x80000000,False),
        ("store_dmem_end",BANKS[0][0],BASE+capacity,4,True),
        ("store_misaligned",BANKS[0][0],BASE+1,4,True),
    ]
    for b,(base,depth) in enumerate(BANKS):
        invalid += [(f"bank{b}_hole",BASE,base+depth*4,4,False),
                    (f"bank{b}_overrun",BASE,base,depth*4+4,False),
                    (f"bank{b}_store_hole",base+depth*4,BASE,4,True)]
    for name,src,dst,n,store in invalid:
        push(name,[p2.TSTART]+setup(src,dst,n)+[transfer(1,2,3,store)],{BASE:0x12345678,BASE+capacity-4:0x87654321})
    for name,w in [("rs3_r8",transfer(1,2,8)),("rs1_r31",transfer(31,2,3)),("rs2_r8",transfer(1,8,3)),
                   ("funct7",transfer(1,2,3)|(1<<25)),("store_rs3_r31",transfer(1,2,31,True)),
                   ("length_r0",transfer(1,2,0)),("alias_src_length",transfer(1,2,1)),
                   ("alias_src_dst",transfer(1,1,3))]:
        push(name,[p2.TSTART]+setup(BASE,BANKS[0][0],4)+[w],{BASE:0x11223344})
    # CPU next-PC bounds must reject dispatch before any transfer side effect.
    prefix=setup(BASE,BANKS[0][0],4)+[s.jal(0,4092-24)]
    push("last_imem_word_load",prefix,{BASE:0x99aa55cc},extra={1023:transfer(1,2,3)})
    if full:
        # Normal initialization uses LOAD; the subsequent forced runtime error allows a prefix only.
        init={BASE+4*i:0x11110000+i for i in range(4)}
        init.update({BASE+0x100+4*i:0xeeee0000+i for i in range(4)})
        words=setup(BASE,BANKS[0][0],16)+[transfer(1,2,3),p2.TSTART]+p2.li(1,BASE+0x100)
        inject_pc=4*len(words);words += [transfer(1,2,3)]
        push("runtime_bounds_after_first_write",words,init,inject_pc=inject_pc)
    if not full:
        keep={"bank0_roundtrip_n1_offset0","bank6_roundtrip_n1_offset0","dmem_at_end","dmem_last_overrun","dst_misaligned","zero_length","last_imem_word_load"}
        cases=[c for c in cases if c[0] in keep]
    return cases

def interpret(image,initial,capacity,inject_pc):
    regs=[0]*8;settings={a:0 for a in p2.RW.values()}
    pc=0;armed=0;count=0;overflow=0;memory=dict(initial);sram={}
    records=[];bus=[]
    for step in range(1024):
        assert pc%4==0 and 0<=pc<4096
        w=image.get(pc//4,0);op=w&127;rd=(w>>7)&31;f=(w>>12)&7;a=(w>>15)&31;b=(w>>20)&31
        err=0;status=0;used=[];value=None;update=None;arm_update=None
        address=w>>20;next_pc=pc+4;delay=2;block=False;store=False
        if op==0x37:used=[rd];value=w&0xfffff000
        elif op==0x13:
            used=[rd,a]
            if f:err=8
        elif op==0x33:
            used=[rd,a,b]
            if f or w>>25:err=8
        elif op==0x63:
            used=[a,b]
            if f not in (0,1):err=8
        elif op==0x6f:used=[rd]
        elif op==0x0b:address=(w>>7)&4095;update=s.signed(w>>19,13)&s.MASK
        elif op==0x73:
            if f==1:
                used=[a]
                if rd:err=8
            elif f==2:
                used=[rd]
                if a:err=8
            else:err=8
        elif op==0x2b:
            if f in (0,1) and w>>25==0:used=[a,b,rd];block=True;store=bool(f)
            elif w==s.END:status=1
            elif w==p2.TSTART:arm_update=1
            elif w==p2.TSTOP:arm_update=0
            else:err=8
        else:err=1
        if not err and any(r>=8 for r in used):err=2
        if not err:
            if op==0x13:value=regs[a]+s.signed(w>>20,12)
            elif op==0x33:value=regs[a]+regs[b]
            elif op==0x63:
                bits=(((w>>31)&1)<<12)|(((w>>7)&1)<<11)|(((w>>25)&63)<<5)|(((w>>8)&15)<<1)
                if (regs[a]!=regs[b]) if f else (regs[a]==regs[b]):next_pc=pc+s.signed(bits,13)
            elif op==0x6f:
                bits=(((w>>31)&1)<<20)|(((w>>12)&255)<<12)|(((w>>20)&1)<<11)|(((w>>21)&1023)<<1)
                next_pc=pc+s.signed(bits,21);value=pc+4
            elif op in (0x0b,0x73):
                writing=op==0x0b or f==1
                if address not in p2.CSR.values() or (writing and address not in settings):err=3
                elif writing:
                    if op==0x73:update=regs[a]
                else:value=settings.get(address,{p2.RO["PERF_COUNT"]:count,p2.RO["PERF_OVERFLOW"]:overflow,p2.RO["STATUS"]:0,p2.RO["ERROR_CODE"]:0}.get(address,0))
            if not status and not err and not block:
                if next_pc%4:err=5
                elif not 0<=next_pc<=4092:err=6
            if block and not err:
                src,dst,n=regs[a],regs[b],regs[rd]
                data_error=error_for(src,dst,n,store,capacity)
                pc_error=5 if next_pc%4 else (6 if not 0<=next_pc<=4092 else 0)
                err=merge_memory_errors(data_error,pc_error);delay=4
                if not err:
                    words=n//4;runtime=(pc==inject_pc)
                    actual_words=1 if runtime else words
                    for i in range(actual_words):
                        source,target=src+4*i,dst+4*i
                        if store:
                            assert source in sram,("uninitialized SRAM fixture",hex(source))
                            data=sram[source];memory[target]=data
                            bus.extend([[step,4+3*i,2,source,data],[step,6+3*i,1,target,data]])
                        else:
                            data=memory.get(source,0);sram[target]=data
                            bus.extend([[step,4+3*i,0,source,data],[step,6+3*i,3,target,data]])
                    active_edges=4 if runtime else 3*words
                    if armed and not store:
                        total=count+active_edges;overflow|=int(total>s.MASK);count=total&s.MASK
                    if runtime:err=6;delay=8
                    else:delay=3*words+4
        if err:status=2
        if status:next_pc=pc
        else:
            if value is not None and rd:regs[rd]=value&s.MASK
            if update is not None:settings[address]=update
            if arm_update is not None:
                armed=arm_update
                if arm_update:count=0;overflow=0
        records.append([pc,w,next_pc,status,err,*regs,*settings.values(),count,overflow,armed,delay])
        if status:return records,bus,memory
        pc=next_pc
    raise ValueError("reference did not halt")

def generate(directory,capacity,full):
    directory.mkdir(parents=True,exist_ok=False)
    listing=[]
    for i,(name,image,initial,inject_pc) in enumerate(fixtures(capacity,full)):
        trace,bus,memory=interpret(image,initial,capacity,inject_pc)
        (directory/f"case_{i}.imem.hex").write_text("".join(f"@{a:08x}\n{w:08x}\n" for a,w in sorted(image.items())),encoding="ascii")
        (directory/f"case_{i}.dmem.hex").write_text("".join(f"@{(a-BASE)//4:08x}\n{w:08x}\n" for a,w in sorted(initial.items())),encoding="ascii")
        for suffix,rows in [("trace",trace),("bus",bus),("final",[[a,v] for a,v in sorted(memory.items())])]:
            (directory/f"case_{i}.{suffix}.hex").write_text("".join(f"{v&s.MASK:08x}\n" for row in rows for v in row),encoding="ascii")
        listing.append({"id":i,"name":name,"steps":len(trace),"events":len(bus),"final_words":len(memory),"inject_pc":inject_pc,"error":trace[-1][4],"timer":trace[-1][25]})
    # cases.txt: injection -1 is written as a signed decimal, not machine code.
    (directory/"cases.txt").write_text("".join(f"{c['id']} {c['steps']} {c['events']} {c['final_words']} {c['inject_pc']}\n" for c in listing),encoding="ascii")
    (directory/"cases.json").write_text(json.dumps(listing,indent=2),encoding="utf-8")
    (directory/"npu_phase3_profile.vh").write_text(f"localparam integer IMEM_BYTES=4096;\nlocalparam integer DMEM_BYTES={capacity};\nlocalparam integer EXPECTED_CASES={len(listing)};\nlocalparam integer EXPECTED_STEPS={sum(c['steps'] for c in listing)};\n",encoding="ascii")
    return listing
