"""Phase 2 directed encoders/reference. No EXEC validation or Phase 3 memory ops."""
import json
import random
from pathlib import Path
import run_phase1 as scalar

RW = {
    "SRC0_BASE":0x7c0, "SRC1_BASE":0x7c1, "DST_BASE":0x7c2, "BIAS_BASE":0x7c3,
    "M":0x7c4, "N":0x7c5, "K":0x7c6, "BIAS_SHIFT":0x7c7,
    "OUT_SHIFT":0x7c8, "ACT_MODE":0x7c9, "ARG_SRC":0x7e0, "ARG_LEN":0x7e1,
}
RO = {"PERF_COUNT":0x7f0,"PERF_OVERFLOW":0x7f1,"STATUS":0x7f2,"ERROR_CODE":0x7f3}
CSR = {**RW,**RO}
TSTART, TSTOP = 0x0000302b, 0x0200302b

def seti(address, value):
    assert 0 <= address < 4096 and -4096 <= value <= 4095
    return ((value & 8191) << 19) | (address << 7) | 0x0b

def csrw(address, rs):
    return (address << 20) | (rs << 15) | 0x1073

def csrr(rd, address):
    return (address << 20) | (rd << 7) | 0x2073

def li(rd, value):
    value &= scalar.MASK
    low=scalar.signed(value & 4095,12)
    return [scalar.lui(rd,((value-low)>>12)&0xfffff),scalar.addi(rd,rd,low)]

def fixtures(size):
    cases=[]
    def push(name,words,extra=None):
        image=dict(enumerate(words))
        if extra: image.update(extra)
        assert all(0<=k<size//4 for k in image),name
        cases.append((name,image))
    push("all_csr_reset_reads",[csrr(1,a) for a in CSR.values()]+[scalar.END])
    for name,address in RW.items():
        words=[]
        for i,value in enumerate([0,-4096,4095,-1]):
            words += [seti(address,value),csrr(i+1,address)]
        push("seti_sign_"+name,words+[scalar.END])
        words=[]
        for value in [0xffffffff,0x80000000,0x7fffffff,0x12345fed]:
            words += li(4,value)+[csrw(address,4),csrr(5,address),csrr(0,address)]
        push("csrw_full32_"+name,words+[scalar.END])
    push("D01_intermediate_invalid",[
        seti(RW["K"],3),csrr(1,RW["K"]),seti(RW["K"],128),csrr(2,RW["K"]),
        seti(RW["M"],-1),seti(RW["N"],0),seti(RW["ACT_MODE"],2),
        seti(RW["ARG_LEN"],11),seti(RW["BIAS_SHIFT"],-4096),
        seti(RW["OUT_SHIFT"],4095),scalar.END])
    words=[]
    for i,address in enumerate(RW.values()):
        words += [seti(address,100+i)]
    words += [csrr(7,a) for a in RW.values()]
    push("cross_csr_isolation",words+[scalar.END])
    push("SETADDR_r4_clobber_and_low12_fix",
        li(4,0x80020000)+[csrw(RW["SRC0_BASE"],4),csrr(5,RW["SRC0_BASE"])]
        +li(4,0x10000ff0)+[csrw(RW["DST_BASE"],4),csrr(6,RW["DST_BASE"]),scalar.END])
    push("timer_scalar_csr_excluded",[
        TSTART,scalar.addi(1,0,10),scalar.addi(1,1,-1),csrr(2,RO["PERF_COUNT"]),
        csrr(3,RO["PERF_OVERFLOW"]),TSTOP,csrr(4,RO["PERF_COUNT"]),
        TSTART,TSTART,csrr(5,RO["PERF_COUNT"]),TSTOP,TSTOP,scalar.END])
    push("timer_armed_survives_end",[TSTART,scalar.END])
    for name,address in RO.items():
        push("ro_read_"+name,[csrr(0,address),csrr(7,address),scalar.END])
        push("ro_seti_"+name,[seti(RW["K"],128),seti(address,0)])
        push("ro_csrw_zero_"+name,[seti(RW["K"],128),csrw(address,0)])
    for address in [0,0x7bf,0x7ca,0x7df,0x7e2,0x7ef,0x7f4,0xfff]:
        for mode,word in [("read",csrr(0,address)),("seti",seti(address,-1)),("write",csrw(address,0))]:
            push(f"reserved_{address:03x}_{mode}",[seti(RW["K"],128),word])
    bad=[
        ("csrw_rd1",csrw(RW["K"],0)|(1<<7)),
        ("csrw_rd31",csrw(RW["K"],0)|(31<<7)),
        ("csrr_rs1",csrr(1,RW["K"])|(1<<15)),
        ("csrr_rs8",csrr(1,RW["K"])|(8<<15)),
    ]
    for f in [0,3,4,5,6,7]:
        bad.append((f"csr_funct3_{f}",(RW["K"]<<20)|(31<<15)|(f<<12)|(31<<7)|0x73))
    for reg in [8,31]:
        bad += [(f"csrw_r{reg}",csrw(RW["K"],reg)),(f"csrr_r{reg}",csrr(reg,RW["K"]))]
    for name,word in bad:
        push(name,[seti(RW["K"],128),word])
    for name,word in [("tstart_rd",TSTART|128),("tstart_rs1",TSTART|(1<<15)),
                      ("tstop_rs2",TSTOP|(1<<20)),("tstop_reserved",TSTOP|(4<<25))]:
        push(name,[TSTART,word])
    for name,word in [
        ("seti",seti(RW["K"],3)),("csrw",csrw(RW["K"],0)),
        ("csrr",csrr(5,RW["K"])),("bad_csr",seti(0x7ca,3)),
        ("tstart",TSTART),("tstop",TSTOP)]:
        push("last_word_"+name,[seti(RW["K"],128),TSTART,scalar.jal(0,size-12)],
             {size//4-1:word})
    for seed in range(8):
        rng=random.Random(2000+seed); words=[]
        for _ in range(16):
            address=rng.choice(list(RW.values()))
            mode=rng.randrange(4)
            if mode==0: words += [seti(address,rng.randrange(-4096,4096))]
            elif mode==1: words += li(4,rng.getrandbits(32))+[csrw(address,4)]
            elif mode==2: words += [csrr(rng.randrange(8),address)]
            else: words += [rng.choice([TSTART,TSTOP])]
        push(f"random_seed_{2000+seed}",words+[scalar.END])
    return cases

def interpret(image,size):
    regs=[0]*8; settings={a:0 for a in RW.values()}; pc=0; armed=0
    records=[]
    for _ in range(4096):
        assert pc%4==0 and 0<=pc<=size-4
        w=image.get(pc//4,0)
        opcode=w&127; rd=(w>>7)&31; f3=(w>>12)&7; a=(w>>15)&31; b=(w>>20)&31
        error=0; status=0; used=[]; value=None; update=None; arm_update=None
        next_pc=pc+4; address=w>>20
        if opcode==0x37: used=[rd]; value=w&0xfffff000
        elif opcode==0x13:
            used=[rd,a]
            if f3: error=8
        elif opcode==0x33:
            used=[rd,a,b]
            if f3 or w>>25: error=8
        elif opcode==0x63:
            used=[a,b]
            if f3 not in (0,1): error=8
        elif opcode==0x6f: used=[rd]
        elif opcode==0x0b:
            address=(w>>7)&4095
            update=scalar.signed(w>>19,13)&scalar.MASK
        elif opcode==0x73:
            if f3==1:
                used=[a]
                if rd!=0: error=8
            elif f3==2:
                used=[rd]
                if a!=0: error=8
            else: error=8
        elif opcode==0x2b:
            if w==scalar.END: status=1
            elif w==TSTART: arm_update=1
            elif w==TSTOP: arm_update=0
            else: error=8
        else: error=1
        if not error and any(r>=8 for r in used): error=2
        if not error:
            if opcode==0x13: value=regs[a]+scalar.signed(w>>20,12)
            elif opcode==0x33: value=regs[a]+regs[b]
            elif opcode==0x63:
                bits=(((w>>31)&1)<<12)|(((w>>7)&1)<<11)|(((w>>25)&63)<<5)|(((w>>8)&15)<<1)
                taken=regs[a]!=regs[b] if f3 else regs[a]==regs[b]
                if taken: next_pc=pc+scalar.signed(bits,13)
            elif opcode==0x6f:
                bits=(((w>>31)&1)<<20)|(((w>>12)&255)<<12)|(((w>>20)&1)<<11)|(((w>>21)&1023)<<1)
                next_pc=pc+scalar.signed(bits,21); value=pc+4
            elif opcode in (0x0b,0x73):
                writing=opcode==0x0b or f3==1
                if address not in CSR.values() or (writing and address not in settings):
                    error=3
                elif writing:
                    if opcode==0x73: update=regs[a]
                else:
                    value=settings.get(address,0) # RO live values are 0 during execution here.
            if not error and not status:
                if next_pc%4: error=5
                elif next_pc<0 or next_pc+4>size: error=6
        if error: status=2
        if status: next_pc=pc
        else:
            if value is not None and rd: regs[rd]=value&scalar.MASK
            if update is not None: settings[address]=update
            if arm_update is not None: armed=arm_update
        records.append([pc,w,next_pc,status,error,*regs,*settings.values(),0,0,armed])
        if status: return records
        pc=next_pc
    raise ValueError("Phase 2 reference did not terminate")

def generate(directory,size):
    directory.mkdir(parents=True,exist_ok=False)
    listing=[]
    for i,(name,image) in enumerate(fixtures(size)):
        records=interpret(image,size)
        (directory/f"case_{i}.imem.hex").write_text("".join(f"@{p:08x}\n{w:08x}\n" for p,w in sorted(image.items())),encoding="ascii")
        (directory/f"case_{i}.trace.hex").write_text("".join(f"{v&scalar.MASK:08x}\n" for row in records for v in row),encoding="ascii")
        listing.append({"id":i,"name":name,"steps":len(records),"status":records[-1][3],"error":records[-1][4]})
    total=sum(c["steps"] for c in listing)
    (directory/"cases.txt").write_text("".join(f"{c['id']} {c['steps']}\n" for c in listing),encoding="ascii")
    (directory/"cases.json").write_text(json.dumps(listing,indent=2),encoding="utf-8")
    (directory/"npu_phase2_profile.vh").write_text(f"localparam integer IMEM_BYTES={size};\nlocalparam integer DMEM_BYTES=16777216;\nlocalparam integer EXPECTED_CASES={len(listing)};\nlocalparam integer EXPECTED_STEPS={total};\n",encoding="ascii")
    return len(listing),total
