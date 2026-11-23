"""Phase 2 CSR/Timer verification. No Phase 3 memory operations."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
import run_phase1 as scalar
import phase2_vectors as vectors

ROOT=scalar.ROOT
legacy=scalar.legacy
RTL=scalar.SOURCES[:-1]

def check_contract():
    spec=(ROOT/"00_docs/programmable_npu/01_isa_spec.md").read_text(encoding="utf-8")
    q=chr(96)
    doc={name:int(value,16) for value,name in re.findall(r"\| "+q+r"0x([0-9a-fA-F]{3})"+q+r" \| "+q+r"([A-Z0-9_]+)"+q,spec)}
    pkg=(ROOT/"04_rtl/isa/npu_isa_pkg.sv").read_text()
    sv={name:int(value,16) for name,value in re.findall(r"\bCSR_(\w+)\s*=\s*12'h([0-9a-f]+)",pkg)}
    assert doc==vectors.CSR==sv,(doc,vectors.CSR,sv)
    assert vectors.seti(vectors.RW["M"],1)==0x000be20b
    assert vectors.TSTART==0x0000302b and vectors.TSTOP==0x0200302b
    assert vectors.csrw(0x7c0,1)==0x7c009073
    assert vectors.csrr(5,0x7c0)==0x7c0022f3
    return doc

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-bin",type=Path,help="Vivado bin; default: PATH")
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    run_id="npu_phase2_"+stamp
    out=ROOT/"07_runs"/run_id;out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"99_build"/run_id;build.mkdir(parents=True,exist_ok=False)
    print("[RUN] "+str(out),flush=True)
    record={"phase":2,"git":legacy.git_state(ROOT),"python":sys.version,"stages":[],"sources_sha256":{},"waveform_recording":False}
    metrics={"status":"ERROR","profiles":[],"unit":None,"synthetic_active":None,"phase3_started":False}
    code=2
    try:
        record["csr_contract"]=check_contract()
        tools=legacy.find_tools(args.vivado_bin)
        snap=out/"source_snapshot"
        names=RTL+["05_tb/npu/tb_npu_phase2.sv","05_tb/npu/tb_npu_phase2_units.sv",
            "05_tb/npu/tb_npu_phase2_active.sv","90_scripts/npu/run_phase1.py",
            "90_scripts/npu/run_phase2.py","90_scripts/npu/phase2_vectors.py","90_scripts/run.py"]
        for name in names:
            p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
            record["sources_sha256"][name]=legacy.sha256(p)
        jobs=[]
        for size in [65536,256]:
            data=out/"data"/str(size)
            cases,steps=vectors.generate(data,size)
            jobs.append((str(size),"tb_npu_phase2","05_tb/npu/tb_npu_phase2.sv",data,cases,steps))
        jobs += [("units","tb_npu_phase2_units","05_tb/npu/tb_npu_phase2_units.sv",None,0,0),
                 ("active","tb_npu_phase2_active","05_tb/npu/tb_npu_phase2_active.sv",None,0,0)]
        for name,tb,tb_file,data,cases,steps in jobs:
            work=build/name;work.mkdir()
            logs=out/"logs"/name;logs.mkdir(parents=True)
            include=["-i",data.as_posix()] if data else []
            commands=[
                ("compile","xvlog",["-sv",*include,*[(snap/p).as_posix() for p in RTL],(snap/tb_file).as_posix(),"-log","xvlog.log"]),
                ("elaborate","xelab",["work."+tb,"-s","phase2_sim","-debug","off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",["phase2_sim","-R","-onerror","quit","-onfinish","quit",
                    *(["-testplusarg","DATA_DIR="+data.as_posix()] if data else []),"-log","xsim.log"]),
            ]
            for stage,tool,arguments in commands:
                rc,text=legacy.run_stage(stage,tools[tool],arguments,work,logs,120,record["stages"])
                if rc or legacy.ERROR_LINE.search(text):
                    print(text[-5000:],flush=True)
                    raise RuntimeError(name+" "+stage+" failed; see "+str(logs))
            if data:
                result=re.findall(r"^\[PHASE2\] result=PASS profile=(\d+) cases=(\d+) steps=(\d+) checks=(\d+)$",text,re.M)
                assert len(result)==1 and tuple(map(int,result[0][:3]))==(int(name),cases,steps) and int(result[0][3])>0,"incomplete scoreboard"
                item={"imem_bytes":int(name),"cases":cases,"steps":steps,"checks":int(result[0][3]),"status":"PASS"}
                metrics["profiles"].append(item)
            elif name=="units":
                result=re.findall(r"^\[PHASE2_UNITS\] result=PASS csr_addresses=(\d+) timer_edges=(\d+) checks=(\d+)$",text,re.M)
                assert len(result)==1 and int(result[0][0])==4096 and int(result[0][1])>=150 and int(result[0][2])>8192
                item={"csr_addresses":4096,"timer_edges":int(result[0][1]),"checks":int(result[0][2]),"status":"PASS"}
                metrics["unit"]=item
            else:
                result=re.findall(r"^\[PHASE2_ACTIVE\] result=PASS instructions=(\d+) cycles=(\d+) checks=(\d+)$",text,re.M)
                assert len(result)==1 and int(result[0][0])==9 and int(result[0][2])>0
                item={"instructions":9,"cycles":int(result[0][1]),"checks":int(result[0][2]),"status":"PASS"}
                metrics["synthetic_active"]=item
            print("[PASS] "+name+" "+json.dumps(item),flush=True)
        metrics.update(status="PASS",reason="CSR permission/full-value/Timer directed scoreboards completed")
        code=0
    except (OSError,ValueError,AssertionError,RuntimeError) as error:
        metrics["reason"]=str(error)
        print("[ERROR] "+str(error),flush=True)
    finally:
        changed=[p for p,h in record["sources_sha256"].items() if legacy.sha256(ROOT/p)!=h]
        metrics["source_changed_during_run"]=changed
        if changed:metrics.update(status="ERROR",reason="source changed during run");code=2
        record["data_sha256"]={p.relative_to(out).as_posix():legacy.sha256(p) for p in (out/"data").rglob("*") if p.is_file()}
        record["finished_utc"]=datetime.now(timezone.utc).isoformat()
        legacy.save_json(out/"manifest.json",record)
        legacy.save_json(out/"metrics.json",metrics)
        (out/"README.md").write_text("# Phase 2 CSR/Timer\n\nResult: "+metrics["status"]+"\n\n"
            "See metrics.json, manifest.json, data/, logs/, source_snapshot/.\n"
            "Qualified engine activity is synthetic; real LOAD/GEMM/STORE/ARGMAX are not executed.\n"
            "No Phase 3, waveform, synthesis or implementation performed.\n",encoding="utf-8")
        print("[RESULT] "+metrics["status"]+" "+str(out),flush=True)
    return code

if __name__=="__main__":
    raise SystemExit(main())
