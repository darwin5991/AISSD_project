"""PC boundary plus memory faults: independent expected codes and full ISA traces."""
import json
import phase2_vectors as p2
import phase3_vectors as p3
import phase4_vectors as p4
import phase5_vectors as p5
import run_phase1 as s
BASE=p3.BASE
OPS=["LW","SW","LOAD","STORE"]
def fixtures(capacity,full,debug=False,case_name=None):
    cases=[]
    def push(op,label,armed,word,setup,expected,mandatory=False):
        words=[p2.seti(a,100+i) for i,a in enumerate(p2.RW.values())]
        words += [s.addi(i,0,300+i) for i in range(1,8)]
        if armed:words += [p2.TSTART]
        # Successful LOAD seeds SRAM and PERF=6; STORE confirms it without counting.
        words += p2.li(1,BASE)+p2.li(2,0x80000000)+p2.li(3,8)+[p3.transfer(1,2,3)]
        words += p2.li(1,0x80000000)+p2.li(2,BASE+0x100)+[p3.transfer(1,2,3,True)]
        words += setup
        pos=len(words);words += [s.jal(0,4092-4*pos)]
        image=dict(enumerate(words));image[1023]=word
        initial={BASE:0x80ff01a5,BASE+4:0x01234567,BASE+0xfc:0xa55aa55a,
                 BASE+0x108:0x5aa55aa5,BASE+capacity-4:0x76543210}
        cases.append({"name":f"{op}_{label}_armed{int(armed)}","image":image,"initial":initial,
                      "expected":expected,"armed":armed,"mandatory":mandatory})
    for armed in [True,False]:
        for op in OPS:
            for label,expected in [("alignment",5),("region",4),("bounds",6),("valid_data",6)]:
                if op in ["LW","SW"]:
                    addr={"alignment":BASE+4,"region":0xf0000000,"bounds":BASE+capacity-4,"valid_data":BASE+8}[label]
                    imm=-3 if label=="alignment" else (4 if label=="bounds" else 0)
                    word=p4.lw(4,1,imm) if op=="LW" else p4.sw(4,1,imm)
                    setup=p2.li(1,addr)
                else:
                    store=op=="STORE"
                    if store:
                        src=0x80000001 if label=="alignment" else (0x800e0000 if label=="region" else 0x80000000)
                        dst=BASE+capacity if label=="bounds" else BASE+0x100
                    else:
                        src=BASE+1 if label=="alignment" else (0xf0000000 if label=="region" else (BASE+capacity if label=="bounds" else BASE))
                        dst=0x80000000
                    setup=p2.li(1,src)+p2.li(2,dst)+p2.li(3,4)
                    word=p3.transfer(1,2,3,store)
                push(op,label,armed,word,setup,expected,True)
            if op in ["LW","SW"]:
                baseword=p4.lw(4,1,0) if op=="LW" else p4.sw(4,1,0)
                push(op,"alignment_before_region",armed,baseword,p2.li(1,0xf0000001),5)
                word=p4.lw(8,1,1) if op=="LW" else p4.sw(31,1,1)
                push(op,"gpr_before_memory",armed,word,p2.li(1,BASE),2)
                word=p4.lw(31,31,-3) if op=="LW" else p4.sw(31,31,-3)
                push(op,"encoding_before_gpr",armed,word|(1<<12),[],8)
            else:
                store=op=="STORE";word=p3.transfer(1,2,3,store)
                setup=p2.li(1,0x80000000 if store else BASE)+p2.li(2,BASE if store else 0x80000000)
                for label,n,expected in [("zero_length_before_pc",0,6),("length_alignment_before_pc",2,5)]:
                    push(op,label,armed,word,setup+p2.li(3,n),expected)
                setup=p2.li(1,0x80000310 if store else BASE)+p2.li(2,BASE if store else 0x80000310)+p2.li(3,4)
                push(op,"sram_bounds",armed,word,setup,6)
                setup=p2.li(1,0xf0000001)+p2.li(2,0x800e0000)+p2.li(3,0)
                push(op,"alignment_before_region",armed,word,setup,5)
                word=p3.transfer(31,2,3,True) if store else p3.transfer(1,2,8)
                push(op,"gpr_before_memory",armed,word,setup,2)
                push(op,"encoding_before_gpr",armed,p3.transfer(31,31,31,store)|(1<<25),[],8)
        push("CSR","invalid_before_pc",armed,p2.csrr(5,0x7f4),[],3)
        push("CSR","readonly_before_pc",armed,p2.csrw(p2.RO["PERF_COUNT"],0),[],3)
        push("OPCODE","invalid_before_pc",armed,0xffffffff,[],1)
    if not full:cases=[c for c in cases if c["mandatory"] and c["armed"]]
    if case_name:
        cases=[c for c in cases if c["name"]==case_name];assert len(cases)==1,case_name
    elif debug:cases=cases[:1]
    return cases

def generate(directory,capacity,full,debug=False,case_name=None):
    directory.mkdir(parents=True,exist_ok=False);listing=[]
    for i,c in enumerate(fixtures(capacity,full,debug,case_name)):
        trace,bus,memory,controls,numeric=p5.interpret(c["image"],c["initial"],capacity,0)
        assert trace[-1][0]==trace[-1][2]==4092 and trace[-1][4]==c["expected"],c["name"]
        assert trace[-1][5:25]==trace[-2][5:25] and trace[-1][25]==(6 if c["armed"] else 0)
        assert all(event[0]!=len(trace)-1 for event in bus),"faulting command accessed memory"
        assert not controls and not numeric
        (directory/f"case_{i}.imem.hex").write_text("".join(f"@{a:08x}\n{w:08x}\n" for a,w in sorted(c["image"].items())),encoding="ascii")
        (directory/f"case_{i}.dmem.hex").write_text("".join(f"@{(a-BASE)//4:08x}\n{w:08x}\n" for a,w in sorted(c["initial"].items())),encoding="ascii")
        for suffix,rows in [("trace",trace),("bus",bus),("control",controls),("numeric",numeric),("final",[[a,v] for a,v in sorted(memory.items())])]:
            (directory/f"case_{i}.{suffix}.hex").write_text("".join(f"{v&s.MASK:08x}\n" for row in rows for v in row),encoding="ascii")
        listing.append({"id":i,"name":c["name"],"steps":len(trace),"events":len(bus),"controls":0,"numeric":0,
            "final_words":len(memory),"hook":0,"error":trace[-1][4],"timer":trace[-1][25],
            "legacy_words":0,"mandatory":c["mandatory"],"armed":c["armed"]})
    (directory/"cases.txt").write_text("".join(f"{c['id']} {c['steps']} {c['events']} {c['final_words']} 0 0 0\n" for c in listing),encoding="ascii")
    (directory/"cases.json").write_text(json.dumps(listing,indent=2),encoding="utf-8")
    (directory/"fault_priority_profile.vh").write_text(f"localparam integer IMEM_BYTES=4096;\nlocalparam integer DMEM_BYTES={capacity};\nlocalparam integer EXPECTED_CASES={len(listing)};\nlocalparam integer EXPECTED_STEPS={sum(c['steps'] for c in listing)};\n",encoding="ascii")
    return listing
