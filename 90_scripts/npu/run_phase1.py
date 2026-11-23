"""Phase 1 only: scalar machine-word fixtures, independent interpreter and XSim.
Run from the repository root: python -B 90_scripts/npu/run_phase1.py --legacy
This is a directed-test encoder, not the Phase 7 assembly/scenario toolchain.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "90_scripts"))
import run as legacy

SOURCES = [
    "04_rtl/isa/npu_isa_pkg.sv",
    "04_rtl/isa/instruction_decoder.sv",
    "04_rtl/isa/register_file.sv",
    "04_rtl/isa/scalar_alu.sv",
    "04_rtl/isa/instruction_controller.sv",
    "04_rtl/controller/npu_top.sv",
    "05_tb/npu/tb_npu_phase1.sv",
]
MASK = (1 << 32) - 1
END = 0x0400302b

def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value

def lui(rd, value):
    return ((value & 0xfffff) << 12) | (rd << 7) | 0x37

def addi(rd, rs, value):
    assert -2048 <= value <= 2047
    return ((value & 0xfff) << 20) | (rs << 15) | (rd << 7) | 0x13

def add(rd, a, b):
    return (b << 20) | (a << 15) | (rd << 7) | 0x33

def branch(a, b, offset, ne=False):
    assert -4096 <= offset <= 4094 and offset % 2 == 0
    x = offset & 0x1fff
    return (((x >> 12) & 1) << 31) | (((x >> 5) & 63) << 25) | (b << 20) | (a << 15) | (int(ne) << 12) | (((x >> 1) & 15) << 8) | (((x >> 11) & 1) << 7) | 0x63

def jal(rd, offset):
    assert -(1 << 20) <= offset < (1 << 20) and offset % 2 == 0
    x = offset & 0x1fffff
    return (((x >> 20) & 1) << 31) | (((x >> 1) & 1023) << 21) | (((x >> 11) & 1) << 20) | (((x >> 12) & 255) << 12) | (rd << 7) | 0x6f

def fixtures(size):
    cases = []
    def push(name, words, extra=None):
        image = dict(enumerate(words))
        if extra:
            image.update(extra)
        assert all(0 <= i < size // 4 for i in image), name
        cases.append((name, image))
    push("end_only", [END])
    push("arithmetic_signed_wrap_alias_r0", [
        lui(1, 0x80000), addi(1, 1, -1), add(2, 1, 1),
        addi(3, 0, -2048), addi(4, 0, 2047), add(4, 3, 4),
        lui(5, 0xfffff), addi(5, 5, -2048), add(5, 5, 5),
        lui(0, 0xfffff), addi(0, 1, 1), add(0, 1, 2), END])
    push("bne_backward_loop_beq", [
        addi(1, 0, 0), addi(2, 0, 7), addi(1, 1, 1),
        branch(1, 2, -4, True), branch(1, 2, 8),
        0x7f, branch(1, 2, 4, True), END])
    push("beq_backward_loop", [
        addi(1,0,3), addi(1,1,-1), branch(1,0,8),
        branch(0,0,-8), END])
    push("jal_link_zero_and_backward", [
        jal(5, 12), END, jal(0,-4), addi(6,5,0), jal(0,-8)])
    push("unused_u_j_fields_are_not_gprs", [lui(7,0xfffff), jal(0,8), 0x7f, END])
    for ne in [False, True]:
        # ne=false -> 0 != 1; ne=true -> 0 == 0, both non-taken.
        b = 0 if ne else 1
        for offset in [2, -4096, 4094]:
            push(f"non_taken_{ne}_{offset}", [addi(1,0,1), branch(0,b,offset,ne), END])
        push(f"taken_misalign_{ne}", [addi(1,0,1), branch(0,1 if ne else 0,2,ne)])
        push(f"taken_bounds_{ne}", [jal(0,size-8)], {
            size//4-2: branch(0,1 if ne else 0,8,ne),
            # For BNE ensure a true comparison without initial register writes.
            **({0:addi(1,0,1),1:jal(0,size-12)} if ne else {})
        })
    push("last_word_end", [jal(5,size-4)], {size//4-1:END})
    push("last_word_sequential_bounds", [jal(0,size-4)], {size//4-1:addi(1,0,1)})
    push("last_word_non_taken_bounds", [addi(1,0,1),jal(0,size-8)], {size//4-1:branch(0,1,-4)})
    push("capacity_outside_jal_link_unchanged", [addi(5,0,123),jal(5,size-4)])
    push("unused_word_zero_fill", [jal(0,128)])
    for offset in [2, -2, -1048576, 1048574]:
        push(f"jal_target_{offset}", [addi(5,0,123),jal(5,offset)])
    for reg in [8,31]:
        for name, word in [
            ("lui_rd",lui(reg,0xabcd1)),("addi_rd",addi(reg,0,1)),
            ("addi_rs1",addi(1,reg,0)),("add_rd",add(reg,0,0)),
            ("add_rs1",add(1,reg,0)),("add_rs2",add(1,0,reg)),
            ("beq_rs1",branch(reg,0,4)),("bne_rs2",branch(0,reg,4,True)),
            ("jal_rd",jal(reg,2))]:
            push(f"invalid_r{reg}_{name}",[addi(1,0,123),word])
    bad = [
        ("unknown_opcode",0xffffffff),("zero_instruction",0),
        ("addi_funct3",addi(1,31,1)|(1<<12)),
        ("add_funct3",add(1,0,31)|(1<<12)),
        ("add_funct7",add(1,31,0)|(0x20<<25)),
        ("branch_funct3",branch(31,31,2)|(2<<12)),
        ("end_rd",END|(1<<7)),("end_rs1",END|(31<<15)),
        ("end_rs2",END|(1<<20)),("end_funct7",END|(4<<25)),
    ]
    for name, word in bad:
        push(name,[addi(1,0,99),word])
    for seed in range(8):
        rng=random.Random(1000+seed)
        words=[]
        for _ in range(40):
            rd,a,b=(rng.randrange(8) for _ in range(3))
            op=rng.randrange(6)
            words.append([
                lui(rd,rng.randrange(1<<20)), addi(rd,a,rng.randrange(-2048,2048)),
                add(rd,a,b), branch(a,b,rng.choice([4,8])),
                branch(a,b,rng.choice([4,8]),True), jal(rd,rng.choice([4,8]))
            ][op])
        push(f"random_seed_{1000+seed}",words+[END,END])
    return cases

def interpret(image, size):
    """ISA reference uses unbounded signed Python PC arithmetic, independent of RTL."""
    regs=[0]*8
    pc=0
    records=[]
    for _ in range(4096):
        assert 0 <= pc <= size-4 and pc % 4 == 0
        word=image.get(pc//4,0)
        opcode=word & 127
        rd=(word>>7)&31
        f3=(word>>12)&7
        a=(word>>15)&31
        b=(word>>20)&31
        err=0; status=0; next_pc=pc+4; value=None; used=[]
        # Validate instruction form before register operands.
        if opcode==0x37:
            used=[rd]; value=word & 0xfffff000
        elif opcode==0x13:
            if f3 != 0: err=8
            used=[rd,a]
        elif opcode==0x33:
            if f3 != 0 or word>>25: err=8
            used=[rd,a,b]
        elif opcode==0x63:
            if f3 not in [0,1]: err=8
            used=[a,b]
        elif opcode==0x6f:
            used=[rd]
        elif opcode==0x2b:
            if word!=END: err=8
            else: status=1
        else:
            err=1
        if not err and any(r>=8 for r in used): err=2
        if not err:
            if opcode==0x13:
                value=regs[a]+signed(word>>20,12)
            elif opcode==0x33:
                value=regs[a]+regs[b]
            elif opcode==0x63:
                offset=(((word>>31)&1)<<12)|(((word>>7)&1)<<11)|(((word>>25)&63)<<5)|(((word>>8)&15)<<1)
                if (regs[a]!=regs[b]) if f3 else (regs[a]==regs[b]):
                    next_pc=pc+signed(offset,13)
            elif opcode==0x6f:
                offset=(((word>>31)&1)<<20)|(((word>>12)&255)<<12)|(((word>>20)&1)<<11)|(((word>>21)&1023)<<1)
                next_pc=pc+signed(offset,21); value=pc+4
            if not status:
                if next_pc % 4: err=5
                elif next_pc<0 or next_pc+4>size: err=6
        if err:
            status=2
        if status:
            next_pc=pc
        elif value is not None and rd!=0:
            regs[rd]=value&MASK
        records.append([pc,word,next_pc,status,err,*regs])
        if status: return records
        pc=next_pc
    raise ValueError("reference program did not terminate")

def generate(directory, size):
    directory.mkdir(parents=True,exist_ok=False)
    cases=fixtures(size)
    metadata=[]
    listing=[]
    for index,(name,image) in enumerate(cases):
        trace=interpret(image,size)
        # Sparse readmemh file; TB explicitly zero-fills the full allocated IMEM first.
        (directory/f"case_{index}.imem.hex").write_text(
            "".join(f"@{i:08x}\n{w:08x}\n" for i,w in sorted(image.items())),encoding="ascii")
        (directory/f"case_{index}.trace.hex").write_text(
            "".join(f"{w&MASK:08x}\n" for record in trace for w in record),encoding="ascii")
        metadata.append(f"{index} {len(trace)}\n")
        listing.append({"id":index,"name":name,"steps":len(trace),"status":trace[-1][3],"error":trace[-1][4]})
    (directory/"cases.txt").write_text("".join(metadata),encoding="ascii")
    total=sum(x["steps"] for x in listing)
    (directory/"npu_phase1_profile.vh").write_text(
        f"localparam integer IMEM_BYTES={size};\nlocalparam integer DMEM_BYTES=16777216;\n"
        f"localparam integer EXPECTED_CASES={len(cases)};\nlocalparam integer EXPECTED_STEPS={total};\n",encoding="ascii")
    legacy.save_json(directory/"cases.json",listing)
    return len(cases),total

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-bin",type=Path,help="Vivado bin; default: search PATH")
    parser.add_argument("--legacy",action="store_true",help="also run existing five RTL targets and Python unit tests")
    args=parser.parse_args()
    # Fixed independent encoding sanity checks, not decoded with RTL helpers.
    assert addi(1,0,-1)==0xfff00093 and lui(7,0xfffff)==0xfffff3b7
    assert branch(1,2,-4,True)==0xfe209ee3 and jal(0,8)==0x0080006f
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    run_id="npu_phase1_"+stamp
    out=ROOT/"07_runs"/run_id
    out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"99_build"/run_id
    build.mkdir(parents=True,exist_ok=False)
    print("[RUN] "+str(out),flush=True)
    record={"phase":1,"git":legacy.git_state(ROOT),"python":sys.version,"stages":[],
            "waveform_recording":False,"sources_sha256":{}}
    metrics={"status":"ERROR","profiles":[],"legacy":[],"phase2_started":False}
    tracked=subprocess.check_output(["git","ls-files","04_rtl","05_tb","90_scripts"],cwd=ROOT,text=True).splitlines()
    before={p:legacy.sha256(ROOT/p) for p in tracked if (ROOT/p).is_file()}
    exit_code=2
    try:
        tools=legacy.find_tools(args.vivado_bin)
        snap=out/"source_snapshot"
        for name in SOURCES+["90_scripts/npu/run_phase1.py","90_scripts/run.py"]:
            p=snap/name; p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,p)
            record["sources_sha256"][name]=legacy.sha256(p)
        for size in [65536,256]:
            data=out/"data"/str(size)
            cases,steps=generate(data,size)
            logs=out/"logs"/str(size); logs.mkdir(parents=True)
            work=build/str(size); work.mkdir()
            commands=[
                ("compile","xvlog",["-sv","-i",data.as_posix(),*[(snap/p).as_posix() for p in SOURCES],"-log","xvlog.log"]),
                ("elaborate","xelab",["work.tb_npu_phase1","-s","phase1_sim","-debug","off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",["phase1_sim","-R","-onerror","quit","-onfinish","quit","-testplusarg","DATA_DIR="+data.as_posix(),"-log","xsim.log"]),
            ]
            for stage,tool,arguments in commands:
                code,text=legacy.run_stage(stage,tools[tool],arguments,work,logs,120,record["stages"])
                if code or legacy.ERROR_LINE.search(text):
                    print(text[-4000:],flush=True)
                    raise RuntimeError(f"{size} {stage} failed; see {logs}")
            found=re.findall(r"^\[PHASE1\] result=PASS profile=(\d+) cases=(\d+) steps=(\d+) checks=(\d+)$",text,re.M)
            if len(found)!=1 or tuple(map(int,found[0][:3]))!=(size,cases,steps) or int(found[0][3])<=0:
                raise RuntimeError("missing/incomplete Phase 1 scoreboard summary")
            result={"imem_bytes":size,"cases":cases,"steps":steps,"checks":int(found[0][3]),"status":"PASS"}
            metrics["profiles"].append(result)
            print("[PROFILE] "+json.dumps(result),flush=True)
        if args.legacy:
            jobs=[("runner_unit",[sys.executable,"-B","-m","unittest","discover","-s","90_scripts/tests","-v"]),
                  ("golden_unit",[sys.executable,"-B","-m","unittest","discover","-s","03_model/golden/tests","-v"])]
            jobs += [(t,[sys.executable,"-B","90_scripts/run.py",t,"--vivado-bin",str(tools["xsim"].parent)])
                     for t in ["control_unit","memory_wrapper","mac_array","accumulator_postprocess","mlp_top"]]
            for name,command in jobs:
                log=out/(name+".log")
                print("[LEGACY] "+name,flush=True)
                with log.open("w",encoding="utf-8") as stream:
                    code=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=1000).returncode
                text=log.read_text(encoding="utf-8")
                item={"name":name,"command":command,"return_code":code,"log":str(log)}
                metrics["legacy"].append(item)
                if code:
                    print(text[-4000:],flush=True)
                    raise RuntimeError(name+" legacy regression failed")
                print("[LEGACY_PASS] "+name,flush=True)
        metrics.update(status="PASS",reason="all requested scoreboards and regressions completed")
        exit_code=0
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        metrics["reason"]=str(error)
        print("[ERROR] "+str(error),flush=True)
    finally:
        changed=[p for p,h in before.items() if not (ROOT/p).is_file() or legacy.sha256(ROOT/p)!=h]
        metrics["legacy_integrity"]={"files":len(before),"changed_or_deleted":changed}
        if changed:
            metrics.update(status="FAIL",reason="legacy source changed during run")
            exit_code=1
        record["finished_utc"]=datetime.now(timezone.utc).isoformat()
        # Hash all generated fixtures so data provenance is reproducible.
        record["data_sha256"]={p.relative_to(out).as_posix():legacy.sha256(p) for p in (out/"data").rglob("*") if p.is_file()}
        legacy.save_json(out/"manifest.json",record)
        legacy.save_json(out/"metrics.json",metrics)
        (out/"README.md").write_text("# NPU Phase 1\n\nResult: "+metrics["status"]+"\n\n"
            "See metrics.json, manifest.json, logs/, data/cases.json and source_snapshot/.\n"
            "No Phase 2, waveform, synthesis or implementation was performed.\n",encoding="utf-8")
        print("[RESULT] "+metrics["status"]+" "+str(out),flush=True)
    return exit_code

if __name__=="__main__":
    raise SystemExit(main())
