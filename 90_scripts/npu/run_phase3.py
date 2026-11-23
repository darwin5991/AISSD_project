"""Phase 3: serial block LOAD/STORE. Scalar LW/SW remain Phase 4."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
import run_phase1 as scalar
import phase3_vectors as vectors
ROOT=scalar.ROOT
legacy=scalar.legacy
RTL=scalar.SOURCES[:-1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-bin",type=Path,help="Vivado bin; default: PATH")
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    run_id="npu_phase3_"+stamp
    out=ROOT/"07_runs"/run_id;out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"99_build"/run_id;build.mkdir(parents=True,exist_ok=False)
    print("[RUN] "+str(out),flush=True)
    record={"phase":3,"git":legacy.git_state(ROOT),"python":sys.version,"stages":[],"sources_sha256":{},"waveform_recording":False}
    metrics={"status":"ERROR","profiles":[],"owner":None,"phase4_started":False}
    exit_code=2
    try:
        assert vectors.transfer(1,2,3)==0x002081ab
        assert vectors.transfer(1,2,3,True)==0x002091ab
        tools=legacy.find_tools(args.vivado_bin)
        snap=out/"source_snapshot"
        names=RTL+["05_tb/npu/tb_npu_phase3.sv","05_tb/npu/tb_npu_memory_owner.sv",
            "90_scripts/npu/run_phase1.py","90_scripts/npu/run_phase3.py",
            "90_scripts/npu/phase3_vectors.py","90_scripts/npu/phase2_vectors.py","90_scripts/run.py"]
        for name in names:
            p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
            record["sources_sha256"][name]=legacy.sha256(p)
        record["spec_sha256"]={p:legacy.sha256(ROOT/p) for p in [
            "00_docs/programmable_npu/01_isa_spec.md","00_docs/programmable_npu/03_implementation_plan.md",
            "00_docs/programmable_npu/10_phase3_decisions.md"]}
        jobs=[]
        for capacity,full in [(262144,True),(16777216,False)]:
            data=out/"data"/str(capacity)
            listing=vectors.generate(data,capacity,full)
            jobs.append((str(capacity),"tb_npu_phase3","05_tb/npu/tb_npu_phase3.sv",data,listing))
        jobs.append(("owner","tb_npu_memory_owner","05_tb/npu/tb_npu_memory_owner.sv",None,None))
        for name,tb,tb_file,data,listing in jobs:
            work=build/name;work.mkdir()
            logs=out/"logs"/name;logs.mkdir(parents=True)
            commands=[
                ("compile","xvlog",["-sv",*(["-i",data.as_posix()] if data else []),*[(snap/p).as_posix() for p in RTL],(snap/tb_file).as_posix(),"-log","xvlog.log"]),
                ("elaborate","xelab",["work."+tb,"-s","phase3_sim","-debug","off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",["phase3_sim","-R","-onerror","quit","-onfinish","quit",
                    *(["-testplusarg","DATA_DIR="+data.as_posix()] if data else []),"-log","xsim.log"]),
            ]
            for stage,tool,arguments in commands:
                rc,text=legacy.run_stage(stage,tools[tool],arguments,work,logs,300,record["stages"])
                if rc or legacy.ERROR_LINE.search(text):
                    print(text[-6000:],flush=True)
                    raise RuntimeError(name+" "+stage+" failed; see "+str(logs))
            if data:
                found=re.findall(r"^\[PHASE3\] result=PASS capacity=(\d+) cases=(\d+) steps=(\d+) events=(\d+) checks=(\d+)$",text,re.M)
                wanted=(int(name),len(listing),sum(x["steps"] for x in listing),sum(x["events"] for x in listing))
                assert len(found)==1 and tuple(map(int,found[0][:4]))==wanted and int(found[0][4])>0,"incomplete Phase 3 summary"
                item={"dmem_bytes":int(name),"cases":wanted[1],"steps":wanted[2],"events":wanted[3],"checks":int(found[0][4]),"status":"PASS"}
                metrics["profiles"].append(item)
            else:
                found=re.findall(r"^\[MEMORY_OWNER\] result=PASS banks=(\d+) checks=(\d+)$",text,re.M)
                assert len(found)==1 and int(found[0][0])==7 and int(found[0][1])>0
                item={"banks":7,"checks":int(found[0][1]),"status":"PASS"}
                metrics["owner"]=item
            print("[PASS] "+name+" "+json.dumps(item),flush=True)
        metrics.update(status="PASS",reason="block memory/Timer/Fault/owner scoreboards completed")
        exit_code=0
    except (OSError,ValueError,AssertionError,RuntimeError) as error:
        metrics["reason"]=str(error)
        print("[ERROR] "+str(error),flush=True)
    finally:
        changed=[p for p,h in record["sources_sha256"].items() if legacy.sha256(ROOT/p)!=h]
        metrics["source_changed_during_run"]=changed
        if changed:metrics.update(status="ERROR",reason="source changed during run");exit_code=2
        record["data_sha256"]={p.relative_to(out).as_posix():legacy.sha256(p) for p in (out/"data").rglob("*") if p.is_file()}
        record["finished_utc"]=datetime.now(timezone.utc).isoformat()
        legacy.save_json(out/"manifest.json",record)
        legacy.save_json(out/"metrics.json",metrics)
        (out/"README.md").write_text("# Phase 3 block transfers\n\nResult: "+metrics["status"]+"\n\n"
            "See metrics.json, manifest.json, data/, logs/, source_snapshot/.\n"
            "Runtime fault injection targets only a transfer cursor in TB; no external error pin is added.\n"
            "No Scalar LW/SW, GEMM/ARGMAX implementation, waveform or synthesis performed.\n",encoding="utf-8")
        print("[RESULT] "+metrics["status"]+" "+str(out),flush=True)
    return exit_code
if __name__=="__main__":
    raise SystemExit(main())
