"""Independent Phase 6 signed ARGMAX model, raw bounds and directed programs."""
import json
import random
from pathlib import Path
import phase2_vectors as p2
import phase3_vectors as p3
import phase4_vectors as p4
import phase5_vectors as p5
import run_phase1 as s
BASE=p3.BASE
GEMM=p5.GEMM
ARGMAX=0x0200202b
config_error=p5.config_error
kernel=p5.kernel

def argmax(rd):return ARGMAX | (rd<<7)

def arg_error(src,length):
    # Unbounded Python integers, independent from the RTL's 64-bit expressions.
    words=-(-length//4)
    bank=next(((base,depth) for base,depth in p3.BANKS[:2] if base<=src<base+0x20000),None)
    if src%4:return 5
    if bank is None:return 4
    limit=bank[0]+4*bank[1]
    if src>=limit or src+4*words>limit:return 6
    if not 1<=length<=10:return 7
    return 0

class Builder(p5.Builder):
    def arg_cfg(self,src,length):
        for address,value in [(0x7e0,src),(0x7e1,length)]:
            signed=s.signed(value&s.MASK,32)
            self.words += ([p2.seti(address,signed)] if -4096<=signed<=4095
                           else p2.li(4,value)+[p2.csrw(address,4)])

def fixtures(capacity,imem_bytes,profile):
    cases=[]
    def add(b,name,expected=0,hook=0,last=False,word=None,tags=()):
        cmd=argmax(5) if word is None else word
        if last:
            pos=len(b.words);b.words += [s.jal(0,imem_bytes-4-4*pos)]
            image=dict(enumerate(b.words));image[imem_bytes//4-1]=cmd
        else:image=dict(enumerate(b.words+[s.END]))
        assert max(image)<imem_bytes//4,name
        cases.append(dict(name=name,image=image,initial=b.initial,hook=hook,
                          expected=expected,tags=list(tags),last=last))
    def warm(b,bank,armed):
        # A real two-word LOAD gives count=6 only when armed; STORE must not count.
        address=p3.BANKS[bank][0]+32
        if armed:b.words += [p2.TSTART]
        b.load(address,[0x80ff7f01,0x01234567]);b.store(address,2)
    def normal(name,bank,length,values,src=None,rd=5,armed=True,hook=0,tags=(),warm_count=True):
        base,depth=p3.BANKS[bank];src=base+64 if src is None else src
        nwords=(length+3)//4
        packed=[p5.pack((values+[127]*3)[i:i+4]) for i in range(0,4*nwords,4)]
        before=int(src>base);after=int(src+4*nwords<base+4*depth)
        data=([0xa55aa55a] if before else [])+packed+([0x5aa55aa5] if after else [])
        b=Builder(capacity);b.load(src-4*before,data)
        if warm_count:warm(b,1-bank,armed)
        else:
            if armed:b.words += [p2.TSTART]
            b.store(src,nwords)
        out=BASE+0x800;b.initial[out]=0xdeadbeef
        pointer=7 if rd==6 else 6
        b.words += p2.li(pointer,out);b.arg_cfg(src,length)
        b.words += [argmax(rd),p4.sw(rd,pointer,0),p2.csrr(7,0x7f0),p2.TSTOP]
        b.store(src-4*before,len(data))
        add(b,name,expected=6 if hook==14 else 0,hook=hook,tags=tags)
    normal("debug_last_candidate_wins",0,10,[-128,-10,-9,-8,-7,-6,-5,-4,-3,126],tags=["A-01","A-03","A-15"])
    if profile=="debug":return cases
    if profile=="full":
        for bank in [0,1]:
            for length in [1,3,4,9,10]:
                for place in sorted(set([0,length//2,length-1])):
                    values=[-128+i for i in range(length)];values[place]=127
                    normal(f"signed_b{bank}_n{length}_max{place}",bank,length,values,tags=["A-01","A-02","A-10"])
                normal(f"ties_b{bank}_n{length}",bank,length,[-1]*length,tags=["A-02"])
            normal(f"padding_positive_b{bank}",bank,10,[-120,-119,-118,-117,-116,-115,-114,-113,-112,-111],tags=["A-03"])
            normal(f"no_update_b{bank}",bank,10,[0,-1,-2,-3,-4,-5,-6,-7,-8,-128],tags=["A-02"])
            normal(f"cross_word_tie_b{bank}",bank,10,[-9,-8,-7,126,-6,-5,-4,-3,126,-2],tags=["A-02"])
            for rd in range(8):
                normal(f"rd_b{bank}_r{rd}",bank,10,[-10,-9,-8,-7,-6,-5,-4,-3,-2,127],rd=rd,tags=["A-12"])
            normal(f"timer_off_b{bank}",bank,3,[-128,127,0],armed=False,tags=["A-14"])
            normal(f"T04_store_argmax_b{bank}",bank,4,[-128,-1,0,127],warm_count=False,tags=["A-14"])
        normal("atomic_arg_snapshot",0,10,[-9,-8,-7,-6,-5,-4,-3,-2,-1,127],hook=11,tags=["A-05"])
        normal("timer_overflow_state_hold",1,10,[127]*10,hook=12,tags=["A-14"])
        normal("reset_during_argmax",0,10,[-9,-8,-7,-6,-5,-4,-3,-2,-1,127],hook=13,tags=["A-16"])
        normal("runtime_index_abort",1,10,[-9,-8,-7,-6,-5,-4,-3,-2,-1,127],hook=14,tags=["A-09","A-16"])
        # No reset: change both source and length; initialize must replace a prior positive maximum.
        b=Builder(capacity);b.load(0x80000040,[p5.pack([127,-1,-2,-3])])
        b.load(0x80020040,[p5.pack([-128,-127,-126,-125]),p5.pack([-124,-123,-122,-121]),p5.pack([-120,-119,127,127])])
        b.words += [p2.TSTART]+p2.li(6,BASE+0x800)
        for i,(src,n,rd) in enumerate([(0x80000040,4,5),(0x80020040,10,5),(0x80000040,1,0),(0x80020040,3,5)]):
            b.arg_cfg(src,n);b.words += [argmax(rd),p4.sw(rd,6,i*4)]
        b.words += [p2.TSTOP];add(b,"consecutive_source_length_change",tags=["A-13","A-14"])
        # Actual GEMM then ARGMAX, without any implicit ARGMAX on GEMM completion.
        for direction in [0,1]:
            b,c=p5.synthetic(capacity,8,10,direction)
            b.cfg(c);b.words += [p2.TSTART,GEMM]
            Builder.arg_cfg(b,c[2],10);b.words += p2.li(6,BASE+0x800)+[argmax(5),p4.sw(5,6,0),p2.TSTOP]
            b.store(c[2],3);add(b,f"gemm_then_argmax_dir{direction}",tags=["A-13","A-14"])
        for bank in [0,1]:
            base,depth=p3.BANKS[bank];t=base+depth*4
            rows=[
                ("01",base,0,7),("02",base,11,7),("03",t-4,4,0),("04",t-4,5,6),
                ("05",t-12,10,0),("06",t-8,10,6),("07",t-12,11,7),("08",t-8,11,6),
                ("09",t,0,6),("10",t,1,6),("11",base+1,0,5),("12",base,16,7),
                ("13",base,0x10000001,6),("14",base,0xfffffffc,6),
                ("15",base,0xfffffffd,6),("16",base,0xffffffff,6),
                ("17a",t-4,1,0),("17b",t-4,3,0),("18",t-12,9,0)]
            for label,src,n,err in rows:
                tags=["A-06","A-07","A-B"+label[:2]]
                if err==0:normal(f"boundary_b{bank}_{label}",bank,n,list(range(-n,0)),src=src,tags=tags)
                else:
                    b=Builder(capacity);warm(b,1-bank,True);b.arg_cfg(src,n);b.words += [argmax(5)]
                    add(b,f"boundary_b{bank}_{label}",expected=err,tags=tags+["A-04","A-09"])
        sources=[0,BASE,0xf0000000,0x800e0000]+[p3.BANKS[i][0] for i in range(2,7)]
        for src in sources:
            for n in [0,11,0xffffffff]:
                for misaligned in [False,True]:
                    b=Builder(capacity);warm(b,0,True);b.arg_cfg(src+int(misaligned),n);b.words += [argmax(5)]
                    add(b,f"region_{src:08x}_n{n}_mis{int(misaligned)}",5 if misaligned else 4,tags=["A-04","A-09","A-10"])
        for rd in range(8,32):
            b=Builder(capacity);b.arg_cfg(0x80000001,0);b.words += [argmax(rd)]
            add(b,f"invalid_rd_{rd}",2,tags=["A-11"])
        for label,word in [("rs1",argmax(31)|(31<<15)),("rs2",argmax(31)|(31<<20)),
                           ("funct7",GEMM|(2<<25))]:
            b=Builder(capacity);b.words += [word];add(b,"illegal_"+label,8,tags=["A-11"])
        for a in [0x7df,0x7e2,0x7ff,0x7f0]:
            b=Builder(capacity);b.words += [p2.csrw(a,0),argmax(5)]
            add(b,f"csr_error_{a:x}",3,tags=["A-11"])
    # Last-IMEM matrix in both 4KiB and 64KiB profiles, with warm nonzero state.
    for bank in [0,1]:
        base,depth=p3.BANKS[bank];t=base+4*depth
        for armed in [False,True]:
            for rd in [0,5]:
                for label,src,n,err in [
                    ("01",base+1,0,5),("02w",0x80040000,0,4),("02b",0x800c0000,11,4),
                    ("02d",BASE,11,4),("03",t-8,11,6),
                    *[("04n"+str(n),base,n,6) for n in [1,3,4,9,10]],
                    ("05n0",base,0,6),("05n11",base,11,6)]:
                    b=Builder(capacity);warm(b,1-bank,armed);b.arg_cfg(src,n)
                    add(b,f"pc_b{bank}_arm{int(armed)}_r{rd}_{label}",err,last=True,word=argmax(rd),
                        tags=["A-08","A-09","A-P"+label[:2]])
            for label,word,err in [("06",argmax(31)|(31<<15),8),("07r8",argmax(8),2),("07r31",argmax(31),2)]:
                b=Builder(capacity);warm(b,1-bank,armed);b.arg_cfg(base+1,0)
                add(b,f"pc_b{bank}_arm{int(armed)}_{label}",err,last=True,word=word,tags=["A-08","A-09","A-11","A-P"+label[:2]])
    if profile=="pc":cases=[c for c in cases if c["last"]]
    return cases

def interpret(image,initial,capacity,inject_pc,imem_bytes=4096):
    regs=[0]*8;settings={a:0 for a in p2.RW.values()}
    pc=0;armed=0;count=0;overflow=0;memory=dict(initial);sram={}
    records=[];bus=[];controls=[];numeric=[];gemm_acc=[0]*4;gemm_result=[0]*4;arg_events=[];arg_max=0;arg_best=0
    for step in range(1024):
        assert pc%4==0 and 0<=pc<imem_bytes
        w=image.get(pc//4,0);op=w&127;rd=(w>>7)&31;f=(w>>12)&7;a=(w>>15)&31;b=(w>>20)&31
        err=0;status=0;used=[];value=None;update=None;arm_update=None
        address=w>>20;next_pc=pc+4;delay=2;block=False;store=False;scalar_memory=False;gemm=False;arg=False
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
            elif f==2 and w>>25==1:
                arg=True;used=[rd]
                if a or b:err=8
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
            if not status and not err and not gemm and not arg and not block and not scalar_memory:
                if next_pc%4:err=5
                elif not 0<=next_pc<=imem_bytes-4:err=6
            if gemm and not err:
                cfg=[settings[0x7c0+i] for i in range(10)]
                cfg_error=config_error(cfg);pc_error=5 if next_pc%4 else (6 if not 0<=next_pc<=imem_bytes-4 else 0)
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
            if arg and not err:
                src=settings[0x7e0];length=settings[0x7e1]
                pc_error=5 if next_pc%4 else (6 if not 0<=next_pc<=imem_bytes-4 else 0)
                err=p3.merge_memory_errors(arg_error(src,length),pc_error);delay=3
                if not err:
                    if inject_pc==12:count=0xfffffffe;overflow=1;armed=1
                    words=(length+3)//4
                    values=[]
                    for j in range(words):
                        data=sram[src+4*j]
                        if inject_pc!=14 or j==0:bus.append([step,5+5*j,2,src+4*j,data])
                        values.extend(p5.bytes4(data))
                    # Semantic expected value: first maximum in the valid signed prefix.
                    winner=max(range(length),key=values.__getitem__)
                    for i in range(1 if inject_pc==14 else length):
                        age=6+5*(i//4)+i%4;candidate=values[i];greater=int(candidate>arg_max)
                        old_max=arg_max
                        if i==0 or greater:arg_max=candidate;arg_best=i
                        arg_events.append([step,age,i,sram[src+4*(i//4)],candidate&s.MASK,
                                           old_max&s.MASK,greater,int(i==0),arg_max&s.MASK,arg_best])
                    if inject_pc==14:err=6;delay=8
                    else:
                        assert arg_best==winner
                        value=winner;delay=5+length+words
            if scalar_memory and not err:
                imm=((w>>25)<<5)|((w>>7)&31) if store else w>>20
                ea=regs[a]+s.signed(imm,12)
                err=p3.merge_memory_errors(p4.scalar_error(ea,capacity),5 if next_pc%4 else (6 if not 0<=next_pc<=imem_bytes-4 else 0))
                if not err:
                    delay=4
                    data=regs[b] if store else memory.get(ea,0)
                    bus.append([step,3,1 if store else 0,ea,data])
                    if store:memory[ea]=data
                    else:value=data
            if block and not err:
                src,dst,n=regs[a],regs[b],regs[rd]
                data_error=p3.error_for(src,dst,n,store,capacity)
                pc_error=5 if next_pc%4 else (6 if not 0<=next_pc<=imem_bytes-4 else 0)
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
        if status:return records,bus,memory,controls,numeric,arg_events
        pc=next_pc
    raise ValueError("reference did not halt")

def generate(directory,capacity,profile,imem_bytes=4096,case_name=None):
    directory.mkdir(parents=True,exist_ok=False);listing=[]
    selected=fixtures(capacity,imem_bytes,profile)
    if case_name:
        selected=[c for c in selected if c["name"]==case_name];assert len(selected)==1,case_name
    for i,c in enumerate(selected):
        trace,bus,memory,controls,numeric,args=interpret(c["image"],c["initial"],capacity,c["hook"],imem_bytes)
        assert trace[-1][4]==c["expected"],(c["name"],trace[-1][4],c["expected"])
        if c["last"]:
            assert trace[-1][0]==trace[-1][2]==imem_bytes-4
            assert trace[-1][5:25]==trace[-2][5:25]
            assert all(e[0]!=len(trace)-1 for e in bus)
        (directory/f"case_{i}.imem.hex").write_text("".join(f"@{a:08x}\n{w:08x}\n" for a,w in sorted(c["image"].items())),encoding="ascii")
        (directory/f"case_{i}.dmem.hex").write_text("".join(f"@{(a-BASE)//4:08x}\n{w:08x}\n" for a,w in sorted(c["initial"].items())),encoding="ascii")
        for suffix,rows in [("trace",trace),("bus",bus),("control",controls),("numeric",numeric),("arg",args),("final",[[a,v] for a,v in sorted(memory.items())])]:
            (directory/f"case_{i}.{suffix}.hex").write_text("".join(f"{v&s.MASK:08x}\n" for row in rows for v in row),encoding="ascii")
        listing.append(dict(id=i,name=c["name"],steps=len(trace),events=len(bus),controls=len(controls),numeric=len(numeric),
                            args=len(args),final_words=len(memory),hook=c["hook"],error=trace[-1][4],timer=trace[-1][25],
                            legacy_words=0,tags=c["tags"],last=c["last"]))
    (directory/"cases.txt").write_text("".join(f"{c['id']} {c['steps']} {c['events']} {c['final_words']} {c['controls']} {c['numeric']} {c['args']} {c['hook']}\n" for c in listing),encoding="ascii")
    (directory/"cases.json").write_text(json.dumps(listing,indent=2),encoding="utf-8")
    (directory/"npu_phase6_profile.vh").write_text(f"localparam integer IMEM_BYTES={imem_bytes};\nlocalparam integer DMEM_BYTES={capacity};\nlocalparam integer EXPECTED_CASES={len(listing)};\nlocalparam integer EXPECTED_STEPS={sum(c['steps'] for c in listing)};\n",encoding="ascii")
    return listing
