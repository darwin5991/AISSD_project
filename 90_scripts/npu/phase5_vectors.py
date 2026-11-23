"""Phase 5 independent signed-INT32 GEMM model and instruction/memory fixtures."""
import json
import random
import hashlib
from pathlib import Path
import phase2_vectors as p2
import phase3_vectors as p3
import phase4_vectors as p4
import run_phase1 as s
BASE=p3.BASE
GEMM=0x0000202b
SOURCE=s.ROOT/"07_runs/golden_sample_00007_20261109_164854_126978Z"
SOURCE_HASHES={}
def wrap32(x):return ((int(x)+(1<<31))&s.MASK)-(1<<31)
def bytes4(w):return [s.signed((w>>(8*i))&255,8) for i in range(4)]
def pack(xs):return sum((x&255)<<(8*i) for i,x in enumerate(xs))

def config_error(c):
    src,w,dst,bias,m,n,k,bs,os,act=c
    if any(a%4 for a in c[:4]):return 5
    def bank(a):return next(((i,b,depth) for i,(b,depth) in enumerate(p3.BANKS) if b<=a<b+0x20000),None)
    a,b,z,q=map(bank,[src,w,dst,bias])
    if a is None or a[0] not in [0,1] or z is None or z[0] not in [0,1] or b is None or b[0]!=2 or q is None or q[0]!=6:return 4
    groups=(n+3)//4
    for address,length,info in [(src,k,a),(dst,groups*4,z),(w,k*groups,b),(bias,groups*4,q)]:
        if address>=info[1]+info[2]*4 or address+length>info[1]+info[2]*4 or address+length>0xffffffff:return 6
    if m!=1 or not 1<=n<=512 or k<8 or k%4 or not -32<=s.signed(bs,32)<=31 or os>31 or act>1 or a[0]==z[0]:return 7
    return 0

def kernel(mem,c,details=False):
    src,weight,dst,bias,m,n,k,bs,shift,act=c
    bs=s.signed(bs,32);out=[];starts=[];updates=[];finals=[]
    for g in range((n+3)//4):
        accum=[wrap32(x<<bs) if bs>=0 else x>>-bs for x in bytes4(mem[bias+4*g])]
        starts.append(accum.copy());group_updates=[]
        for i in range(k//4):
            x=bytes4(mem[src+4*i])
            for lane in range(4):
                w=bytes4(mem[weight+lane*0x20000+4*(g*(k//4)+i)])
                accum[lane]=wrap32(accum[lane]+sum(a*b for a,b in zip(x,w)))
            group_updates.append(accum.copy())
        updates.append(group_updates);finals.append(accum.copy())
        result=[max(-128,min(127,(max(0,a) if act else a)>>shift)) for a in accum]
        out.append(pack(result))
    return (out,starts,updates,finals) if details else out

class Builder:
    def __init__(self,capacity):
        self.capacity=capacity
        self.words=[p2.seti(a,100+i) for i,a in enumerate(p2.RW.values())]+[s.addi(i,0,200+i) for i in range(1,8)]
        self.initial={BASE:0x12345678,BASE+capacity-4:0x89abcdef}
        self.cursor=0x1000;self.out_cursor=capacity-(0x10000 if capacity>=0x20000 else 0x1000)
        self.legacy_expected={}
    def load(self,dst,data):
        address=BASE+self.cursor;self.cursor+=len(data)*4+16
        assert self.cursor<self.out_cursor,"fixture overlaps output allocation"
        self.initial.update({address+4*i:w for i,w in enumerate(data)})
        self.words+=p2.li(1,address)+p2.li(2,dst)+p2.li(3,4*len(data))+[p3.transfer(1,2,3)]
    def cfg(self,c):
        for i,v in enumerate(c):
            signed=s.signed(v&s.MASK,32)
            self.words+=([p2.seti(0x7c0+i,signed)] if -4096<=signed<=4095 else p2.li(4,v)+[p2.csrw(0x7c0+i,4)])
    def store(self,src,words,expected=None):
        address=BASE+self.out_cursor;self.out_cursor+=4*words+16
        assert self.out_cursor<self.capacity
        self.initial[address-4]=0x5aa55aa5;self.initial[address+4*words]=0xa55aa55a
        self.words+=p2.li(1,src)+p2.li(2,address)+p2.li(3,words*4)+[p3.transfer(1,2,3,True)]
        if expected is not None:self.legacy_expected[address]=expected
    def finish(self,name,hook=0,extra=None):
        image=dict(enumerate(self.words+[s.END]))
        if extra:image.update(extra)
        assert max(image)<1024,name
        return (name,image,self.initial,hook,self.legacy_expected)

def synthetic(capacity,k=8,n=12,direction=0,seed=5000,shifts=(0,2,0),boundary=False):
    rng=random.Random(seed);groups=(n+3)//4;words=k//4
    srcbank=direction;dstbank=1-direction
    src=p3.BANKS[srcbank][0]+(4*(p3.BANKS[srcbank][1]-words) if boundary else 8)
    dst=p3.BANKS[dstbank][0]+(4*(p3.BANKS[dstbank][1]-groups) if boundary else 12)
    woff=29280-words*groups if boundary else 3;boff=163-groups if boundary else 2
    c=[src,0x80040000+woff*4,dst,0x800c0000+boff*4,1,n,k,shifts[0]&s.MASK,shifts[1],shifts[2]]
    b=Builder(capacity)
    inputs=[rng.randrange(-128,128) for _ in range(k)]
    b.load(src,[pack(inputs[i:i+4]) for i in range(0,k,4)])
    for lane in range(4):
        data=[]
        for g in range(groups):
            for i in range(words):
                data.append(pack([rng.randrange(-128,128) if 4*g+lane<n else 0 for _ in range(4)]))
        b.load(0x80040000+lane*0x20000+woff*4,data)
    b.load(c[3],[pack([rng.randrange(-128,128) if 4*g+l<n else 0 for l in range(4)]) for g in range(groups)])
    prefix=int(dst>p3.BANKS[dstbank][0])
    b.load(dst-4*prefix,([0x6b6b6b6b] if prefix else [])+[0x5c5c5c5c]*groups)
    return b,c

def source_words(relative):
    path=SOURCE/relative
    data=path.read_bytes()
    manifest=json.loads((SOURCE/"manifest.json").read_text())
    digest=hashlib.sha256(data).hexdigest()
    assert digest==manifest["files_sha256"][relative],relative
    SOURCE_HASHES[relative]=digest
    return [int(x,16) for x in data.decode().split()]

def fixtures(capacity,full,debug=False):
    cases=[]
    ks=[8,12,16,32] if full else [8]
    ns=[1,4,5,8,9,10,12,20,512] if full else [12]
    for k in ks:
        for n in ns:
            for direction in ([0,1] if full else [0]):
                b,c=synthetic(capacity,k,n,direction,seed=5000+k+n+direction,boundary=full)
                b.cfg(c);b.words += [p2.TSTART,GEMM,p2.csrr(5,p2.RO["PERF_COUNT"]),p2.TSTOP]
                prefix=int(c[2]>p3.BANKS[1-direction][0])
                b.store(c[2]-4*prefix,(n+3)//4+prefix)
                cases.append(b.finish(f"k{k}_n{n}_dir{direction}_boundary{int(full)}"))
    if not full:
        return cases[:1] if debug else cases
    for bs in [-32,-31,-1,0,23,24,25,30,31]:
        for os in [0,31]:
            for act in [0,1]:
                b,c=synthetic(capacity,8,9,0,seed=6001,shifts=(bs,os,act))
                # Extreme biases make alignment and subsequent accumulation wrap observable.
                # The kernel consumes externally loaded random signed bias, including large shifts.
                b.cfg(c);b.words += [p2.TSTART,GEMM,p2.TSTOP];b.store(c[2],3)
                cases.append(b.finish(f"wrap_bias{bs}_out{os}_act{act}"))
    b,c=synthetic(capacity,8,12)
    b.cfg(c);b.words += [p2.TSTART,GEMM,p2.csrr(5,p2.RO["PERF_COUNT"]),p2.TSTOP];b.store(c[2],3)
    cases.append(b.finish("atomic_snapshot_live_csr_change",hook=1))
    b,c=synthetic(capacity,8,20)
    b.cfg(c);b.words += [p2.TSTART,GEMM]
    cases.append(b.finish("runtime_bounds_after_first_output",hook=2))
    b=Builder(capacity)
    c=[0x80000000,0x80040000,0x80020000,0x800c0000,1,4,8,31,0,0]
    b.load(c[0],[pack([127]*4)]*2)
    for lane in range(4):b.load(0x80040000+lane*0x20000,[pack([-127]*4),pack([127]*4)])
    b.load(c[3],[pack([1]*4)])
    b.cfg(c);b.words += [p2.TSTART,GEMM,p2.TSTOP];b.store(c[2],1)
    cases.append(b.finish("accumulator_wrap_both_directions"))
    # Repeated commands reuse the same datapath without a reset and change settings.
    b,c=synthetic(capacity,8,12)
    b.words += [p2.TSTART]
    for j in range(4):
        c[7]=[-1,0,24,31][j]&s.MASK;c[8]=[0,1,5,31][j];c[9]=j%2
        b.cfg(c);b.words += [GEMM];b.store(c[2],3)
    b.words += [p2.csrr(5,p2.RO["PERF_COUNT"]),p2.TSTOP]
    cases.append(b.finish("four_gemm_no_reset"))
    b,c=synthetic(capacity,8,12)
    b.cfg(c);b.words += [GEMM];b.store(c[2],3)
    cases.append(b.finish("gemm_unarmed"))
    # Start measuring before another LOAD: count is the sum of real engine activity.
    b,c=synthetic(capacity,8,12)
    b.words += [p2.TSTART];b.load(c[0],[0x807f01ff,0x80ff7f01]);b.cfg(c)
    b.words += [GEMM,p2.TSTOP];b.store(c[2],3)
    cases.append(b.finish("load_plus_gemm_timer"))
    base=[0x80000000,0x80040000,0x80020000,0x800c0000,1,12,8,0,0,0]
    invalid=[]
    for index in range(4):invalid.append((f"align_field{index}",{index:base[index]+1}))
    invalid += [
        ("src0_weight",{0:0x80040000}),("dst_bias",{2:0x800c0000}),("weight_bank1",{1:0x80060000}),
        ("bias_buffer",{3:0x80000000}),("src_dmem",{0:BASE}),("same_buffer",{2:0x80000004}),
        ("input_end",{0:0x80000310}),("input_overrun",{0:0x8000030c}),
        ("output_end",{2:0x80020200}),("output_overrun",{2:0x800201fc}),
        ("weight_end",{1:0x8005c980}),("weight_overrun",{1:0x8005c97c}),
        ("bias_end",{3:0x800c028c}),("bias_overrun",{3:0x800c0288}),
        ("m0",{4:0}),("m2",{4:2}),("m_high",{4:0x80000001}),
        ("n0",{5:0}),("n513",{5:513,0:0x80020000,2:0x80000000,6:8}),
        ("n_high_wrap",{5:0xffffffff}),("k0",{6:0}),("k3",{6:3}),("k4",{6:4}),
        ("k6",{6:6}),("k7",{6:7}),("k_high",{6:0x80000008}),("k_wrap",{6:0xfffffffc}),
        ("bias_shift32",{7:32}),("bias_shift_neg33",{7:0xffffffdf}),
        ("bias_shift_lowbits_valid",{7:0x10000001}),("bias_shift63",{7:63}),
        ("out_shift32",{8:32}),("out_shift_high",{8:0x80000001}),
        ("out_shift_negative",{8:0xffffffff}),("act2",{9:2}),("act_high",{9:0x80000001}),
        ("align_before_region_bounds_config",{0:BASE+1,5:0,6:4}),
        ("region_before_bounds_config",{0:BASE,5:0xffffffff,6:4}),
        ("bounds_before_k4",{0:0x80000310,6:4}),("bounds_before_same_buffer",{0:0x80000310,2:0x80000310}),
        ("role_before_same_buffer",{0:0x80040000,2:0x80040000}),
        ("count_not_address_alignment",{6:3}),
    ]
    for name,changes in invalid:
        b=Builder(capacity);c=base.copy()
        for i,v in changes.items():c[i]=v
        b.cfg(c);b.words += [p2.TSTART,GEMM]
        cases.append(b.finish("fault_"+name))
    for name,word in [("rd",GEMM|(1<<7)),("rs1",GEMM|(31<<15)),("rs2",GEMM|(31<<20)),("reserved_exec_funct7",GEMM|(2<<25))]:
        b=Builder(capacity);b.words += [word];cases.append(b.finish("encoding_"+name))
    b=Builder(capacity);b.cfg(base)
    pos=len(b.words);b.words += [s.jal(0,4092-4*pos)]
    cases.append(b.finish("last_imem_gemm",extra={1023:GEMM}))
    for label,changes in [("align",{0:0x80000001,6:4}),("region",{1:0x80060000,6:4}),("config",{6:4}),("bounds",{0:0x80000310})]:
        b=Builder(capacity);c=base.copy()
        for i,v in changes.items():c[i]=v
        b.cfg(c);pos=len(b.words);b.words += [s.jal(0,4092-4*pos)]
        cases.append(b.finish("last_imem_priority_"+label,extra={1023:GEMM}))
    # Actual saved sample-7 model data, separate FCs and a 3-command chain.
    weights=[source_words(f"memory/weight_bank{i}.hex") for i in range(4)]
    bias=source_words("memory/bias.hex")
    fc=[source_words(f"expected/fc{i}_output.hex") for i in range(1,4)]
    inputs=[source_words("memory/buffer_a.hex"),fc[0],fc[1]]
    configs=[[0x80000000,0x80040000,0x80020000,0x800c0000,1,512,784,3,10,1],
             [0x80020000,0x80058800,0x80000000,0x800c0200,1,128,512,1,7,1],
             [0x80000000,0x8005c800,0x80020000,0x800c0280,1,10,128,2,7,0]]
    for i,c in enumerate(configs):
        b=Builder(capacity);b.load(c[0],inputs[i])
        g=(c[5]+3)//4;w=c[6]//4;off=(c[1]-0x80040000)//4;boff=(c[3]-0x800c0000)//4
        for lane in range(4):b.load(c[1]+lane*0x20000,weights[lane][off:off+g*w])
        b.load(c[3],bias[boff:boff+g]);b.cfg(c);b.words += [p2.TSTART,GEMM,p2.TSTOP]
        b.store(c[2],g,fc[i]);cases.append(b.finish(f"legacy_fc{i+1}"))
    b=Builder(capacity);b.load(0x80000000,inputs[0])
    for lane in range(4):b.load(0x80040000+lane*0x20000,weights[lane])
    b.load(0x800c0000,bias);b.words += [p2.TSTART]
    for i,c in enumerate(configs):
        b.cfg(c);b.words += [GEMM];b.store(c[2],len(fc[i]),fc[i])
    b.words += [p2.csrr(5,p2.RO["PERF_COUNT"]),p2.TSTOP]
    cases.append(b.finish("legacy_fc1_fc2_fc3_chain"))
    return cases

def interpret(image,initial,capacity,inject_pc):
    regs=[0]*8;settings={a:0 for a in p2.RW.values()}
    pc=0;armed=0;count=0;overflow=0;memory=dict(initial);sram={}
    records=[];bus=[];controls=[];numeric=[];gemm_acc=[0]*4;gemm_result=[0]*4
    for step in range(1024):
        assert pc%4==0 and 0<=pc<4096
        w=image.get(pc//4,0);op=w&127;rd=(w>>7)&31;f=(w>>12)&7;a=(w>>15)&31;b=(w>>20)&31
        err=0;status=0;used=[];value=None;update=None;arm_update=None
        address=w>>20;next_pc=pc+4;delay=2;block=False;store=False;scalar_memory=False;gemm=False
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
            elif w==GEMM:gemm=True
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
            if not status and not err and not gemm and not block and not scalar_memory:
                if next_pc%4:err=5
                elif not 0<=next_pc<=4092:err=6
            if gemm and not err:
                cfg=[settings[0x7c0+i] for i in range(10)]
                cfg_error=config_error(cfg);pc_error=5 if next_pc%4 else (6 if not 0<=next_pc<=4092 else 0)
                errors=[code for code in [cfg_error,pc_error] if code]
                err=min(errors,key={5:0,4:1,6:2,7:3}.__getitem__) if errors else 0
                delay=3
                if not err:
                    src,weight,dst,bias,m,n,k,bs,shift,act=cfg
                    groups=(n+3)//4;kw=k//4
                    output,starts,acc_updates,finals=kernel(sram,cfg,True)
                    runtime=(inject_pc==2)
                    abort=kw+12 if runtime else None
                    timeline={};flags={};num_updates={}
                    def event(age,kind,address,data):
                        if abort is None or age<abort:
                            timeline.setdefault(age,[]).append([step,age,kind,address,data])
                    def flag(age,mask):
                        if abort is None or age<abort:flags[age]=flags.get(age,0)|mask
                    for g in range(groups):
                        first=6+g*(kw+1);last=first+kw-1
                        for i in range(kw):
                            r=first+i
                            for address in [src+4*i]+[weight+lane*0x20000+4*(g*kw+i) for lane in range(4)]:
                                event(r,2,address,sram[address])
                            flag(r+1,1);flag(r+4,2)
                            num_updates.setdefault(r+4,{})["acc"]=acc_updates[g][i]
                        event(first,2,bias+4*g,sram[bias+4*g])
                        load_age=first+1 if g==0 else first+3
                        num_updates.setdefault(load_age,{})["acc"]=starts[g]
                        num_updates.setdefault(last+5,{})["result"]=finals[g]
                        if g==0:flag(first+1,4)
                        if g<groups-1:flag(last+5,4)
                        flag(last+5,8);flag(last+6,16)
                        event(last+6,3,dst+4*g,output[g])
                        if abort is None or last+6<abort:sram[dst+4*g]=output[g]
                    for age,change in sorted(num_updates.items()):
                        if abort is not None and age>=abort:continue
                        if "acc" in change:gemm_acc=change["acc"]
                        if "result" in change:gemm_result=change["result"]
                        numeric.append([step,age,*gemm_acc,*gemm_result])
                    for age,events_at_age in sorted(timeline.items()):
                        bus.extend(sorted(events_at_age,key=lambda row:row[3]))
                    controls.extend([[step,age,mask] for age,mask in sorted(flags.items())])
                    active_edges=kw+8 if runtime else groups*(kw+1)+6
                    if armed:
                        total=count+active_edges;overflow|=int(total>s.MASK);count=total&s.MASK
                    if runtime:err=6;delay=kw+13
                    else:delay=groups*(kw+1)+11
            if scalar_memory and not err:
                imm=((w>>25)<<5)|((w>>7)&31) if store else w>>20
                ea=regs[a]+s.signed(imm,12)
                err=p3.merge_memory_errors(p4.scalar_error(ea,capacity),5 if next_pc%4 else (6 if not 0<=next_pc<=4092 else 0))
                if not err:
                    delay=4
                    data=regs[b] if store else memory.get(ea,0)
                    bus.append([step,3,1 if store else 0,ea,data])
                    if store:memory[ea]=data
                    else:value=data
            if block and not err:
                src,dst,n=regs[a],regs[b],regs[rd]
                data_error=p3.error_for(src,dst,n,store,capacity)
                pc_error=5 if next_pc%4 else (6 if not 0<=next_pc<=4092 else 0)
                err=p3.merge_memory_errors(data_error,pc_error);delay=4
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
        if status:return records,bus,memory,controls,numeric
        pc=next_pc
    raise ValueError("reference did not halt")

def generate(directory,capacity,full,debug=False,case_name=None):
    directory.mkdir(parents=True,exist_ok=False)
    listing=[]
    selected=fixtures(capacity,full,debug and case_name is None)
    if case_name:
        selected=[c for c in selected if c[0]==case_name]
        assert len(selected)==1,("unknown scenario",case_name)
    for i,(name,image,initial,hook,legacy_expected) in enumerate(selected):
        trace,bus,memory,controls,numeric=interpret(image,initial,capacity,hook)
        for address,expected in legacy_expected.items():
            assert [memory[address+4*j] for j in range(len(expected))]==expected,("legacy layer mismatch",name)
        (directory/f"case_{i}.imem.hex").write_text("".join(f"@{a:08x}\n{w:08x}\n" for a,w in sorted(image.items())),encoding="ascii")
        (directory/f"case_{i}.dmem.hex").write_text("".join(f"@{(a-BASE)//4:08x}\n{w:08x}\n" for a,w in sorted(initial.items())),encoding="ascii")
        for suffix,rows in [("trace",trace),("bus",bus),("control",controls),("numeric",numeric),("final",[[a,v] for a,v in sorted(memory.items())])]:
            (directory/f"case_{i}.{suffix}.hex").write_text("".join(f"{v&s.MASK:08x}\n" for row in rows for v in row),encoding="ascii")
        listing.append({"id":i,"name":name,"steps":len(trace),"events":len(bus),"controls":len(controls),"numeric":len(numeric),
            "final_words":len(memory),"hook":hook,"error":trace[-1][4],"timer":trace[-1][25],
            "legacy_words":sum(map(len,legacy_expected.values()))})
    (directory/"cases.txt").write_text("".join(f"{c['id']} {c['steps']} {c['events']} {c['final_words']} {c['controls']} {c['numeric']} {c['hook']}\n" for c in listing),encoding="ascii")
    (directory/"cases.json").write_text(json.dumps(listing,indent=2),encoding="utf-8")
    (directory/"npu_phase5_profile.vh").write_text(f"localparam integer IMEM_BYTES=4096;\nlocalparam integer DMEM_BYTES={capacity};\nlocalparam integer EXPECTED_CASES={len(listing)};\nlocalparam integer EXPECTED_STEPS={sum(c['steps'] for c in listing)};\n",encoding="ascii")
    return listing
