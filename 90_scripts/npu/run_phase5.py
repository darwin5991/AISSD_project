"""Phase 5 CSR GEMM integration, arithmetic/timing/fault and Legacy layer comparison."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
import run_phase1 as scalar
import phase5_vectors as vectors
ROOT=scalar.ROOT
legacy=scalar.legacy
RTL=scalar.SOURCES[:-1]

def selfcheck():
    sys.path.insert(0,str(ROOT/"03_model/golden"))
    import accumulator_postprocess_golden as saved
    checks=0
    for shift in range(-32,32):
        for value in [-128,-127,-1,0,1,126,127]:
            expected=vectors.wrap32(value<<shift) if shift>=0 else value>>-shift
            assert int(saved.aligned_bias([value],shift)[0])==expected
            checks+=1
    for value in [-(1<<33),-(1<<31)-1,-(1<<31),-1,0,1,(1<<31)-1,1<<31,1<<32]:
        assert int(saved.wrap32([value])[0])==vectors.wrap32(value)
        checks+=1
    assert vectors.GEMM==0x0000202b
    assert vectors.wrap32(0x7fffffff+1)==-0x80000000
    assert vectors.wrap32(-0x80000000-1)==0x7fffffff
    return checks+3

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
    run_id="npu_phase5_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out=ROOT/"07_runs"/run_id;out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"99_build"/run_id;build.mkdir(parents=True,exist_ok=False)
    print("[RUN] "+str(out),flush=True)
    record={"phase":5,"git":legacy.git_state(ROOT),"python":sys.version,"stages":[],
            "sources_sha256":{},"waveform_recording":"debug only"}
    metrics={"status":"ERROR","profiles":[],"phase6_started":False,"minimum_k":8,"minimum_k_user_finalized":True}
    code=2
    try:
        metrics["golden_unit_checks"]=selfcheck()
        tools=legacy.find_tools(args.vivado_bin)
        snap=out/"source_snapshot"
        names=RTL+["05_tb/npu/tb_npu_phase5.sv","90_scripts/npu/run_phase1.py",
            "90_scripts/npu/run_phase5.py","90_scripts/npu/phase5_vectors.py",
            "90_scripts/npu/phase4_vectors.py","90_scripts/npu/phase3_vectors.py",
            "90_scripts/npu/phase2_vectors.py","90_scripts/run.py"]
        names += [p.relative_to(ROOT).as_posix() for p in (ROOT/"03_model/golden").glob("*.py")]
        for name in names:
            p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
            record["sources_sha256"][name]=legacy.sha256(p)
        record["spec_sha256"]={p:legacy.sha256(ROOT/p) for p in [
            "00_docs/programmable_npu/01_isa_spec.md","00_docs/programmable_npu/02_architecture.md",
            "00_docs/programmable_npu/03_implementation_plan.md","00_docs/programmable_npu/04_verification_plan.md",
            "00_docs/programmable_npu/14_phase5_decisions.md"]}
        jobs=[("debug",16384,False,True)]
        if not args.debug_only:jobs += [("1048576",1048576,True,False),("16777216",16777216,False,False)]
        if args.case:jobs=[("debug",1048576,True,True)]
        metrics["selected_case"]=args.case
        for name,capacity,full,debug in jobs:
            data=out/"data"/name;listing=vectors.generate(data,capacity,full,debug,case_name=args.case)
            print("[DATA] "+name+" "+str(len(listing))+" cases",flush=True)
            work=build/name;work.mkdir();logs=out/"logs"/name;logs.mkdir(parents=True)
            simargs=["phase5_sim","-onerror","quit","-onfinish","quit",
                "-testplusarg","DATA_DIR="+data.as_posix(),"-log","xsim.log"]
            if debug:
                signals=["clk","rst_n","imem_en","imem_addr","dmem_en","dmem_we",
                    "u_dut/gemm_start","u_dut/gemm_active","u_dut/gemm_done","u_dut/gemm_we",
                    "u_dut/u_gemm/u_control/state","u_dut/u_gemm/u_control/read_issue",
                    "u_dut/u_gemm/u_control/input_word","u_dut/u_gemm/u_control/output_group",
                    "u_dut/u_gemm/mac_input_valid","u_dut/u_gemm/bias_load",
                    "u_dut/u_gemm/result_load","u_dut/u_gemm/u_accumulator/psum_valid",
                    "u_dut/u_gemm/u_bias/word_in"]
                selected=" ".join("/tb_npu_phase5/"+p for p in signals)
                (work/"wave.tcl").write_text("log_wave "+selected+"\nopen_vcd {"+(out/"timing.vcd").as_posix()+"}\n"
                    "log_vcd "+selected+"\nrun all\nclose_vcd\nquit\n",encoding="utf-8")
                simargs += ["-wdb",(out/"timing.wdb").as_posix(),"-tclbatch","wave.tcl"]
            else:simargs += ["-R"]
            commands=[
                ("compile","xvlog",["-sv","-i",data.as_posix(),*[(snap/p).as_posix() for p in RTL],
                    (snap/"05_tb/npu/tb_npu_phase5.sv").as_posix(),"-log","xvlog.log"]),
                ("elaborate","xelab",["work.tb_npu_phase5","-s","phase5_sim","-debug",
                    "typical" if debug else "off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",simargs)]
            for stage,tool,arguments in commands:
                rc,text=legacy.run_stage(stage,tools[tool],arguments,work,logs,300,record["stages"])
                if rc or legacy.ERROR_LINE.search(text):
                    print(text[-7000:],flush=True)
                    raise RuntimeError(name+" "+stage+" failed; see "+str(logs))
            found=re.findall(r"^\[PHASE5\] result=PASS capacity=(\d+) cases=(\d+) steps=(\d+) events=(\d+) controls=(\d+) numeric=(\d+) checks=(\d+)$",text,re.M)
            wanted=(capacity,len(listing),sum(x["steps"] for x in listing),sum(x["events"] for x in listing),
                    sum(x["controls"] for x in listing),sum(x["numeric"] for x in listing))
            assert len(found)==1 and tuple(map(int,found[0][:6]))==wanted and int(found[0][6])>0,"incomplete Phase 5 verdict"
            python_checks=compare_observed(data,listing)
            item={"profile":name,"dmem_bytes":capacity,"cases":wanted[1],"steps":wanted[2],
                  "events":wanted[3],"controls":wanted[4],"numeric":wanted[5],
                  "rtl_checks":int(found[0][6]),"python_checks":python_checks,
                  "legacy_words":sum(x["legacy_words"] for x in listing),"status":"PASS"}
            if full and not args.case:
                boundaries=[c for c in listing if c["name"].startswith("k") and "_boundary1" in c["name"]]
                assert len(boundaries)==72 and all(c["error"]==0 for c in boundaries)
                metrics["k_boundary_cases"]=len(boundaries)
                metrics["minimum_k"]=8
            if debug:assert (out/"timing.vcd").stat().st_size and (out/"timing.wdb").stat().st_size
            metrics["profiles"].append(item)
            print("[PASS] "+name+" "+json.dumps(item),flush=True)
        metrics.update(status="PASS",reason="GEMM timing/INT32/Snapshot/Fault and Python observed dump comparisons complete")
        code=0
    except (OSError,ValueError,AssertionError,RuntimeError,KeyError) as error:
        metrics["reason"]=str(error);print("[ERROR] "+str(error),flush=True)
    finally:
        changed=[p for p,h in record["sources_sha256"].items() if legacy.sha256(ROOT/p)!=h]
        metrics["source_changed_during_run"]=changed
        if changed:metrics.update(status="ERROR",reason="source changed during run");code=2
        record["legacy_source"]=str(vectors.SOURCE)
        record["legacy_data_sha256"]=vectors.SOURCE_HASHES
        record["data_sha256"]={p.relative_to(out).as_posix():legacy.sha256(p) for p in (out/"data").rglob("*") if p.is_file()}
        record["finished_utc"]=datetime.now(timezone.utc).isoformat()
        legacy.save_json(out/"manifest.json",record);legacy.save_json(out/"metrics.json",metrics)
        (out/"README.md").write_text("# Phase 5 GEMM\n\nResult: "+metrics["status"]+"\n\n"
            "See metrics.json, manifest.json, data/, logs/, source_snapshot/.\n"
            "Numeric dumps compare every accumulator/result update as signed INT32 bit patterns.\n"
            "Debug waveform only; no synthesis/FPGA/MNIST accuracy or Phase 6 implementation.\n",encoding="utf-8")
        print("[RESULT] "+metrics["status"]+" "+str(out),flush=True)
    return code
if __name__=="__main__":raise SystemExit(main())
