"""Phase 4 Scalar LW/SW, mixed block ownership and independent Python comparison."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
import run_phase1 as scalar
import phase4_vectors as vectors
ROOT=scalar.ROOT
legacy=scalar.legacy
RTL=scalar.SOURCES[:-1]

def selfcheck():
    checks=0
    for actual,expected in [(vectors.lw(5,1,4),0x0040a283),
                            (vectors.sw(2,1,-4),0xfe20ae23),
                            (vectors.lw(5,1,-2048),0x8000a283),
                            (vectors.lw(5,1,2047),0x7ff0a283)]:
        assert actual==expected
        checks+=1
    for imm in range(-2048,2048):
        i=vectors.lw(5,1,imm);s=vectors.sw(2,1,imm)
        assert scalar.signed(i>>20,12)==imm
        assert scalar.signed(((s>>25)<<5)|((s>>7)&31),12)==imm
        checks+=2
    for address,expected in [(vectors.BASE,0),(vectors.BASE+4092,0),
        (vectors.BASE+4096,6),(0x20000000,4),(0x80000000,4),(0xf0000001,5),
        (0x100000000,6),(-4,6),(-1,5),(0x100000001,5)]:
        assert vectors.scalar_error(address,4096)==expected
        checks+=1
    return checks

def compare_observed(data,listing):
    checks=0
    for case in listing:
        for expected_suffix,actual_suffix in [("trace","observed_trace"),("final","observed_final")]:
            def load(suffix):
                return [int(x,16) for x in (data/f"case_{case['id']}.{suffix}.hex").read_text().split()]
            expected=load(expected_suffix);actual=load(actual_suffix)
            assert actual==expected,f"Python observed comparison failed: {case['name']} {actual_suffix}"
            checks+=len(expected)
    return checks

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-bin",type=Path)
    parser.add_argument("--debug-only",action="store_true",help="One short mixed program with WDB/VCD timing capture")
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    run_id="npu_phase4_"+stamp
    out=ROOT/"07_runs"/run_id;out.mkdir(parents=True,exist_ok=False)
    build=ROOT/"99_build"/run_id;build.mkdir(parents=True,exist_ok=False)
    print("[RUN] "+str(out),flush=True)
    record={"phase":4,"git":legacy.git_state(ROOT),"python":sys.version,"stages":[],
            "sources_sha256":{},"waveform_recording":"debug job only"}
    metrics={"status":"ERROR","profiles":[],"phase5_started":False}
    exit_code=2
    try:
        metrics["golden_unit_checks"]=selfcheck()
        tools=legacy.find_tools(args.vivado_bin)
        snap=out/"source_snapshot"
        names=RTL+["05_tb/npu/tb_npu_phase4.sv","90_scripts/npu/run_phase1.py",
            "90_scripts/npu/run_phase4.py","90_scripts/npu/phase4_vectors.py",
            "90_scripts/npu/phase3_vectors.py","90_scripts/npu/phase2_vectors.py","90_scripts/run.py"]
        for name in names:
            p=snap/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
            record["sources_sha256"][name]=legacy.sha256(p)
        record["spec_sha256"]={p:legacy.sha256(ROOT/p) for p in [
            "00_docs/programmable_npu/01_isa_spec.md","00_docs/programmable_npu/02_architecture.md",
            "00_docs/programmable_npu/03_implementation_plan.md","00_docs/programmable_npu/04_verification_plan.md"]}
        jobs=[("debug",4096,False,True)]
        if not args.debug_only:jobs += [("65536",65536,True,False),("4096",4096,False,False),("16777216",16777216,False,False)]
        for name,capacity,full,debug in jobs:
            data=out/"data"/name
            listing=vectors.generate(data,capacity,full,debug=debug)
            work=build/name;work.mkdir()
            logs=out/"logs"/name;logs.mkdir(parents=True)
            simargs=["phase4_sim","-onerror","quit","-onfinish","quit",
                     "-testplusarg","DATA_DIR="+data.as_posix(),"-log","xsim.log"]
            if debug:
                (work/"wave.tcl").write_text("log_wave -r /tb_npu_phase4/u_dut/*\n"
                    "open_vcd {"+(out/"timing.vcd").as_posix()+"}\n"
                    "log_vcd /tb_npu_phase4/clk /tb_npu_phase4/rst_n /tb_npu_phase4/imem_en "
                    "/tb_npu_phase4/imem_addr /tb_npu_phase4/dmem_en /tb_npu_phase4/dmem_we "
                    "/tb_npu_phase4/dmem_addr /tb_npu_phase4/dmem_wdata /tb_npu_phase4/dmem_rdata "
                    "/tb_npu_phase4/u_dut/u_instruction_controller/register_write "
                    "/tb_npu_phase4/u_dut/u_instruction_controller/register_write_data "
                    "/tb_npu_phase4/u_dut/u_instruction_controller/state\n"
                    "run all\nclose_vcd\nquit\n",encoding="utf-8")
                simargs += ["-wdb",(out/"timing.wdb").as_posix(),"-tclbatch","wave.tcl"]
            else:simargs += ["-R"]
            commands=[
                ("compile","xvlog",["-sv","-i",data.as_posix(),*[(snap/p).as_posix() for p in RTL],
                    (snap/"05_tb/npu/tb_npu_phase4.sv").as_posix(),"-log","xvlog.log"]),
                ("elaborate","xelab",["work.tb_npu_phase4","-s","phase4_sim","-debug",
                    "typical" if debug else "off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",simargs)]
            for stage,tool,arguments in commands:
                rc,text=legacy.run_stage(stage,tools[tool],arguments,work,logs,300,record["stages"])
                if rc or legacy.ERROR_LINE.search(text):
                    print(text[-6000:],flush=True)
                    raise RuntimeError(name+" "+stage+" failed; see "+str(logs))
            found=re.findall(r"^\[PHASE4\] result=PASS capacity=(\d+) cases=(\d+) steps=(\d+) events=(\d+) checks=(\d+)$",text,re.M)
            wanted=(capacity,len(listing),sum(x["steps"] for x in listing),sum(x["events"] for x in listing))
            assert len(found)==1 and tuple(map(int,found[0][:4]))==wanted and int(found[0][4])>0,"incomplete Phase 4 summary"
            python_checks=compare_observed(data,listing)
            item={"profile":name,"dmem_bytes":capacity,"cases":wanted[1],"steps":wanted[2],
                  "events":wanted[3],"rtl_checks":int(found[0][4]),"python_checks":python_checks,"status":"PASS"}
            if debug:
                assert (out/"timing.wdb").stat().st_size>0 and (out/"timing.vcd").stat().st_size>0
            metrics["profiles"].append(item)
            print("[PASS] "+name+" "+json.dumps(item),flush=True)
        metrics.update(status="PASS",reason="Scalar memory/mixed block timing and Python observed-data comparisons completed")
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
        legacy.save_json(out/"manifest.json",record);legacy.save_json(out/"metrics.json",metrics)
        (out/"README.md").write_text("# Phase 4 Scalar LW/SW\n\nResult: "+metrics["status"]+"\n\n"
            "See metrics.json, manifest.json, data/, logs/, source_snapshot/.\n"
            "Only debug records timing.wdb and timing.vcd; bulk profiles have no waveform recording.\n"
            "Every observed trace/final dump is compared by Python after the RTL scoreboard.\n"
            "Phase 5 GEMM is not started.\n",encoding="utf-8")
        print("[RESULT] "+metrics["status"]+" "+str(out),flush=True)
    return exit_code
if __name__=="__main__":
    raise SystemExit(main())
