"""Phase 6 independent ARGMAX, CSR snapshots, raw bounds, timing and regressions."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
import run_phase1 as scalar
import phase6_vectors as vectors
ROOT=scalar.ROOT
legacy=scalar.legacy
RTL=scalar.SOURCES[:-1]

def selfcheck():
    checks=0
    for base,depth in vectors.p3.BANKS[:2]:
        t=base+depth*4
        rows=[(base,0,7),(base,11,7),(t-4,4,0),(t-4,5,6),(t-12,10,0),
              (t-8,10,6),(t-12,11,7),(t-8,11,6),(t,0,6),(t,1,6),(base+1,0,5),
              (base,16,7),(base,0x10000001,6),(base,0xfffffffc,6),
              (base,0xfffffffd,6),(base,0xffffffff,6),(t-4,1,0),(t-4,3,0),(t-12,9,0)]
        for src,n,error in rows:
            assert vectors.arg_error(src,n)==error;checks+=1
    for src in [0,0x10000000,0xf0000000,0x800e0000,*[b for b,d in vectors.p3.BANKS[2:]]]:
        for n in [0,11,0xffffffff]:
            assert vectors.arg_error(src,n)==4;assert vectors.arg_error(src+1,n)==5;checks+=2
    for a in [0,5,4,6,7]:
        for b in [0,5,4,6,7]:
            ordered=[e for e in [5,4,6,7] if e in [a,b]]
            assert vectors.p3.merge_memory_errors(a,b)==(ordered[0] if ordered else 0);checks+=1
    assert vectors.argmax(5)==0x020022ab
    return checks+1

def compare_observed(data,listing):
    checks=0
    for case in listing:
        for suffix in ["trace","final","numeric","arg"]:
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
    run_id="npu_phase6_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out=ROOT/"07_runs"/run_id;out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"99_build"/run_id;build.mkdir(parents=True,exist_ok=False)
    print("[RUN] "+str(out),flush=True)
    record={"phase":6,"git":legacy.git_state(ROOT),"python":sys.version,"stages":[],
            "sources_sha256":{},"waveform_recording":"debug only"}
    metrics={"status":"ERROR","profiles":[],"phase7_started":False,"phase8_started":False}
    code=2
    try:
        metrics["golden_unit_checks"]=selfcheck()
        tools=legacy.find_tools(args.vivado_bin)
        snap=out/"source_snapshot"
        names=RTL+["05_tb/npu/tb_npu_phase6.sv","90_scripts/npu/run_phase1.py",
            "90_scripts/npu/run_phase6.py","90_scripts/npu/phase6_vectors.py","90_scripts/npu/phase5_vectors.py",
            "90_scripts/npu/phase4_vectors.py","90_scripts/npu/phase3_vectors.py",
            "90_scripts/npu/phase2_vectors.py","90_scripts/run.py"]
        names += [p.relative_to(ROOT).as_posix() for p in (ROOT/"03_model/golden").glob("*.py")]
        for name in names:
            p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
            record["sources_sha256"][name]=legacy.sha256(p)
        record["spec_sha256"]={p:legacy.sha256(ROOT/p) for p in [
            "00_docs/programmable_npu/01_isa_spec.md","00_docs/programmable_npu/02_architecture.md",
            "00_docs/programmable_npu/03_implementation_plan.md","00_docs/programmable_npu/04_verification_plan.md",
            "00_docs/programmable_npu/17_phase6_decisions.md"]}
        jobs=[("debug",16384,"debug",4096,True)]
        if not args.debug_only:jobs += [("65536",65536,"full",4096,False),("imem65536",65536,"pc",65536,False),("16777216",16777216,"debug",65536,False)]
        if args.case:jobs=[("debug",65536,"full",4096,True)]
        metrics["selected_case"]=args.case
        for name,capacity,profile,imem_bytes,debug in jobs:
            data=out/"data"/name;listing=vectors.generate(data,capacity,profile,imem_bytes,case_name=args.case)
            print("[DATA] "+name+" "+str(len(listing))+" cases",flush=True)
            work=build/name;work.mkdir();logs=out/"logs"/name;logs.mkdir(parents=True)
            simargs=["phase6_sim","-onerror","quit","-onfinish","quit",
                "-testplusarg","DATA_DIR="+data.as_posix(),"-log","xsim.log"]
            if debug:
                signals=["clk","rst_n","imem_en","imem_addr","dmem_en","dmem_we","done","fault",
                    "u_dut/argmax_start","u_dut/argmax_active","u_dut/argmax_done","u_dut/argmax_result",
                    "u_dut/argmax_en","u_dut/argmax_address","u_dut/argmax_rdata","u_dut/argmax_error",
                    "u_dut/u_memory/owner","u_dut/u_memory/ram_en","u_dut/u_memory/ram_we",
                    "probe_a","probe_b",
                    "u_dut/u_argmax/state","u_dut/u_argmax/index","u_dut/u_argmax/initialize","u_dut/u_argmax/compare_en",
                    "u_dut/u_argmax/words_full","u_dut/u_argmax/end_full",
                    "u_dut/u_argmax/u_compare/candidate","u_dut/u_argmax/u_compare/max_value","u_dut/u_argmax/u_compare/greater",
                    "u_dut/u_instruction_controller/pc","u_dut/u_instruction_controller/register_write",
                    "u_dut/u_instruction_controller/register_write_address","u_dut/u_instruction_controller/register_write_data",
                    "u_dut/u_instruction_controller/perf_count","u_dut/u_instruction_controller/timer_armed",
                    "u_dut/u_instruction_controller/perf_overflow"]
                selected=" ".join("{/tb_npu_phase6/"+p+"}" for p in signals)
                (work/"wave.tcl").write_text("log_wave "+selected+"\nopen_vcd {"+(out/"timing.vcd").as_posix()+"}\n"
                    "log_vcd "+selected+"\nrun all\nclose_vcd\nquit\n",encoding="utf-8")
                simargs += ["-wdb",(out/"timing.wdb").as_posix(),"-tclbatch","wave.tcl"]
            else:simargs += ["-R"]
            commands=[
                ("compile","xvlog",["-sv","-i",data.as_posix(),*[(snap/p).as_posix() for p in RTL],
                    (snap/"05_tb/npu/tb_npu_phase6.sv").as_posix(),"-log","xvlog.log"]),
                ("elaborate","xelab",["work.tb_npu_phase6","-s","phase6_sim","-debug",
                    "typical" if debug else "off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",simargs)]
            for stage,tool,arguments in commands:
                rc,text=legacy.run_stage(stage,tools[tool],arguments,work,logs,300,record["stages"])
                if rc or legacy.ERROR_LINE.search(text):
                    print(text[-7000:],flush=True)
                    raise RuntimeError(name+" "+stage+" failed; see "+str(logs))
            found=re.findall(r"^\[PHASE6\] result=PASS capacity=(\d+) cases=(\d+) steps=(\d+) events=(\d+) controls=(\d+) numeric=(\d+) checks=(\d+) args=(\d+) reset_aborts=(\d+)$",text,re.M)
            wanted=(capacity,len(listing),sum(x["steps"] for x in listing),sum(x["events"] for x in listing),
                    sum(x["controls"] for x in listing),sum(x["numeric"] for x in listing))
            assert len(found)==1 and tuple(map(int,found[0][:6]))==wanted and int(found[0][6])>0,"incomplete Phase 6 verdict"
            expected_args=sum(x["args"] for x in listing)
            expected_resets=sum(x["hook"]==13 for x in listing)
            assert int(found[0][7])==expected_args and int(found[0][8])==expected_resets,"incomplete ARGMAX/Reset coverage"
            python_checks=compare_observed(data,listing)
            item={"profile":name,"dmem_bytes":capacity,"imem_bytes":imem_bytes,"arg_samples":expected_args,"reset_aborts":expected_resets,"cases":wanted[1],"steps":wanted[2],
                  "events":wanted[3],"controls":wanted[4],"numeric":wanted[5],
                  "rtl_checks":int(found[0][6]),"python_checks":python_checks,
                  "legacy_words":sum(x["legacy_words"] for x in listing),"status":"PASS"}
            tags=sorted({tag for c in listing for tag in c["tags"]})
            item["test_ids"]=tags
            if profile=="full" and not args.case:
                required=[f"A-{i:02d}" for i in range(1,17)]+[f"A-B{i:02d}" for i in range(1,19)]+[f"A-P{i:02d}" for i in range(1,8)]
                assert set(required)<=set(tags),"missing planned test IDs"
                metrics["required_test_ids"]=required
            if debug:assert (out/"timing.vcd").stat().st_size and (out/"timing.wdb").stat().st_size
            metrics["profiles"].append(item)
            print("[PASS] "+name+" "+json.dumps(item),flush=True)
        metrics.update(status="PASS",reason="ARGMAX signed/Snapshot/raw bounds/PC fault/timing/Timer/Reset and Python observed dump comparisons complete")
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
        (out/"README.md").write_text("# Phase 6 ARGMAX\n\nResult: "+metrics["status"]+"\n\n"
            "See metrics.json, manifest.json, data/, logs/, source_snapshot/.\n"
            "ARGMAX dumps compare every signed candidate, old/new maximum and selected index.\n"
            "Debug waveform only; no synthesis/FPGA/MNIST accuracy or Phase 7/8 implementation.\n",encoding="utf-8")
        print("[RESULT] "+metrics["status"]+" "+str(out),flush=True)
    return code
if __name__=="__main__":raise SystemExit(main())
