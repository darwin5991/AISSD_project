"""Phase 4 scalar encoders, independent ISA/DMEM reference and mixed block fixtures."""
import json
import random
import phase2_vectors as p2
import phase3_vectors as p3
import run_phase1 as s
BASE=p3.BASE

def lw(rd,rs1,imm=0):
    assert 0<=rd<32 and 0<=rs1<32 and -2048<=imm<=2047
    return ((imm&4095)<<20)|(rs1<<15)|(2<<12)|(rd<<7)|0x03

def sw(rs2,rs1,imm=0):
    assert 0<=rs2<32 and 0<=rs1<32 and -2048<=imm<=2047
    bits=imm&4095
    return ((bits>>5)<<25)|(rs2<<20)|(rs1<<15)|(2<<12)|((bits&31)<<7)|0x23

def fixtures(capacity,full):
    cases=[]
    def push(name,words,initial=None,last=None):
        # Nonzero GPRs/RW CSRs make fault and scalar-memory side effects visible.
        prefix=[p2.seti(a,100+i) for i,a in enumerate(p2.RW.values())]
        prefix += [s.addi(i,0,200+i) for i in range(1,8)]+[p2.TSTART]
        image=dict(enumerate(prefix+words))
        if last is not None:
            image[len(prefix+words)]=s.jal(0,4092-4*len(prefix+words))
            image[1023]=last
        assert max(image)<1024,name
        cases.append((name,image,initial or {},-1))
    guards={BASE:0x01020304,BASE+4:0x80000000,BASE+capacity-4:0xfedcba98}
    # RAW dependencies, aliases, r0, full 32-bit patterns, repeated writes and endian order.
    words=p2.li(1,BASE+0x100)
    vals=[0,1,0x7fffffff,0x80000000,0xffffffff,0x01020304,0x80ff017f,0xa5a55a5a]
    for i,v in enumerate(vals):
        words+=p2.li(2,v)+[sw(2,1,4*i),lw(3,1,4*i),s.add(4,3,0),sw(4,1,64+4*i)]
    words += [lw(0,1),sw(0,1,96),lw(5,1,96),p2.csrr(6,p2.RO["PERF_COUNT"]),p2.TSTOP,s.END]
    push("patterns_dependencies_r0",words,guards)
    push("negative_offsets_and_unaligned_base",
         p2.li(1,BASE+0x100)+[lw(2,1,-4),sw(2,1,-8)]
         +p2.li(1,BASE+1)+[lw(3,1,-1),sw(3,1,3),s.END],
         {**guards,BASE+0xfc:0xdeadbeef})
    push("lw_rd_equals_base",p2.li(1,BASE)+[lw(1,1),lw(2,1),sw(2,1,4),s.END],
         {**guards,BASE:BASE+0x100,BASE+0x100:0x1234abcd})
    push("sw_base_equals_data",p2.li(1,BASE+0x100)+[sw(1,1),lw(2,1),s.END],guards)
    push("first_last_valid_word",p2.li(1,BASE)+[lw(2,1),sw(2,1)]
         +p2.li(1,BASE+capacity-4)+[lw(3,1),sw(3,1),s.END],guards)
    if full:
        # All 4096 signed I/S immediates, including every split and sign bit.
        # Compensate the base to make the final EA aligned even for odd immediates.
        for store in [False,True]:
            for start in range(-2048,2048,64):
                words=p2.li(2,0x807f01fe)
                for imm in range(start,start+64):
                    words+=p2.li(1,BASE+0x100-imm)+[sw(2,1,imm) if store else lw(3,1,imm)]
                push(f"all_imm_{'sw' if store else 'lw'}_{start}",words+[s.END],
                     {**guards,BASE+0x100:0x80ff1234})
        for store in [False,True]:
            for a in range(1,8):
                words=[]
                for b in range(8):
                    words+=p2.li(a,BASE+0x100)
                    if store and b and b!=a:words+=p2.li(b,0xff000000+b)
                    words += [sw(b,a) if store else lw(b,a)]
                push(f"valid_registers_{'sw' if store else 'lw'}_base{a}",words+[s.END],
                     {**guards,BASE+0x100:0xcafebabe})
        rng=random.Random(4001)
        words=p2.li(1,BASE+0x1000)
        init=dict(guards)
        for i in range(80):
            offset=4*rng.randrange(-128,128)
            value=rng.getrandbits(32)
            words+=p2.li(2,value)+[sw(2,1,offset),lw(3,1,offset)]
        push("random_memory_seed4001",words+[s.END],init)
    bad_addresses=[
        ("misaligned1",BASE+1,0),("misaligned2",BASE+2,0),("misaligned3",BASE+3,0),
        ("misaligned_bad_region",0xf0000001,0),("misaligned_capacity",BASE+capacity+1,0),
        ("capacity_end",BASE+capacity,0),("capacity_plus4",BASE+capacity+4,0),
        ("capacity_positive_imm",BASE+capacity-4,4),
        ("capacity_large_negative_imm",BASE+capacity+2048,-2048),
        ("below_base",BASE,-4),("region_end",0x1ffffffc,4),
        ("imem",0,0),("mmio",0xf0000000,0),("other",0x20000000,0),
        ("sram_A",0x80000000,0),("sram_W0",0x80040000,0),("sram_bias",0x800c0000,0),
        ("unsigned_high_base",0x90000000,0),
        ("wrap_up",0xfffffffc,4),("wrap_down",0,-4),
        ("wrap_up_misaligned",0xffffffff,2047),("wrap_down_misaligned",0,-1)]
    for store in [False,True]:
        for name,a,imm in bad_addresses:
            push(f"fault_{'sw' if store else 'lw'}_{name}",
                 p2.li(1,a)+[sw(2,1,imm) if store else lw(2,1,imm)],guards)
        for reg in range(8,32):
            for position in ["base","data"]:
                a,b=(reg,2) if position=="base" else (1,reg)
                push(f"bad_gpr_{'sw' if store else 'lw'}_{position}_r{reg}",
                     p2.li(1,BASE)+[sw(b,a) if store else lw(b,a)],guards)
        for f in [0,1,3,4,5,6,7]:
            word=sw(31,31,-1) if store else lw(31,31,-1)
            word=(word&~(7<<12))|(f<<12)
            push(f"encoding_before_gpr_{'sw' if store else 'lw'}_f{f}",[word],guards)
        last=sw(2,1) if store else lw(2,1)
        push(f"last_imem_{'sw' if store else 'lw'}",p2.li(1,BASE),guards,last=last)
    push("fault_lw_r0_still_checks_address",p2.li(1,BASE+1)+[lw(0,1)],guards)
    push("fault_lw_r0_bounds",p2.li(1,BASE+capacity)+[lw(0,1)],guards)
    push("fault_base_r0", [lw(2,0,0)],guards)
    # Exercise scalar/xfer/scalar DMEM ownership and data dependence on every SRAM bank.
    for b,(bank,_) in enumerate(p3.BANKS if full else [p3.BANKS[0],p3.BANKS[6]]):
        words=p2.li(1,BASE+0x100)+p2.li(2,0x80000000+b)+[sw(2,1),sw(0,1,4)]
        words+=p2.li(2,bank)+p2.li(3,8)+[p3.transfer(1,2,3)]
        words+=p2.li(4,BASE+0x200)+[p3.transfer(2,4,3,True),lw(5,4),lw(6,4,4)]
        words += [p2.csrr(7,p2.RO["PERF_COUNT"]),p2.TSTOP,s.END]
        push(f"scalar_block_scalar_bank_{bank:08x}",words,guards)
    # A committed prefix followed by a rejected instruction: no later SW/fetch.
    push("fault_after_valid_sw",p2.li(1,BASE)+p2.li(2,0xdeadbeef)
         +[sw(2,1),lw(3,1),sw(2,1,2),sw(0,1),s.END],guards)
    if not full:
        keep={"patterns_dependencies_r0","negative_offsets_and_unaligned_base","first_last_valid_word",
              "fault_sw_capacity_end","fault_lw_below_base","fault_lw_misaligned1","fault_lw_wrap_up",
              "last_imem_sw","scalar_block_scalar_bank_80000000","scalar_block_scalar_bank_800c0000",
              "fault_after_valid_sw"}
        cases=[c for c in cases if c[0] in keep]
    return cases

def scalar_error(address,capacity):
    # User-confirmed order; arithmetic is unbounded Python, not a wrapped RTL sum.
    if address%4:return 5
    if not 0<=address<=s.MASK:return 6
    if address>>28!=1:return 4
    if address+4>BASE+capacity:return 6
    return 0

def interpret(image,initial,capacity,inject_pc):
    regs=[0]*8;settings={a:0 for a in p2.RW.values()}
    pc=0;armed=0;count=0;overflow=0;memory=dict(initial);sram={}
    records=[];bus=[]
    for step in range(1024):
        assert pc%4==0 and 0<=pc<4096
        w=image.get(pc//4,0);op=w&127;rd=(w>>7)&31;f=(w>>12)&7;a=(w>>15)&31;b=(w>>20)&31
        err=0;status=0;used=[];value=None;update=None;arm_update=None
        address=w>>20;next_pc=pc+4;delay=2;block=False;store=False;scalar_memory=False
        if op==0x37:used=[rd];value=w&0xfffff000
        elif op==0x13:
            used=[rd,a]
            if f:err=8
        elif op in (0x03,0x23):
            scalar_memory=True;store=(op==0x23)
            used=[a,b] if store else [rd,a]
            if f!=2:err=8
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
            if not status and not err:
                if next_pc%4:err=5
                elif not 0<=next_pc<=4092:err=6
            if scalar_memory and not err:
                imm=((w>>25)<<5)|((w>>7)&31) if store else w>>20
                ea=regs[a]+s.signed(imm,12)
                err=scalar_error(ea,capacity)
                if not err:
                    delay=4
                    data=regs[b] if store else memory.get(ea,0)
                    bus.append([step,3,1 if store else 0,ea,data])
                    if store:memory[ea]=data
                    else:value=data
            if block and not err:
                src,dst,n=regs[a],regs[b],regs[rd]
                err=p3.error_for(src,dst,n,store,capacity);delay=4
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

def generate(directory,capacity,full,debug=False):
    directory.mkdir(parents=True,exist_ok=False)
    listing=[]
    selected=fixtures(capacity,full)
    if debug:selected=[c for c in selected if c[0]=="scalar_block_scalar_bank_80000000"]
    for i,(name,image,initial,inject_pc) in enumerate(selected):
        trace,bus,memory=interpret(image,initial,capacity,inject_pc)
        (directory/f"case_{i}.imem.hex").write_text("".join(f"@{a:08x}\n{w:08x}\n" for a,w in sorted(image.items())),encoding="ascii")
        (directory/f"case_{i}.dmem.hex").write_text("".join(f"@{(a-BASE)//4:08x}\n{w:08x}\n" for a,w in sorted(initial.items())),encoding="ascii")
        for suffix,rows in [("trace",trace),("bus",bus),("final",[[a,v] for a,v in sorted(memory.items())])]:
            (directory/f"case_{i}.{suffix}.hex").write_text("".join(f"{v&s.MASK:08x}\n" for row in rows for v in row),encoding="ascii")
        listing.append({"id":i,"name":name,"steps":len(trace),"events":len(bus),"final_words":len(memory),"inject_pc":inject_pc,"error":trace[-1][4],"timer":trace[-1][25]})
    # cases.txt: injection -1 is written as a signed decimal, not machine code.
    (directory/"cases.txt").write_text("".join(f"{c['id']} {c['steps']} {c['events']} {c['final_words']} {c['inject_pc']}\n" for c in listing),encoding="ascii")
    (directory/"cases.json").write_text(json.dumps(listing,indent=2),encoding="utf-8")
    (directory/"npu_phase4_profile.vh").write_text(f"localparam integer IMEM_BYTES=4096;\nlocalparam integer DMEM_BYTES={capacity};\nlocalparam integer EXPECTED_CASES={len(listing)};\nlocalparam integer EXPECTED_STEPS={sum(c['steps'] for c in listing)};\n",encoding="ascii")
    return listing
