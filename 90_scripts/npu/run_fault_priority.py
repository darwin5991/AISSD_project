"""Memory/next-PC fault-priority follow-up; Phase 6 is out of scope."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
import run_phase1 as scalar
import fault_priority_vectors as vectors
ROOT=scalar.ROOT
legacy=scalar.legacy
RTL=scalar.SOURCES[:-1]

def selfcheck():
    import phase3_vectors as p3
    checks=0
    order=[5,4,6,7]
    for a in [0,*order]:
        for b in [0,*order]:
            expected=next((e for e in order if e in [a,b]),0)
            assert p3.merge_memory_errors(a,b)==expected
            checks+=1
    return checks

def compare_observed(data,listing):
    checks=0
    for case in listing:
        for suffix in ["trace","final","numeric"]:
            def load(name):return [int(x,16) for x in (data/f"case_{case['id']}.{name}.hex").read_text().split()]
            expected=load(suffix);actual=load("observed_"+suffix)
            assert actual==expected,f"Python observed comparison: {case['name']} {suffix}"
            checks+=len(expected)
    return checks

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-bin",type=Path)
    parser.add_argument("--debug-only",action="store_true")
    parser.add_argument("--case",help="One named directed scenario with debug waveform")
    args=parser.parse_args()
    run_id="npu_fault_priority_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out=ROOT/"07_runs"/run_id;out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"99_build"/run_id;build.mkdir(parents=True,exist_ok=False)
    print("[RUN] "+str(out),flush=True)
    record={"scope":"memory_next_pc_fault_priority","git":legacy.git_state(ROOT),"python":sys.version,"stages":[],
            "sources_sha256":{},"waveform_recording":"debug only"}
    metrics={"status":"ERROR","profiles":[],"phase6_started":False}
    code=2
    try:
        metrics["golden_unit_checks"]=selfcheck()
        tools=legacy.find_tools(args.vivado_bin)
        snap=out/"source_snapshot"
        names=RTL+["05_tb/npu/tb_npu_fault_priority.sv","90_scripts/npu/run_phase1.py",
            "90_scripts/npu/run_fault_priority.py","90_scripts/npu/fault_priority_vectors.py",
            "90_scripts/npu/phase5_vectors.py","90_scripts/npu/phase4_vectors.py","90_scripts/npu/phase3_vectors.py",
            "90_scripts/npu/phase2_vectors.py","90_scripts/run.py"]
        for name in names:
            p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
            record["sources_sha256"][name]=legacy.sha256(p)
        record["spec_sha256"]={p:legacy.sha256(ROOT/p) for p in [
            "00_docs/programmable_npu/01_isa_spec.md","00_docs/programmable_npu/02_architecture.md",
            "00_docs/programmable_npu/03_implementation_plan.md","00_docs/programmable_npu/04_verification_plan.md",
            "00_docs/programmable_npu/14_phase5_decisions.md"]}
        jobs=[("debug",4096,False,True)]
        if not args.debug_only:jobs += [("4096",4096,True,False),("16777216",16777216,False,False)]
        if args.case:jobs=[("debug",4096,True,True)]
        metrics["selected_case"]=args.case
        for name,capacity,full,debug in jobs:
            data=out/"data"/name;listing=vectors.generate(data,capacity,full,debug,case_name=args.case)
            print("[DATA] "+name+" "+str(len(listing))+" cases",flush=True)
            work=build/name;work.mkdir();logs=out/"logs"/name;logs.mkdir(parents=True)
            simargs=["fault_priority_sim","-onerror","quit","-onfinish","quit",
                "-testplusarg","DATA_DIR="+data.as_posix(),"-log","xsim.log"]
            if debug:
                signals=["clk","rst_n","imem_en","imem_addr","dmem_en","dmem_we",
                    "u_dut/gemm_start","u_dut/gemm_active","u_dut/gemm_done","u_dut/gemm_we",
                    "u_dut/u_gemm/u_control/state","u_dut/u_gemm/u_control/read_issue",
                    "u_dut/u_gemm/u_control/input_word","u_dut/u_gemm/u_control/output_group",
                    "u_dut/u_gemm/mac_input_valid","u_dut/u_gemm/bias_load",
                    "u_dut/u_gemm/result_load","u_dut/u_gemm/u_accumulator/psum_valid",
                    "u_dut/u_gemm/u_bias/word_in"]
                selected=" ".join("/tb_npu_fault_priority/"+p for p in signals)
                (work/"wave.tcl").write_text("log_wave "+selected+"\nopen_vcd {"+(out/"timing.vcd").as_posix()+"}\n"
                    "log_vcd "+selected+"\nrun all\nclose_vcd\nquit\n",encoding="utf-8")
                simargs += ["-wdb",(out/"timing.wdb").as_posix(),"-tclbatch","wave.tcl"]
            else:simargs += ["-R"]
            commands=[
                ("compile","xvlog",["-sv","-i",data.as_posix(),*[(snap/p).as_posix() for p in RTL],
                    (snap/"05_tb/npu/tb_npu_fault_priority.sv").as_posix(),"-log","xvlog.log"]),
                ("elaborate","xelab",["work.tb_npu_fault_priority","-s","fault_priority_sim","-debug",
                    "typical" if debug else "off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",simargs)]
            for stage,tool,arguments in commands:
                rc,text=legacy.run_stage(stage,tools[tool],arguments,work,logs,300,record["stages"])
                if rc or legacy.ERROR_LINE.search(text):
                    print(text[-7000:],flush=True)
                    raise RuntimeError(name+" "+stage+" failed; see "+str(logs))
            found=re.findall(r"^\[FAULT_PRIORITY\] result=PASS capacity=(\d+) cases=(\d+) steps=(\d+) events=(\d+) controls=(\d+) numeric=(\d+) checks=(\d+)$",text,re.M)
            wanted=(capacity,len(listing),sum(x["steps"] for x in listing),sum(x["events"] for x in listing),
                    sum(x["controls"] for x in listing),sum(x["numeric"] for x in listing))
            assert len(found)==1 and tuple(map(int,found[0][:6]))==wanted and int(found[0][6])>0,"incomplete Fault priority verdict"
            python_checks=compare_observed(data,listing)
            item={"profile":name,"dmem_bytes":capacity,"cases":wanted[1],"steps":wanted[2],
                  "events":wanted[3],"controls":wanted[4],"numeric":wanted[5],
                  "rtl_checks":int(found[0][6]),"python_checks":python_checks,
                  "legacy_words":sum(x["legacy_words"] for x in listing),"status":"PASS"}
            if full:
                required=[c for c in listing if c["mandatory"]]
                assert len(required)==32
                metrics["mandatory_matrix_cases"]=len(required)
            if debug:assert (out/"timing.vcd").stat().st_size and (out/"timing.wdb").stat().st_size
            metrics["profiles"].append(item)
            print("[PASS] "+name+" "+json.dumps(item),flush=True)
        metrics.update(status="PASS",reason="memory/PC-priority/side-effect/Timer and Python observed dump comparisons complete")
        code=0
    except (OSError,ValueError,AssertionError,RuntimeError,KeyError) as error:
        metrics["reason"]=str(error);print("[ERROR] "+str(error),flush=True)
    finally:
        changed=[p for p,h in record["sources_sha256"].items() if legacy.sha256(ROOT/p)!=h]
        metrics["source_changed_during_run"]=changed
        if changed:metrics.update(status="ERROR",reason="source changed during run");code=2
        record["data_sha256"]={p.relative_to(out).as_posix():legacy.sha256(p) for p in (out/"data").rglob("*") if p.is_file()}
        record["finished_utc"]=datetime.now(timezone.utc).isoformat()
        legacy.save_json(out/"manifest.json",record);legacy.save_json(out/"metrics.json",metrics)
        (out/"README.md").write_text("# Memory/next-PC Fault priority\n\nResult: "+metrics["status"]+"\n\n"
            "See metrics.json, manifest.json, data/, logs/, source_snapshot/.\n"
            "Faulting instructions are checked for zero memory accesses and no architectural writes.\n"
            "Debug waveform only; no synthesis/FPGA/MNIST accuracy or Phase 6 implementation.\n",encoding="utf-8")
        print("[RESULT] "+metrics["status"]+" "+str(out),flush=True)
    return code
if __name__=="__main__":raise SystemExit(main())
